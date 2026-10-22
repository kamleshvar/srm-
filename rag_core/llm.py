"""
rag_core/llm.py
Handles streaming inference via Ollama's /api/generate endpoint.

Model: configurable via OLLAMA_MODEL env var (default: llama3.2)
Host:  configurable via OLLAMA_HOST env var (default: http://localhost:11434)
"""

import requests
import json
import os

# ─────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────

OLLAMA_HOST  = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2")

# ─────────────────────────────────────────────
# Prompt template
# ─────────────────────────────────────────────

SYSTEM_PROMPT = """You are an intelligent assistant for SRM Institute of Science and Technology.
You help students, faculty, and visitors find accurate information about SRM — including admissions, courses, departments, facilities, events, fees, placements, and campus life.

Answer ONLY based on the provided context. If the context does not contain enough information to answer confidently, say so honestly.
Be concise, helpful, and friendly. Format your answer in clear markdown when appropriate.
Never make up information or hallucinate facts about SRM."""


def build_prompt(question: str, context: str) -> str:
    """Combine system instructions, retrieved context, and user question into one prompt."""
    return f"""{SYSTEM_PROMPT}

=== RELEVANT CONTEXT FROM SRM KNOWLEDGE BASE ===
{context if context else "No relevant context found."}
=== END OF CONTEXT ===

Student Question: {question}

Answer:"""


# ─────────────────────────────────────────────
# Streaming generator
# ─────────────────────────────────────────────

def stream_answer(question: str, context: str):
    """
    Generator that yields string tokens from Ollama as they arrive.
    Uses streaming=True so the UI updates in real-time.
    """
    prompt = build_prompt(question, context)

    payload = {
        "model":  OLLAMA_MODEL,
        "prompt": prompt,
        "stream": True,
        "options": {
            "temperature": 0.3,   # Low temp for factual RAG answers
            "top_p": 0.9,
            "num_ctx": 4096,
            "num_predict": 300, # Context window
        }
    }

    try:
        resp = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json=payload,
            stream=True,
            timeout=300
        )
        resp.raise_for_status()

        for line in resp.iter_lines():
            if line:
                try:
                    chunk = json.loads(line.decode("utf-8"))
                    token = chunk.get("response", "")
                    if token:
                        yield token
                    if chunk.get("done", False):
                        break
                except json.JSONDecodeError:
                    continue

    except requests.exceptions.ConnectionError:
        yield "\n\n⚠️ **Error:** Could not connect to Ollama. Make sure it's running (`ollama serve`)."
    except requests.exceptions.Timeout:
        yield "\n\n⚠️ **Error:** Ollama request timed out. Try a shorter question or check server load."
    except Exception as e:
        yield f"\n\n⚠️ **Error:** {str(e)}"


# ─────────────────────────────────────────────
# Health check helper
# ─────────────────────────────────────────────

def check_ollama_alive() -> bool:
    """Returns True if Ollama server is reachable."""
    try:
        r = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=5)
        return r.status_code == 200
    except Exception:
        return False
