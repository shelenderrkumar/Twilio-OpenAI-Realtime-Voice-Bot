"""Per-call shopping cart with stock and unit-of-measure validation.

Every operation returns a small dict with a ``status`` and a human-readable
``message``; the model turns that into a spoken reply.
"""

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from voicebot.services.catalog import Product, ProductMatcher

UNIT_ALIASES = {
    "kilogram": "kg", "kilograms": "kg", "kilo": "kg", "kilos": "kg", "kgs": "kg",
    "liter": "litre", "liters": "litre", "litres": "litre", "l": "litre",
    "units": "unit", "piece": "unit", "pieces": "unit", "pack": "unit", "packs": "unit",
    "packet": "unit", "packets": "unit", "item": "unit", "items": "unit",
    "dozens": "dozen",
}  # fmt: skip


def normalize_unit(unit: str) -> str:
    unit = unit.strip().lower()
    return UNIT_ALIASES.get(unit, unit)


def units_match(requested: str, expected: str) -> bool:
    requested, expected = normalize_unit(requested), normalize_unit(expected)
    return requested == expected or SequenceMatcher(None, requested, expected).ratio() > 0.6


def _fmt(quantity: float) -> str:
    return f"{quantity:g}"


@dataclass
class CartLine:
    product: Product
    quantity: float

    @property
    def price(self) -> float:
        return round(self.quantity * self.product.unit_price, 2)

    def as_dict(self) -> dict[str, Any]:
        return {
            "sku": self.product.sku,
            "item_name": self.product.name,
            "item_quantity": f"{_fmt(self.quantity)} {self.product.unit}",
            "unit_price": self.product.unit_price,
            "price": self.price,
            "image_url": self.product.image_url,
        }


class Cart:
    def __init__(self, catalog: ProductMatcher):
        self.catalog = catalog
        self.lines: dict[int, CartLine] = {}

    # -- helpers ------------------------------------------------------------
    def _resolve(self, item_name: str) -> tuple[Product | None, dict[str, Any] | None]:
        match = self.catalog.match(item_name)
        if match.product is not None:
            return match.product, None
        if match.suggestions:
            return None, {
                "status": "ambiguous",
                "message": f"No exact match for '{item_name}'. Did you mean one of these?",
                "suggestions": match.suggestions,
            }
        return None, {"status": "not_found", "message": f"'{item_name}' is not sold in this store."}

    def _set(self, product: Product, quantity: float, unit: str) -> dict[str, Any]:
        if not units_match(unit, product.unit):
            return {
                "status": "unit_mismatch",
                "message": f"{product.name} is sold per {product.unit}, not per {unit}.",
            }
        if quantity <= 0:
            self.lines.pop(product.sku, None)
            return {"status": "ok", "message": f"Removed {product.name} from the cart."}
        if quantity > product.stock:
            return {
                "status": "insufficient_stock",
                "message": (
                    f"Only {_fmt(product.stock)} {product.unit} of {product.name} in stock; "
                    f"requested {_fmt(quantity)}."
                ),
            }
        self.lines[product.sku] = CartLine(product, round(quantity, 2))
        return {
            "status": "ok",
            "message": f"Cart now has {_fmt(quantity)} {product.unit} of {product.name}.",
            "line": self.lines[product.sku].as_dict(),
        }

    def _current(self, product: Product) -> float:
        line = self.lines.get(product.sku)
        return line.quantity if line else 0.0

    # -- operations ---------------------------------------------------------
    def add(self, item_name: str, quantity: float, unit: str) -> dict[str, Any]:
        product, error = self._resolve(item_name)
        if error:
            return error
        return self._set(product, self._current(product) + quantity, unit)

    def change_quantity(
        self, item_name: str, quantity: float, unit: str, action: str
    ) -> dict[str, Any]:
        """``action`` is ``increase``, ``decrease`` or ``set``."""
        product, error = self._resolve(item_name)
        if error:
            return error
        if product.sku not in self.lines:
            return {"status": "not_in_cart", "message": f"{product.name} is not in the cart yet."}
        current = self._current(product)
        target = {
            "increase": current + quantity,
            "decrease": current - quantity,
            "set": quantity,
        }.get(action)
        if target is None:
            return {"status": "error", "message": f"Unknown action '{action}'."}
        return self._set(product, target, unit)

    def remove(self, item_name: str) -> dict[str, Any]:
        product, error = self._resolve(item_name)
        if error:
            return error
        if self.lines.pop(product.sku, None) is None:
            return {"status": "not_in_cart", "message": f"{product.name} is not in the cart."}
        return {"status": "ok", "message": f"Removed {product.name} from the cart."}

    def availability(self, item_name: str) -> dict[str, Any]:
        product, error = self._resolve(item_name)
        if error:
            return error
        if product.stock <= 0:
            return {"status": "out_of_stock", "message": f"{product.name} is out of stock."}
        return {
            "status": "ok",
            "message": (
                f"{product.name} is available at {_fmt(product.unit_price)} dollars per "
                f"{product.unit}."
            ),
        }

    @property
    def total(self) -> float:
        return round(sum(line.price for line in self.lines.values()), 2)

    def summary(self) -> dict[str, Any]:
        return {
            "items": [line.as_dict() for line in self.lines.values()],
            "total_price": f"{_fmt(self.total)} dollars",
        }

    def as_list(self) -> list[dict[str, Any]]:
        return [line.as_dict() for line in self.lines.values()]
