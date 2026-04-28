import requests
import os
import time
from fastapi import FastAPI, HTTPException, Request
from datetime import datetime
from collections import Counter # <-- NUEVO: Para contar los agentes

app = FastAPI()

HENRIK_API_KEY = os.getenv("HENRIK_API_KEY", "")

cache = {}

# ---------------- CACHE ----------------
def get_cache(k):
    if k in cache:
        data, ts = cache[k]
        if time.time() - ts < 120: 
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
        return {"kda": 0, "winrate": 0, "trend": "➖", "hs": 0, "adr": 0, "acs": 0, "most_played_agent": "Desconocido", "top_agents": []}

    kills, deaths, assists, wins = 0, 0, 0, 0
    headshots, bodyshots, legshots = 0, 0, 0
    damage, rounds, score = 0, 0, 0
    kdas_history = []
    agents_played = [] # <-- NUEVO: Guardaremos los agentes de cada partida
    total_matches = 0

    for m in matches[:10]:
        players = m.get("players", {}).get("all_players", [])
        player = None

        for p in players:
            if p.get("name", "").lower() == username.lower() and p.get("tag", "").lower() == tag.lower():
                player = p
                break

        if not player:
            continue

        # Guardar el agente jugado
        agent = player.get("character")
        if agent:
            agents_played.append(agent)

        stats = player.get("stats", {})
        
        k = stats.get("kills", 0)
        d = stats.get("deaths", 1)
        a = stats.get("assists", 0)
        
        hs = stats.get("headshots", 0)
        bs = stats.get("bodyshots", 0)
        ls = stats.get("legshots", 0)
        
        dmg = player.get("damage_made") or stats.get("damage_made") or 0
        sc = stats.get("score", 0)
        r = m.get("metadata", {}).get("rounds_played", 1)

        kills += k
        deaths += d
        assists += a
        headshots += hs
        bodyshots += bs
        legshots += ls
        damage += dmg
        rounds += r
        score += sc

        kdas_history.append((k + a) / max(d, 1))

        team = player.get("team", "").lower()
        teams = m.get("teams", {})
        if team and isinstance(teams, dict):
            if teams.get(team, {}).get("has_won"):
                wins += 1

        total_matches += 1

    if total_matches == 0:
        return {"kda": 0, "winrate": 0, "trend": "➖", "hs": 0, "adr": 0, "acs": 0, "most_played_agent": "Desconocido", "top_agents": []}

    total_shots = headshots + bodyshots + legshots
    
    trend = "Estable ➖"
    if len(kdas_history) >= 4:
        chronological = list(reversed(kdas_history))
        mid = len(chronological) // 2
        p1 = sum(chronological[:mid]) / mid
        p2 = sum(chronological[mid:]) / (len(chronological) - mid)
        if p2 > p1 + 0.3: trend = "Mejorando 📈"
        elif p2 < p1 - 0.3: trend = "Empeorando 📉"

    # <-- NUEVO: Contar los agentes más jugados
    agent_counts = Counter(agents_played)
    top_agents = [agent for agent, count in agent_counts.most_common(3)]
    most_played = top_agents[0] if top_agents else "Desconocido"

    return {
        "kda": round((kills + assists) / max(deaths, 1), 2),
        "winrate": round((wins / total_matches) * 100, 1),
        "trend": trend,
        "hs": round((headshots / max(total_shots, 1)) * 100, 1),
        "adr": round(damage / max(rounds, 1), 1),
        "acs": round(score / max(rounds, 1), 1),
        "most_played_agent": most_played,
        "top_agents": top_agents
    }

# ---------------- CORE ----------------
def obtener_stats(username, tag, region="eu"):
    key = f"{username.lower()}#{tag.lower()}"
    cached = get_cache(key)
    if cached: return cached

    headers = {"Authorization": HENRIK_API_KEY} if HENRIK_API_KEY else {}

    acc_json = safe_get(f"https://api.henrikdev.xyz/valorant/v1/account/{username}/{tag}", headers)
    acc = acc_json.get("data", {})

    mmr_json = safe_get(f"https://api.henrikdev.xyz/valorant/v1/mmr/{region}/{username}/{tag}", headers)
    mmr_data = mmr_json.get("data", {})
    rank = mmr_data.get("currenttierpatched", "Unranked")
    rr = mmr_data.get("ranking_in_tier", 0)

    match_json = safe_get(f"https://api.henrikdev.xyz/valorant/v3/matches/{region}/{username}/{tag}?size=10", headers)
    matches = match_json.get("data", [])

    last_match = matches[0] if matches else {}
    mapa = last_match.get("metadata", {}).get("map", "Desconocido")
    modo = last_match.get("metadata", {}).get("mode", "Desconocido")
    match_id = last_match.get("metadata", {}).get("matchid", "")
    
    last_match_info = {}
    if last_match:
        players = last_match.get("players", {}).get("all_players", [])
        for p in players:
            if p.get("name", "").lower() == username.lower() and p.get("tag", "").lower() == tag.lower():
                s = p.get("stats", {})
                r = last_match.get("metadata", {}).get("rounds_played", 1)
                team = p.get("team", "").lower()
                won = last_match.get("teams", {}).get(team, {}).get("has_won", False)
                
                last_match_info = {
                    "id": match_id,
                    "kills": s.get("kills", 0),
                    "deaths": s.get("deaths", 1),
                    "assists": s.get("assists", 0),
                    "acs": round(s.get("score", 0) / max(r, 1), 1),
                    "won": won
                }
                break

    analysis = analyze_matches(matches, username, tag)    

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
        "smurf": is_smurf,
        "last_match": last_match_info,
        "agent": analysis["most_played_agent"], # <-- NUEVO
        "top_agents": analysis["top_agents"]    # <-- NUEVO
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