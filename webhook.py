import requests
import os
import time
import urllib.parse
from fastapi import FastAPI, HTTPException, Request
from collections import Counter
import datetime

app = FastAPI()
HENRIK_API_KEY = os.getenv("HENRIK_API_KEY", "")
cache = {}

def get_cache(k):
    if k in cache:
        data, ts = cache[k]
        if time.time() - ts < 300:
            return data
    return None

def set_cache(k, v):
    cache[k] = (v, time.time())

def safe_get(url, headers):
    try:
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
    EMPTY = {"kda": 0, "winrate": 0, "trend": "Estable", "hs": 0, "adr": 0, "acs": 0,
             "kast": 0, "damage_delta": 0, "agent": "Desconocido", "top_agents": []}
    if not matches:
        return EMPTY

    kills = deaths = assists = wins = 0
    headshots = bodyshots = legshots = 0
    damage_made_total = damage_received_total = 0
    score_total = rounds_total = 0
    kast_ok = kast_total = 0
    kdas_history = []
    agents_played = []
    total_matches = 0

    for m in matches[:10]:
        player = None
        for p in m.get("players", {}).get("all_players", []):
            if (puuid and p.get("puuid") == puuid) or (
                p.get("name", "").lower() == username.lower() and
                p.get("tag", "").lower() == tag.lower()
            ):
                player = p
                break
        if not player:
            continue

        my_puuid = player.get("puuid") or ""
        st = player.get("stats", {})
        k  = int(st.get("kills",     0) or 0)
        d  = int(st.get("deaths",    0) or 0)
        a  = int(st.get("assists",   0) or 0)
        hs = int(st.get("headshots", 0) or 0)
        bs = int(st.get("bodyshots", 0) or 0)
        ls = int(st.get("legshots",  0) or 0)
        sc = int(st.get("score",     0) or 0)
        r  = int(m.get("metadata", {}).get("rounds_played", 1) or 1)

        kills     += k;  deaths    += d;  assists   += a
        headshots += hs; bodyshots += bs; legshots  += ls
        score_total  += sc
        rounds_total += r

        if k + a > 0 or d > 0:
            kdas_history.append((k + a) / max(d, 1))

        agent = player.get("character")
        if agent:
            agents_played.append(agent)

        team  = (player.get("team") or "").lower()
        teams = m.get("teams", {})
        if team and isinstance(teams, dict) and teams.get(team, {}).get("has_won"):
            wins += 1

        match_rounds = m.get("rounds", [])

        if not match_rounds:
            # Fallback sin datos de ronda
            dmg = int(player.get("damage_made") or 0)
            damage_made_total += dmg
            kast_total += r
            kast_ok    += min(k + a, r)
        else:
            kast_total += len(match_rounds)
            for rnd in match_rounds:
                try:
                    ps_list     = rnd.get("player_stats", []) or []
                    kill_events = rnd.get("kill_events",  []) or []

                    my_ps = None
                    for ps in ps_list:
                        ps_puuid = ps.get("player_puuid") or ""
                        ps_name  = str(ps.get("player_display_name") or "").split("#")[0].lower()
                        if (my_puuid and ps_puuid == my_puuid) or (not my_puuid and ps_name == username.lower()):
                            my_ps = ps
                            break

                    if my_ps is None:
                        kast_total -= 1
                        continue

                    # Daño hecho
                    for dmg_entry in (my_ps.get("damage") or []):
                        damage_made_total += int(dmg_entry.get("damage", 0) or 0)

                    # Daño recibido
                    for ps in ps_list:
                        if ps is my_ps:
                            continue
                        for dmg_entry in (ps.get("damage") or []):
                            recv_puuid = dmg_entry.get("receiver_puuid") or ""
                            recv_name  = str(dmg_entry.get("receiver_display_name") or "").split("#")[0].lower()
                            if (my_puuid and recv_puuid == my_puuid) or (not my_puuid and recv_name == username.lower()):
                                damage_received_total += int(dmg_entry.get("damage", 0) or 0)

                    # KAST
                    rnd_k = int(my_ps.get("kills", 0) or 0)

                    rnd_a = 0
                    for ke in kill_events:
                        for ast in (ke.get("assistants") or []):
                            ast_puuid = ast.get("assistant_puuid", "") if isinstance(ast, dict) else str(ast)
                            ast_name  = str(ast.get("assistant_display_name") or "").split("#")[0].lower() if isinstance(ast, dict) else ""
                            if (my_puuid and ast_puuid == my_puuid) or ast_name == username.lower():
                                rnd_a += 1
                                break

                    survived = not any(
                        (my_puuid and ke.get("victim_puuid") == my_puuid) or
                        str(ke.get("victim_display_name") or "").split("#")[0].lower() == username.lower()
                        for ke in kill_events
                    )

                    traded = False
                    if not survived:
                        my_death = next(
                            (ke for ke in kill_events if
                             (my_puuid and ke.get("victim_puuid") == my_puuid) or
                             str(ke.get("victim_display_name") or "").split("#")[0].lower() == username.lower()),
                            None
                        )
                        if my_death:
                            killer_puuid = my_death.get("killer_puuid", "")
                            t0 = int(my_death.get("kill_time_in_round") or 0)
                            traded = any(
                                ke.get("victim_puuid") == killer_puuid and
                                abs(int(ke.get("kill_time_in_round") or 0) - t0) <= 5000
                                for ke in kill_events
                            )

                    if rnd_k > 0 or rnd_a > 0 or survived or traded:
                        kast_ok += 1

                except Exception as e:
                    print(f"[KAST/round] {e}")
                    continue

        total_matches += 1

    if total_matches == 0:
        return EMPTY

    total_shots = headshots + bodyshots + legshots

    trend = "Estable"
    if len(kdas_history) >= 4:
        chron = list(reversed(kdas_history))
        mid   = len(chron) // 2
        p1    = sum(chron[:mid])  / mid
        p2    = sum(chron[mid:])  / (len(chron) - mid)
        if   p2 > p1 + 0.3: trend = "Mejorando"
        elif p2 < p1 - 0.3: trend = "Empeorando"

    agent_counts = Counter(agents_played)
    top_agents   = [ag for ag, _ in agent_counts.most_common()]
    most_played  = top_agents[0] if top_agents else "Desconocido"

    return {
        "kda":          round((kills + assists) / max(deaths, 1), 2),
        "winrate":      round((wins / total_matches) * 100, 1),
        "trend":        trend,
        "hs":           round((headshots / max(total_shots, 1)) * 100, 1),
        "adr":          round(damage_made_total / max(rounds_total, 1), 1),
        "acs":          round(score_total / max(rounds_total, 1), 1),
        "kast":         round((kast_ok / max(kast_total, 1)) * 100, 1),
        "damage_delta": round((damage_made_total - damage_received_total) / max(rounds_total, 1), 1),
        "agent":        most_played,
        "top_agents":   top_agents,
    }


