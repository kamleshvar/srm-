"""
ingest.py
One-time (or re-runnable) script to load your scraped SRM data
into ChromaDB with sentence-transformer embeddings.

Supports:
    - JSON  files  (list of objects OR single object)
    - CSV   files
    - TXT   files  (plain text, split into chunks)

Usage:
    python ingest.py                    # ingest all files in ./data/
    python ingest.py --reset            # wipe collection and re-ingest
    python ingest.py --file data/x.json # ingest a single file

Place your scraped data files in the ./data/ directory.
Expected JSON format (any of these work):
    [{"title": "...", "content": "...", "url": "..."}, ...]
    {"title": "...", "content": "..."}
    [{"question": "...", "answer": "..."}]   ← FAQ format
"""

import argparse
import json
import csv
import os
import uuid
import sys
import chromadb
from chromadb.utils import embedding_functions

# ─────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────

CHROMA_PATH  = os.environ.get("CHROMA_PATH", "./chroma_db")
COLLECTION   = "srm_docs"
EMBED_MODEL  = "all-MiniLM-L6-v2"
DATA_DIR     = "./data"

# Chunk size in characters (for plain text files)
CHUNK_SIZE   = 800
CHUNK_OVERLAP = 100

# ─────────────────────────────────────────────
# Chunker
# ─────────────────────────────────────────────

