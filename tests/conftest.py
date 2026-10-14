from pathlib import Path

import pytest
from langchain_core.embeddings import DeterministicFakeEmbedding

from voicebot.config import Settings
from voicebot.services.catalog import Match, Product
from voicebot.services.notifier import LogNotifier
from voicebot.services.orders import OrderStore
from voicebot.services.tracking import TrackingService

DATA = Path(__file__).resolve().parent.parent / "data"

POTATO = Product(sku=3, name="potato", stock=5, unit="kg", unit_price=1.5)
EGGS = Product(sku=13, name="eggs", stock=150, unit="dozen", unit_price=1)
SOLD_OUT = Product(sku=26, name="hazelnut spread", stock=0, unit="unit", unit_price=2)


class FakeCatalog:
    """Exact-name catalog standing in for the embedding-based one."""

    def __init__(self, products=(POTATO, EGGS, SOLD_OUT), suggestions=None):
        self.products = {p.name: p for p in products}
        self.suggestions = suggestions or {}

    def match(self, query: str) -> Match:
        if query in self.products:
            return Match(product=self.products[query])
        return Match(suggestions=self.suggestions.get(query, []))


@pytest.fixture
def embeddings():
    return DeterministicFakeEmbedding(size=64)


@pytest.fixture
def settings(tmp_path):
    return Settings(
        _env_file=None,
        openai_api_key="test-key",
        orders_csv=tmp_path / "orders.csv",
        knowledge_index_dir=tmp_path / "kb_index",
        catalog_index_dir=tmp_path / "catalog_index",
        gmail_credentials_file=tmp_path / "missing.json",
    )


class FakeDeps:
    def __init__(self, settings, catalog=None, knowledge_base=None):
        self.settings = settings
        self.catalog = catalog or FakeCatalog()
        self.knowledge_base = knowledge_base
        self.orders = OrderStore(settings.orders_csv)
        self.tracking = TrackingService(self.orders)
        self.notifier = LogNotifier()
        self.web_search = None


@pytest.fixture
def deps(settings):
    return FakeDeps(settings)
