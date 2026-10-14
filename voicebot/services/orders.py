"""Minimal order store backed by a CSV file (swap for a database in production)."""

import csv
import secrets
import threading
from pathlib import Path
from typing import Any

FIELDS = ["tracking_number", "status", "address", "mobile_number", "items", "total_price"]


class OrderStore:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()

    def _read(self) -> list[dict[str, str]]:
        if not self.path.exists():
            return []
        with open(self.path, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def get(self, tracking_number: str) -> dict[str, str] | None:
        wanted = "".join(ch for ch in str(tracking_number) if ch.isdigit())
        return next((o for o in self._read() if o["tracking_number"] == wanted), None)

    def place(
        self, address: str, mobile_number: str, items: list[dict[str, Any]], total_price: float
    ) -> str:
        with self._lock:
            orders = self._read()
            taken = {o["tracking_number"] for o in orders}
            tracking_number = str(secrets.randbelow(900_000) + 100_000)
            while tracking_number in taken:
                tracking_number = str(secrets.randbelow(900_000) + 100_000)

            self.path.parent.mkdir(parents=True, exist_ok=True)
            is_new = not self.path.exists()
            with open(self.path, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=FIELDS)
                if is_new:
                    writer.writeheader()
                writer.writerow(
                    {
                        "tracking_number": tracking_number,
                        "status": "Order is being prepared",
                        "address": address,
                        # Kept as text so leading zeros / country codes survive.
                        "mobile_number": str(mobile_number),
                        "items": "; ".join(f"{i['item_quantity']} {i['item_name']}" for i in items),
                        "total_price": f"{total_price:g}",
                    }
                )
        return tracking_number
