"""Product catalog with semantic name matching.

Spoken product names are noisy ("peanut butter", "chunky peanut butter", "PB"), so
items are matched by embedding similarity instead of exact string lookup:

* score >= ``exact_threshold``    -> confident match
* score >= ``suggest_threshold``  -> ambiguous, offer the closest products instead
* otherwise                       -> not sold here
"""

import csv
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Product:
    sku: int
    name: str
    stock: float
    unit: str
    unit_price: float
    image_url: str = ""


@dataclass
class Match:
    product: Product | None = None
    suggestions: list[str] = field(default_factory=list)


class ProductMatcher(Protocol):
    def match(self, query: str) -> Match: ...


def load_products(path: Path) -> list[Product]:
    with open(path, newline="", encoding="utf-8") as f:
        return [
            Product(
                sku=int(row["sku"]),
                name=row["product_name"].strip(),
                stock=float(row["quantity_in_stock"]),
                unit=row["unit_to_measure"].strip().lower(),
                unit_price=float(row["price_per_unit"]),
                image_url=row.get("image_uri", ""),
            )
            for row in csv.DictReader(f)
        ]


class SemanticCatalog:
    """FAISS index over product names. Built once from the CSV, then cached on disk."""

    def __init__(
        self,
        products: list[Product],
        embeddings,
        index_dir: Path | None = None,
        exact_threshold: float = 0.85,
        suggest_threshold: float = 0.80,
    ):
        from langchain_community.vectorstores import FAISS

        self.products = {p.sku: p for p in products}
        self.exact_threshold = exact_threshold
        self.suggest_threshold = suggest_threshold

        if index_dir is not None and (index_dir / "index.faiss").exists():
            # Safe: the index is produced locally by this class, never downloaded.
            self._index = FAISS.load_local(
                str(index_dir), embeddings, allow_dangerous_deserialization=True, normalize_L2=True
            )
        else:
            self._index = FAISS.from_texts(
                [p.name for p in products],
                embeddings,
                metadatas=[{"sku": p.sku} for p in products],
                # Unit vectors keep relevance scores in [0, 1] for any embedding model.
                normalize_L2=True,
            )
            if index_dir is not None:
                self._index.save_local(str(index_dir))
                logger.info("Built catalog index at %s", index_dir)

    def match(self, query: str) -> Match:
        hits = self._index.similarity_search_with_relevance_scores(query, k=3)
        if not hits:
            return Match()
        best_doc, best_score = hits[0]
        if best_score >= self.exact_threshold:
            return Match(product=self.products[best_doc.metadata["sku"]])
        if best_score >= self.suggest_threshold:
            return Match(suggestions=[self.products[d.metadata["sku"]].name for d, _ in hits])
        return Match()
