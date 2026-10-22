# gunicorn.conf.py
# Production config for SRM RAG

bind       = "0.0.0.0:5000"
workers    = 1          # Keep at 1 for Ollama — it's a single GPU
worker_class = "sync"   # sync is fine; no WebSockets needed
threads    = 4
timeout    = 180        # Ollama can take time for long answers
keepalive  = 5
loglevel   = "info"
accesslog  = "-"
errorlog   = "-"
