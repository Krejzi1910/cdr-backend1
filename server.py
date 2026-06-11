"""
Color Dice Rigged — BACKEND  v1.0
==================================
FastAPI service that farms tokens from online-dice.com in the background
and serves them to the Chrome extension via a small REST API.

Endpoints:
  GET  /api/find?count=4&colors=Red,Blue,Green,Yellow
       -> { "status": "found", "token": "9PEMx", "fresh": false, "source": "cache" }
       -> { "status": "not-found-yet", "indexing": true }

  GET  /api/stats
       -> { "size": 12345, "coverage": {2: 1.0, 3: 0.98, 4: 0.7, 5: 0.3, 6: 0.05},
            "rate": 1.2, "cooldown_until": 0 }

  GET  /api/health
       -> { "ok": true, "uptime_sec": 3600 }

  Auth via Bearer token in `Authorization` header (random key generated on install).
"""

import os
import time
import asyncio
import logging
from typing import Optional, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from db import DB
from farmer import Farmer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("cdr")

# ------------ config ------------
API_KEY = os.environ.get("CDR_API_KEY", "")
DB_PATH = os.environ.get("CDR_DB_PATH", "/tmp/cdr.sqlite")
# Render uses PORT env var; Oracle/local can use CDR_PORT
LISTEN_PORT = int(os.environ.get("PORT") or os.environ.get("CDR_PORT", "8000"))
START_TS = time.time()

# rotate dice counts (weighted towards 3-4 dice which are most useful)
DICE_ROTATION = [2, 3, 3, 4, 4, 4, 5, 6]

db: DB = None
farmer: Farmer = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global db, farmer
    db = DB(DB_PATH)
    db.init_schema()
    farmer = Farmer(db, dice_rotation=DICE_ROTATION)
    bg_task = asyncio.create_task(farmer.run_forever())
    log.info("Backend started. DB=%s key=%s", DB_PATH, "set" if API_KEY else "OPEN")
    yield
    farmer.stop()
    bg_task.cancel()
    try:
        await bg_task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="Color Dice Rigged Backend", version="1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


def _check_auth(authorization: Optional[str]):
    if not API_KEY:
        return  # open mode (not recommended)
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization")
    expected = f"Bearer {API_KEY}"
    if authorization.strip() != expected:
        raise HTTPException(status_code=401, detail="Bad token")


@app.get("/api/health")
async def health():
    return {
        "ok": True,
        "uptime_sec": int(time.time() - START_TS),
        "version": "1.0",
        "auth_required": bool(API_KEY),
    }


@app.get("/api/stats")
async def stats(authorization: Optional[str] = Header(None)):
    _check_auth(authorization)
    return {
        "size": db.total_count(),
        "coverage": db.coverage(),
        "rate_per_sec": farmer.current_rate(),
        "cooldown_until": farmer.cooldown_until,
        "tier": farmer.tier,
        "last_token": db.last_token(),
        "uptime_sec": int(time.time() - START_TS),
    }


@app.get("/api/find")
async def find(
    count: int = Query(..., ge=2, le=6),
    colors: str = Query(..., description="Comma-separated, e.g. Red,Blue,Green,Yellow"),
    fresh_only: bool = Query(False, description="If true, only return tokens <3min old"),
    authorization: Optional[str] = Header(None),
):
    _check_auth(authorization)

    color_list = [c.strip() for c in colors.split(",") if c.strip()]
    if len(color_list) != count:
        raise HTTPException(status_code=400, detail=f"Expected {count} colors, got {len(color_list)}")

    valid = {"Blue", "Green", "Red", "Purple", "Orange", "Yellow"}
    if not all(c in valid for c in color_list):
        raise HTTPException(status_code=400, detail="Invalid color name")

    combo_key = f"{count}|{','.join(color_list)}"

    # 1. check cache
    row = db.find_token(combo_key, max_age_sec=180 if fresh_only else None)
    if row:
        return {
            "status": "found",
            "token": row["token"],
            "age_sec": int(time.time() - row["ts"]),
            "source": "cache",
        }

    # 2. miss — kick off on-demand burst farm for this specific combo
    found_token = await farmer.burst_find(combo_key, count, color_list, max_rolls=80, timeout_sec=15)
    if found_token:
        return {"status": "found", "token": found_token, "age_sec": 0, "source": "live"}

    return {"status": "not-found-yet", "indexing": True,
            "hint": "Cache miss for this combo. Background farmer is still building the index — try again in a moment."}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=LISTEN_PORT, log_level="info")
