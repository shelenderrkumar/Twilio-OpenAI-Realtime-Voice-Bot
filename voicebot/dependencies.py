"""Shared, lazily-built services (indexes are loaded once per process, not per call)."""

from functools import cached_property

from voicebot.config import Settings
from voicebot.services.catalog import SemanticCatalog, load_products
from voicebot.services.knowledge_base import KnowledgeBase
from voicebot.services.notifier import build_notifier
from voicebot.services.orders import OrderStore
from voicebot.services.tracking import TrackingService


class Dependencies:
    def __init__(self, settings: Settings):
        self.settings = settings

    @cached_property
    def embeddings(self):
        from langchain_openai import OpenAIEmbeddings

        return OpenAIEmbeddings(
            model=self.settings.embedding_model, api_key=self.settings.openai_api_key
        )

    @cached_property
    def catalog(self) -> SemanticCatalog:
        return SemanticCatalog(
            load_products(self.settings.catalog_csv),
            self.embeddings,
            self.settings.catalog_index_dir,
        )

    @cached_property
    def knowledge_base(self) -> KnowledgeBase:
        return KnowledgeBase(
            self.settings.knowledge_base_dir, self.settings.knowledge_index_dir, self.embeddings
        )

    @cached_property
    def orders(self) -> OrderStore:
        return OrderStore(self.settings.orders_csv)

    @cached_property
    def tracking(self) -> TrackingService:
        return TrackingService(self.orders, self.settings.tracking_api_url)

    @cached_property
    def notifier(self):
        return build_notifier(self.settings)

    @cached_property
    def web_search(self):
        if self.settings.tavily_api_key is None:
            return None
        from langchain_community.tools import TavilySearchResults

        return TavilySearchResults(
            max_results=3, api_key=self.settings.tavily_api_key.get_secret_value()
        )
