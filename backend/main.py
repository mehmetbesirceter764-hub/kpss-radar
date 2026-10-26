
from fastapi import FastAPI
from datetime import datetime, timezone
from scanner import scan

app = FastAPI(title="KPSS Radar API", version="0.2.0")

@app.get("/api/health")
def health():
    return {
        "ok": True,
        "service": "kpss-radar",
        "time": datetime.now(timezone.utc).isoformat()
    }

@app.get("/api/report")
def report():
    return scan()
    
