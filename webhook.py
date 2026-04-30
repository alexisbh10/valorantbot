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
        if time.time() - ts < 300: # 5 minutos de caché
            return data
    return None

def set_cache(k, v):
    cache[k] = (v, time.time())

def safe_get(url, headers):
    try:
        # 20 SEGUNDOS de paciencia. El historial de partidas a veces tarda en cargar.
        r = requests.get(url, headers=headers, timeout=20)
        try:
            data = r.json()
        except:
            data = {}
        return r.status_code, data
    except requests.exceptions.Timeout:
        return 408, {}
    except Exception as e:
        return 500, {}

def analyze_matches(matches, puuid, username, tag):
    if not matches:
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
            p_puuid = p.get("puuid")
            p_name = p.get("name", "")
            p_tag = p.get("tag", "")
            
            # DOBLE FILTRO: Busca por PUUID exacto o por Nombre+Tag (Lo que funcione)
            if (puuid and p_puuid == puuid) or (p_name.lower() == username.lower() and p_tag.lower() == tag.lower()):
                player = p
                break

        if not player:
            continue

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

        # Evita cuelgues si juegan un modo raro como Deathmatch
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
    if cached: return cached, None

    headers = {"Authorization": HENRIK_API_KEY} if HENRIK_API_KEY else {}
    safe_user = urllib.parse.quote(username)
    safe_tag = urllib.parse.quote(tag)

    # 1. OBTIENE LA CUENTA
    acc_status, acc_json = safe_get(f"https://api.henrikdev.xyz/valorant/v1/account/{safe_user}/{safe_tag}", headers)
    if acc_status == 429: return None, "Rate Limit (La API de Riot está saturada)"
    if acc_status == 404: return None, "Jugador no encontrado (Riot ID cambiado o erróneo)"
    if acc_status != 200: return None, f"Error cargando cuenta (HTTP {acc_status})"

    acc = acc_json.get("data", {})
    puuid = acc.get("puuid")
    real_name = acc.get("name") or username
    real_tag = acc.get("tag") or tag

    # 2. OBTIENE EL RANGO
    mmr_status, mmr_json = safe_get(f"https://api.henrikdev.xyz/valorant/v1/mmr/{region}/{safe_user}/{safe_tag}", headers)
    mmr_data = mmr_json.get("data", {}) if mmr_status == 200 else {}
    rank = mmr_data.get("currenttierpatched", "Unranked")
    rr = mmr_data.get("ranking_in_tier", 0)

    # 3. OBTIENE EL HISTORIAL
    if puuid:
        match_url = f"https://api.henrikdev.xyz/valorant/v3/by-puuid/matches/{region}/{puuid}?size=10"
    else:
        match_url = f"https://api.henrikdev.xyz/valorant/v3/matches/{region}/{safe_user}/{safe_tag}?size=10"

    match_status, match_json = safe_get(match_url, headers)
    
    # 🛑 AQUÍ ESTABA EL FALLO: Si esto fallaba, antes devolvía ceros. Ahora bloquea y avisa del error.
    if match_status == 429: return None, "Rate Limit de Riot (Espera unos minutos)"
    if match_status == 408: return None, "Timeout (La API tardó demasiado en responder)"
    if match_status != 200: return None, f"Error cargando el historial de partidas (HTTP {match_status})"

    matches = match_json.get("data", [])

    last_match = matches[0] if matches else {}
    mapa = last_match.get("metadata", {}).get("map", "Desconocido")
    modo = last_match.get("metadata", {}).get("mode", "Desconocido")
    match_id = last_match.get("metadata", {}).get("matchid", "")
    
    last_match_info = {}
    if last_match:
        players = last_match.get("players", {}).get("all_players", [])
        for p in players:
            p_puuid = p.get("puuid")
            p_name = p.get("name", "")
            p_tag = p.get("tag", "")
            
            if (puuid and p_puuid == puuid) or (p_name.lower() == username.lower() and p_tag.lower() == tag.lower()):
                s = p.get("stats", {})
                r = last_match.get("metadata", {}).get("rounds_played", 1)
                
                team = (p.get("team") or "").lower()
                won = last_match.get("teams", {}).get(team, {}).get("has_won", False) if team else False
                
                last_match_info = {
                    "id": match_id,
                    "kills": s.get("kills", 0),
                    "deaths": s.get("deaths", 1),
                    "assists": s.get("assists", 0),
                    "acs": round(s.get("score", 0) / max(r, 1), 1),
                    "won": won,
                    "agente": p.get("character", "Desconocido") # ✅ Esta es la nueva línea
                }
                break

    analysis = analyze_matches(matches, puuid, username, tag)    

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
    return stats, None

@app.post("/tracker")
async def tracker(request: Request):
    body = await request.json()
    username = body.get("username")
    tag = body.get("tag")
    region = body.get("region", "eu")

    if not username or not tag:
        raise HTTPException(status_code=400, detail="Falta username o tag")

    stats, err = obtener_stats(username, tag, region)

    if err:
        return {"success": False, "error": err}

    return {"success": True, "stats": stats}