def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split long text into overlapping chunks."""
    if len(text) <= size:
        return [text.strip()] if text.strip() else []

    chunks = []
    start  = 0
    while start < len(text):
        end   = start + size
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end - overlap

    return chunks


# ─────────────────────────────────────────────
# Loaders
# ─────────────────────────────────────────────

def flatten_nested(obj, parent_key="", sep=" > ") -> list[dict]:
    """
    Recursively walk any nested JSON (dicts, lists, primitives)
    and convert every meaningful leaf/section into a text chunk.
    Works for deeply nested structures like the SRM institution profile.
    """
    records = []

    if isinstance(obj, dict):
        # Build a readable text block from this dict's key-value pairs
        lines = []
        for k, v in obj.items():
            label = k.replace("_", " ").title()
            if isinstance(v, (str, int, float, bool)):
                lines.append(f"{label}: {v}")
            elif isinstance(v, list):
                # Flatten simple lists inline
                simple = [str(i) for i in v if isinstance(i, (str, int, float))]
                if simple:
                    lines.append(f"{label}: {', '.join(simple)}")
                # Recurse into complex list items
                for i, item in enumerate(v):
                    if isinstance(item, (dict, list)):
                        child_key = f"{parent_key}{sep}{label}[{i}]" if parent_key else f"{label}[{i}]"
                        records.extend(flatten_nested(item, child_key, sep))
            elif isinstance(v, dict):
                child_key = f"{parent_key}{sep}{label}" if parent_key else label
                records.extend(flatten_nested(v, child_key, sep))

        if lines:
            text  = (f"Section: {parent_key}\n\n" if parent_key else "") + "\n".join(lines)
            title = parent_key.split(sep)[-1] if parent_key else "SRM Info"
            for chunk in chunk_text(text):
                records.append({
                    "text":   chunk,
                    "source": "srm_data",
                    "title":  title,
                })

    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            child_key = f"{parent_key}[{i}]" if parent_key else f"Item {i}"
            records.extend(flatten_nested(item, child_key, sep))

    return records


def load_json(path: str) -> list[dict]:
    """
    Load JSON file. Handles:
        - Flat list: [{"title": ..., "content": ..., "url": ...}]
        - FAQ format: [{"question": ..., "answer": ...}]
        - Deeply nested dicts (e.g. SRM institution profile)
    Returns list of {text, source, title}
    """
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    records = []
    items   = raw if isinstance(raw, list) else [raw]

    for item in items:
        if not isinstance(item, dict):
            continue

        # ── FAQ format ──────────────────────────
        if "question" in item and "answer" in item:
            text = "Q: {}\nA: {}".format(item["question"], item["answer"])
            records.append({
                "text":   text,
                "source": item.get("url", path),
                "title":  item.get("question", "FAQ"),
            })
            continue

        # ── Flat content format ──────────────────
        content = (
            item.get("content")
            or item.get("text")
            or item.get("body")
            or item.get("description")
            or ""
        )
        if content and isinstance(content, str) and content.strip():
            title  = item.get("title") or item.get("heading") or os.path.basename(path)
            source = item.get("url") or item.get("source") or path
            for chunk in chunk_text(content):
                records.append({
                    "text":   "{}\n\n{}".format(title, chunk) if title else chunk,
                    "source": source,
                    "title":  title,
                })
            continue

        # ── Deeply nested / institution profile ──
        # No flat content key found — recurse into the whole object
        records.extend(flatten_nested(item, parent_key="", sep=" > "))

    return records


def load_csv(path: str) -> list[dict]:
    """Load CSV. Auto-detects content columns."""
    records = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Try to find content column
            content_keys = ["content", "text", "body", "description", "answer", "info"]
            title_keys   = ["title", "heading", "question", "name"]

            content = ""
            title   = ""

            for k in content_keys:
                if k in row and row[k].strip():
                    content = row[k].strip()
                    break

            for k in title_keys:
                if k in row and row[k].strip():
                    title = row[k].strip()
                    break

            # Fallback: concatenate all columns
            if not content:
                content = " | ".join(f"{k}: {v}" for k, v in row.items() if v.strip())

            source = row.get("url", path)

            for chunk in chunk_text(content):
                records.append({
                    "text":   f"{title}\n\n{chunk}" if title else chunk,
                    "source": source,
                    "title":  title,
                })

    return records


def load_txt(path: str) -> list[dict]:
    """Load plain text file and chunk it."""
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    records = []
    for chunk in chunk_text(text):
        records.append({
            "text":   chunk,
            "source": path,
            "title":  os.path.basename(path),
        })
    return records


# ─────────────────────────────────────────────
# Ingestor
# ─────────────────────────────────────────────

def get_collection(reset: bool = False):
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    emb_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBED_MODEL
    )

    if reset:
        try:
            client.delete_collection(COLLECTION)
            print(f"[ingest] ✓ Deleted existing collection '{COLLECTION}'")
        except Exception:
            pass

    col = client.get_or_create_collection(
        name=COLLECTION,
        embedding_function=emb_fn,
        metadata={"hnsw:space": "cosine"}
    )
    return col


def ingest_records(col, records: list[dict], batch_size: int = 50):
    """Batch-upsert records into ChromaDB."""
    total   = len(records)
    ingested = 0

    for i in range(0, total, batch_size):
        batch = records[i : i + batch_size]

        ids       = [str(uuid.uuid4()) for _ in batch]
        documents = [r["text"]   for r in batch]
        metadatas = [{"source": r["source"], "title": r["title"]} for r in batch]

        col.upsert(ids=ids, documents=documents, metadatas=metadatas)
        ingested += len(batch)
        print(f"[ingest] Progress: {ingested}/{total} chunks embedded...")

    return ingested


def ingest_file(col, path: str) -> int:
    """Load and ingest a single file. Returns number of chunks added."""
    ext = os.path.splitext(path)[1].lower()

    print(f"[ingest] Loading {path} ...")

    if ext == ".json":
        records = load_json(path)
    elif ext == ".csv":
        records = load_csv(path)
    elif ext in (".txt", ".md"):
        records = load_txt(path)
    else:
        print(f"[ingest] ⚠ Unsupported file type: {ext} — skipping")
        return 0

    if not records:
        print(f"[ingest] ⚠ No records found in {path}")
        return 0

    print(f"[ingest] Found {len(records)} chunks in {os.path.basename(path)}")
    return ingest_records(col, records)


# ─────────────────────────────────────────────
# CLI entrypoint
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Ingest SRM scraped data into ChromaDB")
    parser.add_argument("--reset", action="store_true", help="Wipe and re-ingest")
    parser.add_argument("--file",  type=str, default=None, help="Ingest a specific file")
    args = parser.parse_args()

    col   = get_collection(reset=args.reset)
    total = 0

    if args.file:
        total += ingest_file(col, args.file)
    else:
        if not os.path.isdir(DATA_DIR):
            print(f"[ingest] ✗ Data directory '{DATA_DIR}' not found. Create it and add your scraped files.")
            sys.exit(1)

        files = [
            os.path.join(DATA_DIR, f)
            for f in sorted(os.listdir(DATA_DIR))
            if f.lower().endswith((".json", ".csv", ".txt", ".md"))
        ]

        if not files:
            print(f"[ingest] ✗ No supported files found in '{DATA_DIR}' (looking for .json, .csv, .txt, .md)")
            sys.exit(1)

        for path in files:
            total += ingest_file(col, path)

    print(f"\n[ingest] ✅ Done! {total} chunks ingested.")
    print(f"[ingest] Total chunks in collection: {col.count()}")


if __name__ == "__main__":
    main()