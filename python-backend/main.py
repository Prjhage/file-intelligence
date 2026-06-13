"""
main.py — FastAPI backend server for File Intelligence.
Runs on http://localhost:8000
"""

import os
import sys
import string
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

sys.path.insert(0, os.path.dirname(__file__))

from indexer import FileIndexer
from searcher import search_files

# ── Rate Limiter ───────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)

# ── Drive Detection ────────────────────────────────────────────────────────────
def get_all_drives() -> List[str]:
    try:
        from ctypes import windll
        drives = []
        bitmask = windll.kernel32.GetLogicalDrives()
        for letter in string.ascii_uppercase:
            if bitmask & 1:
                drive_path = f"{letter}:\\"
                drive_type = windll.kernel32.GetDriveTypeW(drive_path)
                if drive_type == 3:
                    drives.append(drive_path)
            bitmask >>= 1
        desktop = os.path.join(os.path.expanduser('~'), 'Desktop')
        if os.path.isdir(desktop):
            drives.append(desktop)
        return drives if drives else [str(Path.home())]
    except Exception as e:
        print(f"[main] Drive detection failed ({e}), falling back to home dir.")
        return [str(Path.home())]

# ── Input Sanitizer ────────────────────────────────────────────────────────────
def sanitize_query(query: str) -> str:
    query = re.sub(r"[^\w\s\-.]", "", query)  # remove SQL special chars
    return query[:100]                          # max 100 characters

# ── Global indexer ─────────────────────────────────────────────────────────────
indexer: FileIndexer = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global indexer
    print("[main] Starting Search Engine (High-Speed Mode)...")
    
    drives = get_all_drives()
    indexer = FileIndexer(folders=drives)
    
    print(f"[main] Initializing indexing for drives: {drives}")
    indexer.start_watching()
    
    existing_count = indexer.total_indexed()
    if existing_count < 100:
        print(f"[main] DB has {existing_count} files — starting full index...")
        indexer.index_all_files()
    else:
        print(f"[main] DB already has {existing_count} files — skipping full re-index. Watcher active.")
    
    print("[main] Backend ready!")
    yield
    
    if indexer:
        indexer.stop_watching()

app = FastAPI(title="File Intelligence API", version="1.0.0", lifespan=lifespan)

# ── Attach rate limiter ────────────────────────────────────────────────────────
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost", "http://127.0.0.1", "tauri://localhost"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ── Pydantic models ────────────────────────────────────────────────────────────
class SearchRequest(BaseModel):
    query: str
    top_k: int = 15

class FolderRequest(BaseModel):
    path: str

# ── Endpoints ──────────────────────────────────────────────────────────────────
@app.get("/")
async def root():
    return {"status": "running", "engine": "SQLite Keyword"}

@app.post("/search")
@limiter.limit("30/minute")
async def search(req: SearchRequest, request: Request):
    if not req.query.strip():
        return {"results": []}
    
    clean_query = sanitize_query(req.query)
    if not clean_query.strip():
        return {"results": []}
    
    results = search_files(clean_query, top_k=req.top_k)
    return {"results": results, "count": len(results)}

@app.get("/status")
@limiter.limit("60/minute")
async def status(request: Request):
    return {
        "total_files": indexer.total_indexed() if indexer else 0,
        "is_indexing": indexer.is_indexing if indexer else False,
        "folders": indexer.folders if indexer else [],
        "ready_for_search": True
    }

@app.post("/index")
@limiter.limit("5/minute")
async def trigger_index(request: Request):
    if indexer:
        indexer.index_all_files()
        return {"status": "started"}
    return {"status": "error", "message": "Indexer not initialized"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
