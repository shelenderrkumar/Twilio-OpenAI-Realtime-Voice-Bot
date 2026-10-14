import pytest

from tests.conftest import FakeCatalog
from voicebot.services.cart import Cart, normalize_unit, units_match


@pytest.fixture
def cart():
    return Cart(FakeCatalog(suggestions={"tomatoes": ["tomato", "potato"]}))


def test_add_accumulates_and_prices(cart):
    assert cart.add("potato", 2, "kg")["status"] == "ok"
    assert cart.add("potato", 1, "kilograms")["status"] == "ok"
    assert cart.as_list() == [
        {
            "sku": 3,
            "item_name": "potato",
            "item_quantity": "3 kg",
            "unit_price": 1.5,
            "price": 4.5,
            "image_url": "",
        }
    ]
    assert cart.summary()["total_price"] == "4.5 dollars"


def test_add_rejects_more_than_stock(cart):
    result = cart.add("potato", 6, "kg")
    assert result["status"] == "insufficient_stock"
    assert cart.lines == {}


def test_add_rejects_wrong_unit(cart):
    assert cart.add("eggs", 2, "kg")["status"] == "unit_mismatch"


def test_unknown_and_ambiguous_items(cart):
    assert cart.add("caviar", 1, "unit")["status"] == "not_found"
    result = cart.add("tomatoes", 1, "kg")
    assert result["status"] == "ambiguous"
    assert result["suggestions"] == ["tomato", "potato"]


@pytest.mark.parametrize(
    ("action", "quantity", "expected"),
    [("increase", 1, "3 kg"), ("decrease", 1, "1 kg"), ("set", 4, "4 kg")],
)
def test_change_quantity(cart, action, quantity, expected):
    cart.add("potato", 2, "kg")
    assert cart.change_quantity("potato", quantity, "kg", action)["status"] == "ok"
    assert cart.as_list()[0]["item_quantity"] == expected


def test_decrease_to_zero_removes_line(cart):
    cart.add("potato", 2, "kg")
    cart.change_quantity("potato", 5, "kg", "decrease")
    assert cart.lines == {}


def test_change_quantity_requires_item_in_cart(cart):
    assert cart.change_quantity("eggs", 1, "dozen", "increase")["status"] == "not_in_cart"


def test_remove(cart):
    cart.add("eggs", 1, "dozen")
    assert cart.remove("eggs")["status"] == "ok"
    assert cart.remove("eggs")["status"] == "not_in_cart"


def test_availability(cart):
    assert cart.availability("potato")["status"] == "ok"
    assert cart.availability("hazelnut spread")["status"] == "out_of_stock"


def test_unit_normalization():
    assert normalize_unit(" Kilos ") == "kg"
    assert units_match("litres", "litre")
    assert not units_match("kg", "dozen")
