import requests
import os
import time
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from datetime import datetime

app = FastAPI()

HENRIK_API_KEY = os.getenv("HENRIK_API_KEY")
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK_URL")

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

# ---------------- CORE STATS ----------------
def obtener_stats(username, tag, region="eu"):
    key = f"{username}{tag}"
    cached = get_cache(key)
    if cached:
        return cached

    headers = {"Authorization": HENRIK_API_KEY}

    acc = requests.get(
        f"https://api.henrikdev.xyz/valorant/v1/account/{username}/{tag}",
        headers=headers
    ).json()["data"]

    mmr = requests.get(
        f"https://api.henrikdev.xyz/valorant/v2/mmr/{region}/{username}/{tag}",
        headers=headers
    ).json()["data"]

    matches = requests.get(
        f"https://api.henrikdev.xyz/valorant/v3/matches/{region}/{username}/{tag}",
        headers=headers
    ).json()["data"]

    last = matches[0]

    stats = {
        "nombre": acc["name"],
        "tag": acc["tag"],
        "nivel": acc["account_level"],

        "rank": mmr["currenttierpatched"],
        "rr": mmr["ranking_in_tier"],

        "mapa": last["metadata"]["map"],
        "modo": last["metadata"]["mode"]
    }

    set_cache(key, stats)
    return stats

# ---------------- DISCORD EMBED ----------------
def crear_embed(s):
    return {
        "title": f"📊 {s['nombre']}#{s['tag']}",
        "color": 0xFF4655,
        "fields": [
            {"name": "🎮 Nivel", "value": s["nivel"], "inline": True},
            {"name": "🏆 Rank", "value": s["rank"], "inline": True},
            {"name": "📈 RR", "value": s["rr"], "inline": True},
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
    user_id = body.get("discord_user_id")

    if not username or not tag:
        raise HTTPException(status_code=400, detail="username y tag requeridos")

    stats = obtener_stats(username, tag, region)
    embed = crear_embed(stats)

    return {
        "success": True,
        "stats": stats
    }

@app.get("/health")
async def health():
    return {"status": "ok"}