# SRM RAG Assistant

A Retrieval-Augmented Generation (RAG) chatbot for SRM Institute, powered by **Ollama** (local LLM) and **ChromaDB** (vector store).

---

## Architecture

```
Browser
  │
  ▼
Flask (app.py)  ──► /ask  ──► retriever.py (ChromaDB)  ──► top-5 chunks
                          └──► llm.py (Ollama /api/generate)  ──► SSE stream
                          
ingest.py  ──► sentence-transformers embed  ──► ChromaDB persist
```

---

## Quick Start (2-hour setup)

### 1. Clone / copy the project
```bash
cd ~
# copy this folder to your Pi or server
```

### 2. Create virtual environment
```bash
cd srm-rag
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Make sure Ollama is running
```bash
ollama serve          # if not already running as a service
ollama pull llama3.2  # pull the model (or whatever model you want)
```

### 4. Drop your scraped data into ./data/
Supported formats:
- **JSON**: `[{"title": "...", "content": "...", "url": "..."}]`
- **CSV**: columns named `title`, `content`, `url`
- **TXT / MD**: plain text, auto-chunked

### 5. Ingest data into ChromaDB
```bash
python ingest.py          # ingests all files in ./data/
python ingest.py --reset  # wipe and re-ingest (if re-scraping)
```

### 6. Run the app
```bash
# Development
python app.py

# Production (Gunicorn)
gunicorn -c gunicorn.conf.py app:app
```

Visit: `http://localhost:5000`

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `llama3.2` | Model name (must be pulled) |
| `CHROMA_PATH` | `./chroma_db` | Path to persist vector DB |

---

## Systemd (production)

```bash
sudo cp srm-rag.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable srm-rag
sudo systemctl start srm-rag
```

---

## Cloudflare Tunnel

Add a public hostname in your Cloudflare Tunnel dashboard:
- Service: `http://localhost:5000`
- Domain: `srm.gaiasentinel.online` (or whatever subdomain)

---

## Adding More Data

Just drop new `.json` / `.csv` / `.txt` files into `./data/` and re-run:
```bash
python ingest.py          # adds new chunks (keeps existing)
python ingest.py --reset  # full re-ingest
```
