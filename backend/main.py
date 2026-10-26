
from fastapi import FastAPI
from datetime import datetime, timezone

app = FastAPI(title="KPSS Radar API", version="0.1.0")

@app.get("/api/health")
def health():
    return {
        "ok": True,
        "service": "kpss-radar",
        "time": datetime.now(timezone.utc).isoformat()
    }

@app.get("/api/report")
def report():
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "starter_not_connected",
        "items": []
    }
  
