"""Retrieval-augmented answers over a folder of Markdown / text documents."""

import logging
from pathlib import Path

from langchain_core.documents import Document

logger = logging.getLogger(__name__)


def load_documents(source_dir: Path) -> list[Document]:
    docs = []
    for path in sorted(source_dir.rglob("*")):
        if path.suffix.lower() in {".md", ".txt"} and path.is_file():
            docs.append(
                Document(
                    page_content=path.read_text(encoding="utf-8"), metadata={"source": path.name}
                )
            )
    return docs


def split_documents(
    docs: list[Document], chunk_size: int = 800, overlap: int = 100
) -> list[Document]:
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=overlap)
    return splitter.split_documents(docs)


class KnowledgeBase:
    def __init__(self, source_dir: Path, index_dir: Path, embeddings, k: int = 4):
        from langchain_community.vectorstores import FAISS

        self.k = k
        if (index_dir / "index.faiss").exists():
            # Safe: the index is produced locally by `build`, never downloaded.
            self._index = FAISS.load_local(
                str(index_dir), embeddings, allow_dangerous_deserialization=True
            )
        else:
            chunks = split_documents(load_documents(source_dir))
            if not chunks:
                raise FileNotFoundError(f"No .md/.txt documents found in {source_dir}")
            self._index = FAISS.from_documents(chunks, embeddings)
            self._index.save_local(str(index_dir))
            logger.info("Indexed %d chunks from %s", len(chunks), source_dir)

    def search(self, query: str) -> list[dict[str, str]]:
        return [
            {"source": doc.metadata.get("source", ""), "content": doc.page_content}
            for doc in self._index.similarity_search(query, k=self.k)
        ]
