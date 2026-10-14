"""Voice grocery-ordering agent: browse, build a cart, check out, track and complain."""

import random
from typing import Literal

from langchain_core.tools import tool

from voicebot.profiles.base import AgentProfile
from voicebot.services.cart import Cart

PROMOTED_PRODUCTS = ["apple", "banana", "oranges", "mangoes"]

INSTRUCTIONS = """
You are a warm, upbeat voice assistant for an online grocery store. Keep replies short
and natural - you are speaking, not writing. Match the caller's emotion: be cheerful by
default and calm and empathetic when they complain. Politely decline anything that is
not about groceries, orders or deliveries. Always use a tool rather than guessing.

Cart:
- New item -> `add_to_cart`. More / less / exactly N of an item already in the cart ->
  `change_item_quantity` with action increase / decrease / set. Drop an item entirely ->
  `remove_from_cart`. Availability or price questions -> `check_item_availability`.
  Cart contents or total -> `get_cart_summary`.
- If a tool returns suggestions, read them out and ask which one the caller meant.
- Units: 1 dozen = 12 items (6 items = 0.5 dozen); 1 kg = 1000 g; 1 litre = 1000 ml.

Checkout, in this order:
1. When the caller says they are done, call `get_promotion` once and offer the deal.
2. Collect the delivery address and mobile number.
3. Call `place_order`, then read the tracking number back digit by digit
   ("one, two, three ...").

After the order:
- Tracking: collect the tracking number (join digits exactly as spoken) and call
  `track_order`.
- Complaints: collect the tracking number, the complaint and the caller's e-mail, then
  call `submit_complaint` and respond with empathy.
""".strip()


def build_grocery_profile(deps) -> AgentProfile:
    cart = Cart(deps.catalog)
    promotion_offered = False

    @tool
    def add_to_cart(item_name: str, quantity: float, unit_of_measure: str) -> dict:
        """Add a grocery item to the cart, e.g. 2 kg of potato or 1 dozen eggs."""
        return cart.add(item_name, quantity, unit_of_measure)

    @tool
    def change_item_quantity(
        item_name: str,
        quantity: float,
        unit_of_measure: str,
        action: Literal["increase", "decrease", "set"],
    ) -> dict:
        """Change the quantity of an item already in the cart. `increase` / `decrease`
        adjust by `quantity`; `set` makes `quantity` the new total."""
        return cart.change_quantity(item_name, quantity, unit_of_measure, action)

    @tool
    def remove_from_cart(item_name: str) -> dict:
        """Remove an item from the cart completely."""
        return cart.remove(item_name)

    @tool
    def check_item_availability(item_name: str) -> dict:
        """Check whether the store sells an item, whether it is in stock and its price."""
        return cart.availability(item_name)

    @tool
    def get_cart_summary() -> dict:
        """List every item in the cart with the total price."""
        return cart.summary()

    @tool
    def get_promotion() -> dict:
        """Get today's promotional offer. Offer it once, when the caller finishes shopping."""
        nonlocal promotion_offered
        if promotion_offered:
            return {"status": "already_offered", "message": "The promotion was already offered."}
        promotion_offered = True
        product = random.choice(PROMOTED_PRODUCTS)
        return {"status": "ok", "message": f"Exclusive discount today on {product}!"}

    @tool
    def place_order(address: str, mobile_number: str) -> dict:
        """Place the order for the current cart and return its tracking number."""
        if not cart.lines:
            return {"status": "empty_cart", "message": "The cart is empty."}
        number = deps.orders.place(address, mobile_number, cart.as_list(), cart.total)
        return {
            "status": "ok",
            "tracking_number": number,
            "message": f"Order placed for {cart.total:g} dollars; delivery within 30 minutes.",
        }

    @tool
    async def track_order(tracking_number: str) -> dict:
        """Look up the delivery status of an order by tracking number."""
        return await deps.tracking.status(tracking_number)

    @tool
    def submit_complaint(tracking_number: str, complaint: str, email: str) -> dict:
        """Forward a customer complaint about an order to the support team."""
        order = deps.orders.get(tracking_number)
        if order is None:
            return {"status": "not_found", "message": f"No order found for {tracking_number}."}
        body = (
            "A complaint was received through the grocery voice assistant.\n\n"
            f"Complaint:       {complaint}\n"
            f"Order:           {order['tracking_number']} ({order['items']})\n"
            f"Customer e-mail: {email}\n"
            f"Delivery address:{order['address']}\n"
            f"Mobile number:   {order['mobile_number']}\n"
        )
        deps.notifier.send(
            to=deps.settings.support_email,
            subject=f"Voice assistant complaint - order {order['tracking_number']}",
            body=body,
            cc=[email, *deps.settings.complaint_cc],
        )
        return {"status": "ok", "message": "Complaint submitted; support will e-mail you."}

    return AgentProfile(
        name="grocery",
        instructions=INSTRUCTIONS,
        tools=[
            add_to_cart,
            change_item_quantity,
            remove_from_cart,
            check_item_availability,
            get_cart_summary,
            get_promotion,
            place_order,
            track_order,
            submit_complaint,
        ],
        state_snapshot=cart.as_list,
    )
