"""
rag_core/retriever.py
Handles vector store operations using ChromaDB + sentence-transformers.

Collection: "srm_docs"
Embedding model: all-MiniLM-L6-v2 (fast, good quality, runs locally)
"""

import chromadb
from chromadb.utils import embedding_functions
import os

# ─────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────

CHROMA_PATH = os.environ.get("CHROMA_PATH", "/opt/api/srm/chroma_db")
COLLECTION    = "srm_docs"
EMBED_MODEL   = "all-MiniLM-L6-v2"   # downloaded once, cached

# ─────────────────────────────────────────────
# Singleton client + collection
# ─────────────────────────────────────────────

_client     = None
_collection = None

def _get_collection():
    global _client, _collection
    if _collection is not None:
        return _collection

    _client = chromadb.PersistentClient(path=CHROMA_PATH)

    emb_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBED_MODEL
    )

    _collection = _client.get_or_create_collection(
        name=COLLECTION,
        embedding_function=emb_fn,
        metadata={"hnsw:space": "cosine"}
    )
    return _collection


# ─────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────

def get_relevant_chunks(query: str, top_k: int = 5) -> list[dict]:
    """
    Retrieve top_k most relevant document chunks for a given query.

    Returns a list of dicts:
        [
            {
                "id":       str,
                "text":     str,
                "source":   str,
                "score":    float   (cosine distance, lower = more relevant)
            },
            ...
        ]
    """
    col = _get_collection()

    # Guard: if collection is empty return empty list
    count = col.count()
    if count == 0:
        return []

    results = col.query(
        query_texts=[query],
        n_results=min(top_k, count),
        include=["documents", "metadatas", "distances"]
    )

    chunks = []
    docs      = results["documents"][0]
    metas     = results["metadatas"][0]
    distances = results["distances"][0]
    ids       = results["ids"][0]

    for i, doc in enumerate(docs):
        chunks.append({
            "id":     ids[i],
            "text":   doc,
            "source": metas[i].get("source", "Unknown"),
            "title":  metas[i].get("title", ""),
            "score":  round(distances[i], 4),
        })

    return chunks


def collection_count() -> int:
    """Return number of chunks currently in the vector store."""
    return _get_collection().count()
