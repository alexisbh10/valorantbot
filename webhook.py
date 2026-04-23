import requests
import os
import time
from fastapi import FastAPI, HTTPException, Request
from datetime import datetime

app = FastAPI()

HENRIK_API_KEY = os.getenv("HENRIK_API_KEY")

cache = {}

# ---------------- CACHE ----------------
def get_cache(k):
    if k in cache:
        data, ts = cache[k]
        if time.time() - ts < 60:
            return data
    return None

def set_cache(k, v):
    cache[k] = (v, time.time())

# ---------------- SAFE REQUEST ----------------
def safe_get(url, headers):
    try:
        r = requests.get(url, headers=headers, timeout=10)
        return r.json()
    except:
        return {}

# ---------------- CORE ----------------
def obtener_stats(username, tag, region="eu"):
    key = f"{username}{tag}"
    cached = get_cache(key)
    if cached:
        return cached

    headers = {"Authorization": HENRIK_API_KEY}

    # ACCOUNT
    acc_json = safe_get(
        f"https://api.henrikdev.xyz/valorant/v1/account/{username}/{tag}",
        headers
    )
    acc = acc_json.get("data") or {}

    # MMR
    mmr_json = safe_get(
        f"https://api.henrikdev.xyz/valorant/v2/mmr/{region}/{username}/{tag}",
        headers
    )
    mmr = mmr_json.get("data") or {}

    # MATCHES
    match_json = safe_get(
        f"https://api.henrikdev.xyz/valorant/v3/matches/{region}/{username}/{tag}",
        headers
    )
    matches = match_json.get("data") or []

    last = matches[0] if matches else None

    stats = {
        "nombre": acc.get("name", "N/A"),
        "tag": acc.get("tag", "N/A"),
        "nivel": acc.get("account_level", 0),

        "rank": mmr.get("currenttierpatched", "Unranked"),
        "rr": mmr.get("ranking_in_tier", 0),

        "mapa": last["metadata"]["map"] if last else "N/A",
        "modo": last["metadata"]["mode"] if last else "N/A"
    }

    set_cache(key, stats)
    return stats

# ---------------- EMBED ----------------
def crear_embed(s):
    return {
        "title": f"📊 {s['nombre']}#{s['tag']}",
        "color": 0xFF4655,
        "fields": [
            {"name": "🎮 Nivel", "value": str(s["nivel"]), "inline": True},
            {"name": "🏆 Rank", "value": s["rank"], "inline": True},
            {"name": "📈 RR", "value": str(s["rr"]), "inline": True},
            {"name": "🗺️ Mapa", "value": s["mapa"], "inline": True},
            {"name": "🎯 Modo", "value": s["modo"], "inline": True},
        ],
        "timestamp": datetime.utcnow().isoformat()
    }

# ---------------- ENDPOINT ----------------
@app.post("/tracker")
async def tracker(request: Request):
    body = await request.json()

    username = body.get("username")
    tag = body.get("tag")
    region = body.get("region", "eu")

    if not username or not tag:
        raise HTTPException(status_code=400, detail="username y tag requeridos")

    stats = obtener_stats(username, tag, region)

    return {
        "success": True,
        "stats": stats
    }

# ---------------- HEALTH ----------------
@app.get("/health")
async def health():
    return {"status": "ok"}