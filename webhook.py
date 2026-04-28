import requests
import os
import time
import urllib.parse
from fastapi import FastAPI, HTTPException, Request
from collections import Counter

app = FastAPI()

HENRIK_API_KEY = os.getenv("HENRIK_API_KEY", "")

cache = {}

def get_cache(k):
    if k in cache:
        data, ts = cache[k]
        if time.time() - ts < 180: 
            return data
    return None

def set_cache(k, v):
    cache[k] = (v, time.time())

def safe_get(url, headers):
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            return r.json()
        elif r.status_code == 429:
            print(f"⚠️ RATE LIMIT (429) en: {url}")
        return {}
    except Exception as e:
        print(f"Error API: {e}")
        return {}

def analyze_matches(matches, puuid):
    if not matches or not puuid:
        return {"kda": 0, "winrate": 0, "trend": "➖", "hs": 0, "adr": 0, "acs": 0, "agent": "Desconocido", "top_agents": []}

    kills, deaths, assists, wins = 0, 0, 0, 0
    headshots, bodyshots, legshots = 0, 0, 0
    damage, rounds, score = 0, 0, 0
    kdas_history = []
    agents_played = []
    total_matches = 0

    for m in matches[:10]:
        players = m.get("players", {}).get("all_players", [])
        player = None

        for p in players:
            if p.get("puuid") == puuid:
                player = p
                break

        if not player:
            continue

        agent = player.get("character")
        if agent:
            agents_played.append(agent)

        stats = player.get("stats", {})
        
        k = stats.get("kills") or 0
        d = stats.get("deaths") or 1
        a = stats.get("assists") or 0
        
        hs = stats.get("headshots") or 0
        bs = stats.get("bodyshots") or 0
        ls = stats.get("legshots") or 0
        
        dmg = player.get("damage_made") or stats.get("damage_made") or 0
        sc = stats.get("score") or 0
        r = m.get("metadata", {}).get("rounds_played") or 1

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

        team = (player.get("team") or "").lower()
        teams = m.get("teams", {})
        if team and isinstance(teams, dict):
            if teams.get(team, {}).get("has_won"):
                wins += 1

        total_matches += 1

    if total_matches == 0:
        return {"kda": 0, "winrate": 0, "trend": "➖", "hs": 0, "adr": 0, "acs": 0, "agent": "Desconocido", "top_agents": []}

    total_shots = headshots + bodyshots + legshots
    
    trend = "Estable ➖"
    if len(kdas_history) >= 4:
        chronological = list(reversed(kdas_history))
        mid = len(chronological) // 2
        p1 = sum(chronological[:mid]) / mid
        p2 = sum(chronological[mid:]) / (len(chronological) - mid)
        if p2 > p1 + 0.3: trend = "Mejorando 📈"
        elif p2 < p1 - 0.3: trend = "Empeorando 📉"

    agent_counts = Counter(agents_played)
    top_agents = [agent for agent, count in agent_counts.most_common()]
    most_played = top_agents[0] if top_agents else "Desconocido"

    return {
        "kda": round((kills + assists) / max(deaths, 1), 2),
        "winrate": round((wins / total_matches) * 100, 1),
        "trend": trend,
        "hs": round((headshots / max(total_shots, 1)) * 100, 1),
        "adr": round(damage / max(rounds, 1), 1),
        "acs": round(score / max(rounds, 1), 1),
        "agent": most_played,
        "top_agents": top_agents
    }

def obtener_stats(username, tag, region="eu"):
    key = f"{username.lower()}#{tag.lower()}"
    cached = get_cache(key)
    if cached: return cached

    headers = {"Authorization": HENRIK_API_KEY} if HENRIK_API_KEY else {}

    safe_user = urllib.parse.quote(username)
    safe_tag = urllib.parse.quote(tag)

    acc_json = safe_get(f"https://api.henrikdev.xyz/valorant/v1/account/{safe_user}/{safe_tag}", headers)
    acc = acc_json.get("data", {})
    
    # ¡LA CLAVE ESTÁ AQUÍ! Si la API falla por Rate Limit, devolvemos None para no envenenar la caché.
    if not acc:
        return None

    puuid = acc.get("puuid")
    real_name = acc.get("name") or username
    real_tag = acc.get("tag") or tag

    mmr_json = safe_get(f"https://api.henrikdev.xyz/valorant/v1/mmr/{region}/{safe_user}/{safe_tag}", headers)
    mmr_data = mmr_json.get("data", {})
    rank = mmr_data.get("currenttierpatched", "Unranked")
    rr = mmr_data.get("ranking_in_tier", 0)

    match_json = safe_get(f"https://api.henrikdev.xyz/valorant/v3/matches/{region}/{safe_user}/{safe_tag}?size=10", headers)
    matches = match_json.get("data", [])

    last_match = matches[0] if matches else {}
    mapa = last_match.get("metadata", {}).get("map", "Desconocido")
    modo = last_match.get("metadata", {}).get("mode", "Desconocido")
    match_id = last_match.get("metadata", {}).get("matchid", "")
    
    last_match_info = {}
    if last_match and puuid:
        players = last_match.get("players", {}).get("all_players", [])
        for p in players:
            if p.get("puuid") == puuid:
                s = p.get("stats", {})
                r = last_match.get("metadata", {}).get("rounds_played") or 1
                
                team = (p.get("team") or "").lower()
                won = last_match.get("teams", {}).get(team, {}).get("has_won", False) if team else False
                
                last_match_info = {
                    "id": match_id,
                    "kills": s.get("kills") or 0,
                    "deaths": s.get("deaths") or 1,
                    "assists": s.get("assists") or 0,
                    "acs": round((s.get("score") or 0) / max(r, 1), 1),
                    "won": won
                }
                break

    analysis = analyze_matches(matches, puuid)    

    is_smurf = (analysis["kda"] > 1.8 and analysis["winrate"] > 65 and any(r in rank.lower() for r in ["iron", "bronze", "silver", "gold"]))

    stats = {
        "nombre": real_name,
        "tag": real_tag,
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
        "agent": analysis.get("agent", "Desconocido"),
        "top_agents": analysis.get("top_agents", [])
    }

    set_cache(key, stats)
    return stats

@app.post("/tracker")
async def tracker(request: Request):
    body = await request.json()
    username = body.get("username")
    tag = body.get("tag")
    region = body.get("region", "eu")

    if not username or not tag:
        raise HTTPException(status_code=400, detail="Falta username o tag")

    stats = obtener_stats(username, tag, region)

    if not stats:
        return {"success": False, "error": "Rate Limit de la API o usuario no encontrado. Reintenta en unos segundos."}

    if stats["rank"] == "Unranked" and stats["nivel"] == 0:
        return {"success": False, "error": "Perfil privado o sin datos recientes."}

    return {"success": True, "stats": stats}