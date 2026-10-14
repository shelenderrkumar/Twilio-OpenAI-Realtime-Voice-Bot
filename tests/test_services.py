import httpx

from tests.conftest import DATA
from voicebot.services.catalog import SemanticCatalog, load_products
from voicebot.services.knowledge_base import KnowledgeBase, load_documents
from voicebot.services.orders import OrderStore
from voicebot.services.tracking import TrackingService, normalize_tracking_number


def test_order_store_roundtrip(tmp_path):
    store = OrderStore(tmp_path / "orders.csv")
    number = store.place(
        "House 1", "03001234567", [{"item_quantity": "2 kg", "item_name": "potato"}], 3
    )
    order = store.get(number)
    assert order["mobile_number"] == "03001234567"  # leading zero preserved
    assert order["items"] == "2 kg potato"
    assert store.get(" ".join(number)) == order  # digits spoken one by one


def test_normalize_tracking_number():
    assert normalize_tracking_number("3 9 7-148") == "397148"


async def test_tracking_from_local_orders():
    service = TrackingService(OrderStore(DATA / "orders.csv"))
    assert (await service.status("397148"))["shipment_status"] == "Delivered"
    assert (await service.status("000000"))["status"] == "not_found"


async def test_tracking_api_never_exposes_personal_data(tmp_path):
    payload = {
        "tracking_status": "In transit",
        "shipper_city": "Lahore",
        "consignee_name": "Ali",
        "consignee_phone": "0300",
        "tracking_history": [{"status": "Arrived at hub", "date_time": "2024-10-25 10:00"}],
    }
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    service = TrackingService(
        OrderStore(tmp_path / "o.csv"), "https://carrier.test/track", transport=transport
    )
    result = await service.status("10334024")
    assert result["shipment_status"] == "Arrived at hub"
    assert "Ali" not in str(result) and "0300" not in str(result)


async def test_tracking_api_failure_is_graceful(tmp_path):
    transport = httpx.MockTransport(lambda request: httpx.Response(500))
    service = TrackingService(
        OrderStore(tmp_path / "o.csv"), "https://carrier.test/track", transport=transport
    )
    assert (await service.status("1"))["status"] == "unavailable"


def test_catalog_csv_is_complete():
    products = load_products(DATA / "grocery_catalog.csv")
    assert len(products) == 51
    assert len({p.sku for p in products}) == 51


def test_semantic_catalog_exact_match_and_cache(tmp_path, embeddings):
    products = load_products(DATA / "grocery_catalog.csv")
    catalog = SemanticCatalog(products, embeddings, tmp_path / "idx")
    assert catalog.match("banana").product.name == "banana"
    reloaded = SemanticCatalog(products, embeddings, tmp_path / "idx")  # loads from disk
    assert reloaded.match("punjab atta").product.sku == 49


def test_knowledge_base_indexes_bundled_docs(tmp_path, embeddings):
    assert len(load_documents(DATA / "knowledge_base")) == 3
    kb = KnowledgeBase(DATA / "knowledge_base", tmp_path / "kb", embeddings, k=2)
    hits = kb.search("volumetric weight")
    assert len(hits) == 2 and all(h["source"].endswith(".md") for h in hits)
