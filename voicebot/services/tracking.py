"""Shipment tracking: an external carrier API when configured, else the local order store."""

import logging
from typing import Any

import httpx

from voicebot.services.orders import OrderStore

logger = logging.getLogger(__name__)


def normalize_tracking_number(raw: str) -> str:
    # Callers read numbers digit by digit ("three, nine, seven ..."); STT may add spaces/dashes.
    return "".join(ch for ch in str(raw) if ch.isalnum())


class TrackingService:
    def __init__(
        self,
        orders: OrderStore,
        api_url: str | None = None,
        timeout: float = 5.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.orders = orders
        self.api_url = api_url
        self.timeout = timeout
        self._transport = transport

    async def status(self, tracking_number: str) -> dict[str, Any]:
        number = normalize_tracking_number(tracking_number)
        if not number:
            return {"status": "invalid", "message": "Please provide a tracking number."}
        if self.api_url:
            return await self._from_api(number)
        order = self.orders.get(number)
        if order is None:
            return {"status": "not_found", "message": f"No order found for {number}."}
        return {"status": "ok", "tracking_number": number, "shipment_status": order["status"]}

    async def _from_api(self, number: str) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout, transport=self._transport) as client:
                response = await client.get(self.api_url, params={"tracking_number": number})
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Tracking API failed for %s: %s", number, exc)
            return {"status": "unavailable", "message": "The tracking service is unavailable."}

        history = data.get("tracking_history") or [{}]
        latest = history[-1]
        # Deliberately omit consignee/shipper names, phones and addresses: anyone who knows
        # a tracking number can call the line, so personal data must never be read out.
        return {
            "status": "ok",
            "tracking_number": number,
            "shipment_status": latest.get("status") or data.get("tracking_status", "unknown"),
            "last_update": latest.get("date_time"),
            "origin_city": data.get("shipper_city"),
        }
