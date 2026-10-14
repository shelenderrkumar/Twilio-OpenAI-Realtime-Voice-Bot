"""Pre-build the FAISS indexes (otherwise they are built lazily on the first call).

python scripts/build_indexes.py
"""

import logging

from voicebot.config import get_settings
from voicebot.dependencies import Dependencies

logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    deps = Dependencies(get_settings())
    print(f"Catalog: {len(deps.catalog.products)} products indexed")
    print(f"Knowledge base: {deps.knowledge_base.search('delivery')[0]['source']} ... ready")
