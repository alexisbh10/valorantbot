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

# ---------------- LEVEL 1 + 2 + 3 ANALYTICS ----------------
def analyze_matches(matches, username, tag):
    if not matches:
        return {
            "kda": 0,
            "winrate": 0,
            "trend": "UNKNOWN",
            "consistency": 0,
            "hs": 0,
            "adr": 0,
            "acs": 0
        }

    kills, deaths, wins = 0, 0, 0
    headshots, bodyshots, legshots = 0, 0, 0
    damage, rounds, score = 0, 0, 0

    kdas = []
    total = 0

    for m in matches[:10]:
        players = m.get("players", {}).get("all_players", [])

        player = None

        # 🔥 BUSCAR JUGADOR CORRECTO
        for p in players:
            if (
                p.get("name", "").lower() == username.lower()
                and p.get("tag", "").lower() == tag.lower()
            ):
                player = p
                break

        if not player:
            continue

        stats = player.get("stats", {})
        dmg = player.get("damage_made", 0)

        k = stats.get("kills", 0)
        d = stats.get("deaths", 1)

        hs = stats.get("headshots", 0)
        bs = stats.get("bodyshots", 0)
        ls = stats.get("legshots", 0)

        r = m.get("metadata", {}).get("rounds_played", 1)
        sc = stats.get("score", 0)

        # acumulados
        kills += k
        deaths += d
        headshots += hs
        bodyshots += bs
        legshots += ls
        damage += dmg
        rounds += r
        score += sc

        kdas.append(k / max(d, 1))

        # win check correcto
        team = player.get("team")
        if m.get("teams", {}).get(team, {}).get("has_won"):
            wins += 1

        total += 1

    if total == 0:
        return {
            "kda": 0,
            "winrate": 0,
            "trend": "UNKNOWN",
            "consistency": 0,
            "hs": 0,
            "adr": 0,
            "acs": 0
        }

    total_shots = headshots + bodyshots + legshots

    # 📊 métricas reales
    kda = round(kills / max(deaths, 1), 2)
    winrate = round((wins / total) * 100, 1)
    hs_percent = round((headshots / max(total_shots, 1)) * 100, 1)
    adr = round(damage / max(rounds, 1), 1)
    acs = round(score / max(rounds, 1), 1)

    # 📈 trend
    trend = "STABLE"
    if len(kdas) >= 5:
        if kdas[-1] > kdas[0]:
            trend = "IMPROVING"
        elif kdas[-1] < kdas[0]:
            trend = "DECLINING"

    return {
        "kda": kda,
        "winrate": winrate,
        "trend": trend,
        "consistency": round(max(kdas) - min(kdas), 2),
        "hs": hs_percent,
        "adr": adr,
        "acs": acs
    }

# ---------------- SMURF DETECTION ----------------
def smurf_detect(elo, rank):
    if elo > 1300 and "Iron" in rank:
        return True
    return False

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

    # ---------------- MMR (FIX REAL) ----------------
    mmr_json = safe_get(
        f"https://api.henrikdev.xyz/valorant/v2/mmr/{region}/{username}/{tag}",
        headers
    )

    mmr_data = mmr_json.get("data")
    if not isinstance(mmr_data, dict):
        mmr_data = {}

    rank = (
        mmr_data.get("currenttierpatched")
        or mmr_data.get("currenttier")
        or "Unranked"
    )

    rr = mmr_data.get("ranking_in_tier") or 0

    # ---------------- MATCHES (FIX REAL) ----------------
    match_json = safe_get(
        f"https://api.henrikdev.xyz/valorant/v3/matches/{region}/{username}/{tag}",
        headers
    )

    matches = match_json.get("data")
    if not isinstance(matches, list):
        matches = []

    last = matches[0] if matches else {}

    mapa = last.get("metadata", {}).get("map", "N/A")
    modo = last.get("metadata", {}).get("mode", "N/A")

    # ---------------- ANALYTICS ----------------
    analysis = analyze_matches(matches, username, tag)    
    elo = calculate_elo(matches)

    stats = {
        # BASIC
        "nombre": acc.get("name", "N/A"),
        "tag": acc.get("tag", "N/A"),
        "nivel": acc.get("account_level", 0),

        # RANK
        "rank": rank,
        "rr": rr,

        # LAST MATCH
        "mapa": mapa,
        "modo": modo,

       # LEVEL 1+
        "kda": analysis["kda"],
        "winrate": analysis["winrate"],
        "hs": analysis["hs"],
        "adr": analysis["adr"],
        "acs": analysis["acs"],

        # LEVEL 2
        "trend": analysis["trend"],
        "consistency": analysis["consistency"],

        # LEVEL 3
        "smurf": smurf_detect(elo, rank)
    }

    set_cache(key, stats)
    return stats

# ---------------- EMBED ----------------
def crear_embed(s):

    smurf_text = "⚠️ SMURF DETECTED" if s["smurf"] else "OK"

    return {
        "title": f"📊 {s['nombre']}#{s['tag']}",
        "color": 0xFF4655,
        "fields": [
            {"name": "🎮 Nivel", "value": str(s["nivel"]), "inline": True},
            {"name": "🏆 Rank", "value": s["rank"], "inline": True},
            {"name": "📈 RR", "value": str(s["rr"]), "inline": True},

            {"name": "📊 KDA", "value": str(s["kda"]), "inline": True},
            {"name": "🎯 HS%", "value": f"{s['hs']}%", "inline": True},
            {"name": "💥 ADR", "value": str(s["adr"]), "inline": True},
            {"name": "⚔️ ACS", "value": str(s["acs"]), "inline": True},
            {"name": "📈 Winrate", "value": f"{s['winrate']}%", "inline": True},

            {"name": "🧠 ELO", "value": str(s["elo"]), "inline": True},
            {"name": "📉 Consistencia", "value": str(s["consistency"]), "inline": True},
            {"name": "📈 Tendencia", "value": s["trend"], "inline": True},

            {"name": "🧪 Estado", "value": smurf_text, "inline": False},

            {"name": "🗺️ Último mapa", "value": s["mapa"], "inline": True},
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