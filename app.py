import os
os.environ["HF_HOME"] = "/opt/api/srm/hf_cache"
os.environ["TRANSFORMERS_CACHE"] = "/opt/api/srm/hf_cache"
"""
SRM RAG - Main Flask Application
Serves the chat UI and exposes the /ask API endpoint.
Auto-starts Ollama if not already running (Ubuntu/Linux).
"""

from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from rag_core.retriever import get_relevant_chunks
from rag_core.llm import stream_answer
import json
import subprocess
import time
import requests
import os

# ─────────────────────────────────────────────
# Auto-start Ollama
# ─────────────────────────────────────────────

OLLAMA_HOST  = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:1b")

def is_ollama_running():
    try:
        r = requests.get(OLLAMA_HOST, timeout=3)
        return r.status_code == 200
    except Exception:
        return False

def start_ollama():
    if is_ollama_running():
        print("[SRM RAG] Ollama already running.")
        return

    print("[SRM RAG] Starting Ollama in background...")
    subprocess.Popen(
        ["ollama", "serve"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True
    )

    print("[SRM RAG] Waiting for Ollama", end="", flush=True)
    for _ in range(30):
        time.sleep(1)
        print(".", end="", flush=True)
        if is_ollama_running():
            print(" ready!")
            return

    print("\n[SRM RAG] WARNING: Ollama did not respond in 30s. Check manually.")

start_ollama()

# ─────────────────────────────────────────────
# Flask app
# ─────────────────────────────────────────────

app = Flask(__name__)

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/ask", methods=["POST"])
def ask():
    data     = request.get_json(force=True)
    question = data.get("question", "").strip()

    if not question:
        return jsonify({"error": "question is required"}), 400

    chunks  = get_relevant_chunks(question, top_k=5)
    context = "\n\n---\n\n".join([c["text"] for c in chunks])

    def generate():
        for token in stream_answer(question, context):
            yield "data: " + json.dumps({"token": token}) + "\n\n"
        yield "data: [DONE]\n\n"

    return Response(
        stream_with_context(generate()),
        content_type="text/event-stream",
        headers={
            "Cache-Control":     "no-cache",
            "X-Accel-Buffering": "no",
        }
    )


@app.route("/sources", methods=["POST"])
def sources():
    data     = request.get_json(force=True)
    question = data.get("question", "").strip()

    if not question:
        return jsonify({"error": "question is required"}), 400

    chunks = get_relevant_chunks(question, top_k=5)
    return jsonify({"sources": chunks})


@app.route("/health")
def health():
    ollama_ok = is_ollama_running()
    return jsonify({
        "status":  "ok",
        "ollama":  "running" if ollama_ok else "down",
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5011, debug=True)
