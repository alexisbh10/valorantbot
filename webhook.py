import requests
import os
import time
from fastapi import FastAPI, HTTPException, Request
from datetime import datetime

app = FastAPI()

HENRIK_API_KEY = os.getenv("HENRIK_API_KEY", "")

cache = {}

# ---------------- CACHE ----------------
def get_cache(k):
    if k in cache:
        data, ts = cache[k]
        if time.time() - ts < 120: # 2 minutos de caché para no saturar la API
            return data
    return None

def set_cache(k, v):
    cache[k] = (v, time.time())

# ---------------- SAFE REQUEST ----------------
def safe_get(url, headers):
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            return r.json()
        return {}
    except Exception as e:
        print(f"Error API: {e}")
        return {}

# ---------------- REAL ANALYTICS ----------------
def analyze_matches(matches, username, tag):
    if not matches:
        return {"kda": 0, "winrate": 0, "trend": "➖", "hs": 0, "adr": 0, "acs": 0}

    kills, deaths, assists, wins = 0, 0, 0, 0
    headshots, bodyshots, legshots = 0, 0, 0
    damage, rounds, score = 0, 0, 0
    kdas_history = []
    total_matches = 0

    for m in matches[:10]: # Analizamos las últimas 10 partidas
        players = m.get("players", {}).get("all_players", [])
        player = None

        for p in players:
            if p.get("name", "").lower() == username.lower() and p.get("tag", "").lower() == tag.lower():
                player = p
                break

        if not player:
            continue

        stats = player.get("stats", {})
        
        # Básicos
        k = stats.get("kills", 0)
        d = stats.get("deaths", 1)
        a = stats.get("assists", 0)
        
        # Tiroteo
        hs = stats.get("headshots", 0)
        bs = stats.get("bodyshots", 0)
        ls = stats.get("legshots", 0)
        
        # Impacto
        dmg = player.get("damage_made") or stats.get("damage_made") or 0
        sc = stats.get("score", 0)
        r = m.get("metadata", {}).get("rounds_played", 1)

        # Acumulados
        kills += k
        deaths += d
        assists += a
        headshots += hs
        bodyshots += bs
        legshots += ls
        damage += dmg
        rounds += r
        score += sc

        # KDA Individual para la tendencia
        kdas_history.append((k + a) / max(d, 1))

        # Winrate
        team = player.get("team")
        teams = m.get("teams", {})
        if team and isinstance(teams, dict) and teams.get(team, {}).get("has_won"):
            wins += 1

        total_matches += 1

    if total_matches == 0:
        return {"kda": 0, "winrate": 0, "trend": "➖", "hs": 0, "adr": 0, "acs": 0}

    # Cálculos Reales
    total_shots = headshots + bodyshots + legshots
    kda_real = round((kills + assists) / max(deaths, 1), 2)
    winrate = round((wins / total_matches) * 100, 1)
    hs_percent = round((headshots / max(total_shots, 1)) * 100, 1)
    adr = round(damage / max(rounds, 1), 1)
    acs = round(score / max(rounds, 1), 1)

    # Tendencia (Comparando primera mitad vs segunda mitad)
    trend = "Estable ➖"
    if len(kdas_history) >= 4:
        chronological = list(reversed(kdas_history))
        mid = len(chronological) // 2
        p1 = sum(chronological[:mid]) / mid
        p2 = sum(chronological[mid:]) / (len(chronological) - mid)
        if p2 > p1 + 0.3: trend = "Mejorando 📈"
        elif p2 < p1 - 0.3: trend = "Empeorando 📉"

    return {
        "kda": kda_real,
        "winrate": winrate,
        "trend": trend,
        "hs": hs_percent,
        "adr": adr,
        "acs": acs
    }

# ---------------- CORE ----------------
def obtener_stats(username, tag, region="eu"):
    key = f"{username.lower()}#{tag.lower()}"
    cached = get_cache(key)
    if cached: return cached

    headers = {"Authorization": HENRIK_API_KEY} if HENRIK_API_KEY else {}

    # ACCOUNT INFO
    acc_json = safe_get(f"https://api.henrikdev.xyz/valorant/v1/account/{username}/{tag}", headers)
    acc = acc_json.get("data", {})

    # MMR (ARREGLADO: v1 es más directo y falla menos para el Rango)
    mmr_json = safe_get(f"https://api.henrikdev.xyz/valorant/v1/mmr/{region}/{username}/{tag}", headers)
    mmr_data = mmr_json.get("data", {})
    
    rank = mmr_data.get("currenttierpatched", "Unranked")
    rr = mmr_data.get("ranking_in_tier", 0)

    # MATCHES PARA STATS
    match_json = safe_get(f"https://api.henrikdev.xyz/valorant/v3/matches/{region}/{username}/{tag}?size=10", headers)
    matches = match_json.get("data", [])

    last_match = matches[0] if matches else {}
    mapa = last_match.get("metadata", {}).get("map", "Desconocido")
    modo = last_match.get("metadata", {}).get("mode", "Desconocido")

    analysis = analyze_matches(matches, username, tag)    

    # Smurf Detect Realista (KDA > 1.8 y Winrate > 65% en rangos bajos)
    is_smurf = (analysis["kda"] > 1.8 and analysis["winrate"] > 65 and any(r in rank.lower() for r in ["iron", "bronze", "silver", "gold"]))

    stats = {
        "nombre": acc.get("name", username),
        "tag": acc.get("tag", tag),
        "nivel": acc.get("account_level", 0),
        "card": acc.get("card", {}).get("small", ""),
        "rank": rank,
        "rr": rr,
        "mapa": mapa,
        "modo": modo,
        "kda": analysis["kda"],
        "winrate": analysis["winrate"],
        "hs": analysis["hs"],
        "adr": analysis["adr"],
        "acs": analysis["acs"],
        "trend": analysis["trend"],
        "smurf": is_smurf
    }

    set_cache(key, stats)
    return stats

# ---------------- ENDPOINT ----------------
@app.post("/tracker")
async def tracker(request: Request):
    body = await request.json()
    username = body.get("username")
    tag = body.get("tag")
    region = body.get("region", "eu")

    if not username or not tag:
        raise HTTPException(status_code=400, detail="Falta username o tag")

    stats = obtener_stats(username, tag, region)

    if stats["rank"] == "Unranked" and stats["nivel"] == 0:
        return {"success": False, "error": "Jugador no encontrado o perfil privado."}

    return {"success": True, "stats": stats}