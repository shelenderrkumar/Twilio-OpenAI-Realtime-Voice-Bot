import json

import pytest

from voicebot.profiles import build_profile
from voicebot.realtime.agent import tool_definition


def tools_of(profile):
    return {t.name: t for t in profile.tools}


async def test_grocery_checkout_flow(deps):
    profile = build_profile("grocery", deps)
    tools = tools_of(profile)

    assert (
        await tools["add_to_cart"].ainvoke(
            {"item_name": "potato", "quantity": 2, "unit_of_measure": "kg"}
        )
    )["status"] == "ok"
    assert profile.state_snapshot()[0]["item_name"] == "potato"

    first = await tools["get_promotion"].ainvoke({})
    again = await tools["get_promotion"].ainvoke({})
    assert first["status"] == "ok" and again["status"] == "already_offered"

    order = await tools["place_order"].ainvoke(
        {"address": "House 1", "mobile_number": "03001234567"}
    )
    tracking = await tools["track_order"].ainvoke({"tracking_number": order["tracking_number"]})
    assert tracking["shipment_status"] == "Order is being prepared"

    complaint = await tools["submit_complaint"].ainvoke(
        {
            "tracking_number": order["tracking_number"],
            "complaint": "Late",
            "email": "me@example.com",
        }
    )
    assert complaint["status"] == "ok"
    sent = deps.notifier.sent[0]
    assert sent["to"] == deps.settings.support_email and "me@example.com" in sent["cc"]


async def test_each_call_gets_its_own_cart(deps):
    first, second = build_profile("grocery", deps), build_profile("grocery", deps)
    await tools_of(first)["add_to_cart"].ainvoke(
        {"item_name": "eggs", "quantity": 1, "unit_of_measure": "dozen"}
    )
    assert second.state_snapshot() == []


async def test_place_order_requires_items(deps):
    result = await tools_of(build_profile("grocery", deps))["place_order"].ainvoke(
        {"address": "x", "mobile_number": "1"}
    )
    assert result["status"] == "empty_cart"


@pytest.mark.parametrize("name", ["grocery", "logistics"])
def test_tool_definitions_are_valid_realtime_schemas(deps, name):
    for tool in build_profile(name, deps).tools:
        definition = tool_definition(tool)
        assert definition["type"] == "function" and definition["description"]
        params = definition["parameters"]
        assert params["type"] == "object"
        assert set(params.get("required", [])) <= set(params["properties"])
        json.dumps(definition)


def test_change_quantity_schema_constrains_action(deps):
    definition = tool_definition(tools_of(build_profile("grocery", deps))["change_item_quantity"])
    assert definition["parameters"]["properties"]["action"]["enum"] == [
        "increase",
        "decrease",
        "set",
    ]


def test_unknown_profile(deps):
    with pytest.raises(ValueError):
        build_profile("pizza", deps)