def obtener_stats(username, tag, region="eu"):
    key = f"{username.lower()}#{tag.lower()}"
    cached = get_cache(key)
    if cached: return cached, None

    headers = {"Authorization": HENRIK_API_KEY} if HENRIK_API_KEY else {}
    safe_user = urllib.parse.quote(username)
    safe_tag  = urllib.parse.quote(tag)

    acc_status, acc_json = safe_get(f"https://api.henrikdev.xyz/valorant/v1/account/{safe_user}/{safe_tag}", headers)
    if acc_status == 429: return None, "Rate Limit (La API de Riot esta saturada)"
    if acc_status == 404: return None, "Jugador no encontrado (Riot ID cambiado o erroneo)"
    if acc_status != 200: return None, f"Error cargando cuenta HTTP {acc_status}"

    acc      = acc_json.get("data", {})
    puuid    = acc.get("puuid")
    realname = acc.get("name") or username
    realtag  = acc.get("tag")  or tag

    mmr_status, mmr_json = safe_get(f"https://api.henrikdev.xyz/valorant/v1/mmr/{region}/{safe_user}/{safe_tag}", headers)
    mmr_data = mmr_json.get("data", {}) if mmr_status == 200 else {}
    rank = mmr_data.get("currenttierpatched", "Unranked")
    rr   = mmr_data.get("ranking_in_tier", 0)

    rank_icon_url = ""
    if mmr_status == 200:
        images = mmr_data.get("images", {})
        rank_icon_url = images.get("large") or images.get("small") or ""

    if puuid:
        match_url = f"https://api.henrikdev.xyz/valorant/v3/by-puuid/matches/{region}/{puuid}?size=10"
    else:
        match_url = f"https://api.henrikdev.xyz/valorant/v3/matches/{region}/{safe_user}/{safe_tag}?size=10"

    match_status, match_json = safe_get(match_url, headers)
    if match_status == 429: return None, "Rate Limit de Riot. Espera unos minutos"
    if match_status == 408: return None, "Timeout. La API tardo demasiado en responder"
    if match_status != 200: return None, f"Error cargando el historial de partidas HTTP {match_status}"

    matches_sucias = match_json.get("data", [])

    inicio_temporada = datetime.datetime(2026, 4, 30, 3, 0, tzinfo=datetime.timezone.utc).timestamp()
    matches = [m for m in matches_sucias
               if m.get("metadata", {}).get("game_start", 0) >= inicio_temporada]

    last_match = matches[0] if matches else None
    mapa  = last_match.get("metadata", {}).get("map",  "Desconocido") if last_match else "Desconocido"
    modo  = last_match.get("metadata", {}).get("mode", "Desconocido") if last_match else "Desconocido"
    matchid = last_match.get("metadata", {}).get("matchid", "") if last_match else ""

    last_match_info = {}
    if last_match:
        for p in last_match.get("players", {}).get("all_players", []):
            p_puuid = p.get("puuid")
            p_name  = p.get("name", "")
            p_tag   = p.get("tag",  "")
            if (puuid and p_puuid == puuid) or (p_name.lower() == username.lower() and p_tag.lower() == tag.lower()):
                s  = p.get("stats", {})
                rp = last_match.get("metadata", {}).get("rounds_played", 1)
                team = (p.get("team") or "").lower()
                won  = last_match.get("teams", {}).get(team, {}).get("has_won", False) if team else False
                last_match_info = {
                    "id":     matchid,
                    "kills":  s.get("kills",   0),
                    "deaths": s.get("deaths",  1),
                    "assists":s.get("assists", 0),
                    "acs":    round(s.get("score", 0) / max(rp, 1), 1),
                    "won":    won,
                    "agente": p.get("character", "Desconocido"),
                }
                break

    analysis = analyze_matches(matches, puuid, username, tag)
    is_smurf = analysis["kda"] > 1.8 and analysis["winrate"] > 65 and any(
        r in rank.lower() for r in ["iron", "bronze", "silver", "gold"]
    )

    stats = {
        "nombre":       realname,
        "tag":          realtag,
        "nivel":        acc.get("account_level", 0),
        "card":         acc.get("card", {}).get("small", ""),
        "rank":         rank,
        "rr":           rr,
        "rank_icon":    rank_icon_url,
        "mapa":         mapa,
        "modo":         modo,
        "kda":          analysis["kda"],
        "winrate":      analysis["winrate"],
        "hs":           analysis["hs"],
        "adr":          analysis["adr"],
        "acs":          analysis["acs"],
        "kast":         analysis["kast"],
        "trend":        analysis["trend"],
        "damage_delta": analysis["damage_delta"],
        "smurf":        is_smurf,
        "last_match":   last_match_info,
        "agent":        analysis.get("agent", "Desconocido"),
        "top_agents":   analysis.get("top_agents", []),
    }

    set_cache(key, stats)
    return stats, None


@app.post("/tracker")
async def tracker(request: Request):
    body = await request.json()
    username = body.get("username")
    tag      = body.get("tag")
    region   = body.get("region", "eu")
    if not username or not tag:
        raise HTTPException(status_code=400, detail="Falta username o tag")
    stats, err = obtener_stats(username, tag, region)
    if err:
        return {"success": False, "error": err}
    return {"success": True, "stats": stats}