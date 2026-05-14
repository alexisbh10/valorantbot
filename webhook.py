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
        except Exception:
            data = {}
        return r.status_code, data
    except requests.exceptions.Timeout:
        return 408, {}
    except Exception:
        return 500, {}


def find_player(players, puuid, username, tag):
    for p in players:
        p_puuid = p.get("puuid")
        p_name = p.get("name", "")
        p_tag = p.get("tag", "")
        if (puuid and p_puuid == puuid) or (p_name.lower() == username.lower() and p_tag.lower() == tag.lower()):
            return p
    return None


def get_team_win(match, player):
    team = (player.get("team") or "").lower()
    teams = match.get("teams", {}) or {}
    if team and isinstance(teams, dict):
        return teams.get(team, {}).get("has_won", False)
    return False


def extract_tracker_like_match_metrics(match, player):
    stats    = player.get("stats", {}) or {}
    metadata = match.get("metadata", {}) or {}
    rounds_played = metadata.get("rounds_played", 0) or 0
    score         = stats.get("score", 0) or 0

    puuid  = player.get("puuid", "") or ""
    p_name = player.get("name", "").lower()
    p_tag  = player.get("tag", "").lower()

    damage_dealt_total    = 0
    damage_received_total = 0
    kast_rounds           = 0

    # KAST: muertes del jugador por ronda (para detectar si sobrevivió)
    # Precalculamos kills de cada ronda para saber quién murió
    all_rounds = match.get("rounds") or []

    for rnd in all_rounds:
        player_stats = rnd.get("player_stats") or []

        # ── Buscar el entry de nuestro jugador en esta ronda ──────────────
        my_ps = None
        for ps in player_stats:
            ps_puuid = ps.get("player_puuid", "") or ""
            if puuid and ps_puuid == puuid:
                my_ps = ps
                break
            if not puuid:
                name_check = ps.get("player_display_name", "").lower()
                if p_name and p_name in name_check:
                    my_ps = ps
                    break

        if my_ps is None:
            continue

        # ── ADR: daño que nuestro jugador hizo a otros ────────────────────
        for dmg in (my_ps.get("damage") or []):
            damage_dealt_total += dmg.get("damage", 0) or 0

        # ── DDA: daño que otros hicieron a nuestro jugador ────────────────
        # Iteramos todos los demás jugadores y sumamos el daño donde receiver == nuestro puuid
        for ps in player_stats:
            ps_puuid = ps.get("player_puuid", "") or ""
            if puuid and ps_puuid == puuid:
                continue  # saltamos el propio jugador
            for dmg in (ps.get("damage") or []):
                receiver = dmg.get("receiver_puuid", "") or ""
                if puuid and receiver == puuid:
                    damage_received_total += dmg.get("damage", 0) or 0

        # ── KAST ─────────────────────────────────────────────────────────
        # K: tuvo al menos 1 kill en la ronda
        # A: tuvo al menos 1 asistencia en la ronda
        # S: sobrevivió (no aparece como víctima en ningún kill de la ronda)
        # T: fue eliminado pero su asesino murió en los 5s siguientes (aproximación: fue traded)

        my_kills    = my_ps.get("kills") or []
        my_assists  = my_ps.get("assists") or []
        had_kill    = len(my_kills) > 0
        had_assist  = len(my_assists) > 0

        # Saber si murió en esta ronda: buscar si aparece como victim en kills de otros
        died_this_round = False
        traded          = False
        my_death_time   = None

        for ps in player_stats:
            ps_puuid = ps.get("player_puuid", "") or ""
            if puuid and ps_puuid == puuid:
                continue
            for kill in (ps.get("kills") or []):
                victim_puuid = kill.get("victim_puuid", "") or ""
                if puuid and victim_puuid == puuid:
                    died_this_round = True
                    my_death_time   = kill.get("kill_time_in_round", None)

        survived = not died_this_round

        # T (traded): si murió, comprobar si el asesino fue eliminado en los 5000ms siguientes
        if died_this_round and my_death_time is not None:
            killer_puuid = None
            # buscar quién mató a nuestro jugador
            for ps in player_stats:
                ps_puuid_k = ps.get("player_puuid", "") or ""
                if puuid and ps_puuid_k == puuid:
                    continue
                for kill in (ps.get("kills") or []):
                    if (kill.get("victim_puuid", "") == puuid):
                        killer_puuid = ps_puuid_k
            # comprobar si el killer murió en ≤5000ms después
            if killer_puuid:
                for ps in player_stats:
                    for kill in (ps.get("kills") or []):
                        if kill.get("victim_puuid", "") == killer_puuid:
                            trade_time = kill.get("kill_time_in_round", None)
                            if trade_time is not None and my_death_time is not None:
                                if 0 <= (trade_time - my_death_time) <= 5000:
                                    traded = True

        if had_kill or had_assist or survived or traded:
            kast_rounds += 1

    # ── Métricas finales ─────────────────────────────────────────────────
    adr  = round(damage_dealt_total / max(rounds_played, 1), 2) if rounds_played else 0
    dda  = round((damage_dealt_total - damage_received_total) / max(rounds_played, 1), 2) if rounds_played else 0
    kast = round((kast_rounds / max(rounds_played, 1)) * 100, 2) if rounds_played else None
    acs  = round(score / max(rounds_played, 1), 1) if rounds_played else 0

    return {
        "rounds_played":          rounds_played,
        "damage_dealt_total":     damage_dealt_total,
        "damage_received_total":  damage_received_total,
        "kast_rounds":            kast_rounds,
        "adr":                    adr,
        "dda":                    dda,
        "kast":                   kast,
        "acs":                    acs,
    }


def analyze_matches(matches, puuid, username, tag):
    if not matches:
        return {
            "kda": 0, "winrate": 0, "trend": "➖", "hs": 0, "adr": 0, "acs": 0,
            "agent": "Desconocido", "top_agents": [], "kast": None, "dda": None,
            "rounds_played": 0, "damage_dealt_total": 0, "damage_received_total": 0, "kast_rounds": None
        }

    kills = deaths = assists = wins = 0
    headshots = bodyshots = legshots = 0
    damage = rounds = score = damage_received = 0
    kdas_history = []
    agents_played = []
    total_matches = 0
    total_kast_rounds = 0
    has_kast_data = False

    for m in matches[:10]:
        players = m.get("players", {}).get("all_players", [])
        player = find_player(players, puuid, username, tag)
        if not player:
            continue

        agent = player.get("character")
        if agent:
            agents_played.append(agent)

        stats = player.get("stats", {}) or {}
        k = stats.get("kills", 0)
        d = stats.get("deaths", 1)
        a = stats.get("assists", 0)
        hs = stats.get("headshots", 0)
        bs = stats.get("bodyshots", 0)
        ls = stats.get("legshots", 0)

        match_metrics = extract_tracker_like_match_metrics(m, player)
        r = match_metrics["rounds_played"] or 0

        kills += k
        deaths += d
        assists += a
        headshots += hs
        bodyshots += bs
        legshots += ls
        damage += match_metrics["damage_dealt_total"]
        damage_received += match_metrics["damage_received_total"]
        rounds += r
        score += (stats.get("score", 0) or 0)
        kdas_history.append((k + a) / max(d, 1))

        if get_team_win(m, player):
            wins += 1

        if match_metrics["kast_rounds"] is not None:
            total_kast_rounds += match_metrics["kast_rounds"]
            has_kast_data = True

        total_matches += 1

    if total_matches == 0:
        return {
            "kda": 0, "winrate": 0, "trend": "➖", "hs": 0, "adr": 0, "acs": 0,
            "agent": "Desconocido", "top_agents": [], "kast": None, "dda": None,
            "rounds_played": 0, "damage_dealt_total": 0, "damage_received_total": 0, "kast_rounds": None
        }

    total_shots = headshots + bodyshots + legshots
    trend = "Estable ➖"
    if len(kdas_history) >= 4:
        chronological = list(reversed(kdas_history))
        mid = len(chronological) // 2
        p1 = sum(chronological[:mid]) / mid
        p2 = sum(chronological[mid:]) / (len(chronological) - mid)
        if p2 > p1 + 0.3:
            trend = "Mejorando 📈"
        elif p2 < p1 - 0.3:
            trend = "Empeorando 📉"

    agent_counts = Counter(agents_played)
    top_agents = [agent for agent, count in agent_counts.most_common()]
    most_played = top_agents[0] if top_agents else "Desconocido"

    return {
        "kda": round((kills + assists) / max(deaths, 1), 2),
        "winrate": round((wins / total_matches) * 100, 1),
        "trend": trend,
        "hs": round((headshots / max(total_shots, 1)) * 100, 1),
        "adr": round(damage / max(rounds, 1), 2) if rounds else 0,
        "acs": round(score / max(rounds, 1), 1) if rounds else 0,
        "kast": round((total_kast_rounds / rounds) * 100, 2) if (has_kast_data and rounds) else None,
        "dda": round((damage - damage_received) / max(rounds, 1), 2) if rounds else 0,
        "rounds_played": rounds,
        "damage_dealt_total": damage,
        "damage_received_total": damage_received,
        "kast_rounds": total_kast_rounds if has_kast_data else None,
        "agent": most_played,
        "top_agents": top_agents,
    }


def obtener_stats(username, tag, region="eu"):
    key = f"{username.lower()}#{tag.lower()}"
    cached = get_cache(key)
    if cached:
        return cached, None

    headers = {"Authorization": HENRIK_API_KEY} if HENRIK_API_KEY else {}
    safe_user = urllib.parse.quote(username)
    safe_tag = urllib.parse.quote(tag)

    acc_status, acc_json = safe_get(f"https://api.henrikdev.xyz/valorant/v1/account/{safe_user}/{safe_tag}", headers)
    if acc_status == 429:
        return None, "Rate Limit (La API de Riot está saturada)"
    if acc_status == 404:
        return None, "Jugador no encontrado (Riot ID cambiado o erróneo)"
    if acc_status != 200:
        return None, f"Error cargando cuenta (HTTP {acc_status})"

    acc = acc_json.get("data", {})
    puuid = acc.get("puuid")
    real_name = acc.get("name") or username
    real_tag = acc.get("tag") or tag

    mmr_status, mmr_json = safe_get(f"https://api.henrikdev.xyz/valorant/v1/mmr/{region}/{safe_user}/{safe_tag}", headers)
    mmr_data = mmr_json.get("data", {}) if mmr_status == 200 else {}
    rank = mmr_data.get("currenttierpatched", "Unranked")
    rr = mmr_data.get("ranking_in_tier", 0)
    rank_icon = mmr_data.get("images", {}).get("large") or mmr_data.get("images", {}).get("small") or mmr_data.get("images", {}).get("triangle_down") or ""

    if puuid:
        match_url = f"https://api.henrikdev.xyz/valorant/v3/by-puuid/matches/{region}/{puuid}?size=10"
    else:
        match_url = f"https://api.henrikdev.xyz/valorant/v3/matches/{region}/{safe_user}/{safe_tag}?size=10"

    match_status, match_json = safe_get(match_url, headers)
    if match_status == 429:
        return None, "Rate Limit de Riot (Espera unos minutos)"
    if match_status == 408:
        return None, "Timeout (La API tardó demasiado en responder)"
    if match_status != 200:
        return None, f"Error cargando el historial de partidas (HTTP {match_status})"

    matches_sucias = match_json.get("data", [])
    inicio_temporada = datetime.datetime(2026, 4, 30, 3, 0, tzinfo=datetime.timezone.utc).timestamp()
    matches = []
    for m in matches_sucias:
        game_start = m.get("metadata", {}).get("game_start", 0)
        if game_start >= inicio_temporada:
            matches.append(m)

    last_match = matches[0] if matches else {}
    mapa = last_match.get("metadata", {}).get("map", "Desconocido")
    modo = last_match.get("metadata", {}).get("mode", "Desconocido")
    match_id = last_match.get("metadata", {}).get("matchid", "")

    last_match_info = {}
    if last_match:
        players = last_match.get("players", {}).get("all_players", [])
        p = find_player(players, puuid, username, tag)
        if p:
            s = p.get("stats", {}) or {}
            match_metrics = extract_tracker_like_match_metrics(last_match, p)
            won = get_team_win(last_match, p)
            hs_last = s.get("headshots", 0) or 0
            bs_last = s.get("bodyshots", 0) or 0
            ls_last = s.get("legshots", 0) or 0
            total_shots_last = hs_last + bs_last + ls_last
            last_match_info = {
                "id": match_id,
                "kills": s.get("kills", 0),
                "deaths": s.get("deaths", 1),
                "assists": s.get("assists", 0),
                "acs": match_metrics["acs"],
                "won": won,
                "agente": p.get("character", "Desconocido"),
                "rounds_played": match_metrics["rounds_played"],
                "damage_dealt_total": match_metrics["damage_dealt_total"],
                "damage_received_total": match_metrics["damage_received_total"],
                "kast_rounds": match_metrics["kast_rounds"],
                "adr": match_metrics["adr"],
                "dda": match_metrics["dda"],
                "kast": match_metrics["kast"],
                "hs": round((hs_last / max(total_shots_last, 1)) * 100, 2),
            }

    analysis = analyze_matches(matches, puuid, username, tag)
    is_smurf = (analysis["kda"] > 1.8 and analysis["winrate"] > 65 and any(r in rank.lower() for r in ["iron", "bronze", "silver", "gold"]))

    stats = {
        "nombre": real_name,
        "tag": real_tag,
        "nivel": acc.get("account_level", 0),
        "card": acc.get("card", {}).get("small", ""),
        "rank": rank,
        "rr": rr,
        "rank_icon": rank_icon,
        "mapa": mapa,
        "modo": modo,
        "kda": analysis["kda"],
        "winrate": analysis["winrate"],
        "hs": analysis["hs"],
        "adr": analysis["adr"],
        "acs": analysis["acs"],
        "kast": analysis["kast"],
        "dda": analysis["dda"],
        "rounds_played": analysis["rounds_played"],
        "damage_dealt_total": analysis["damage_dealt_total"],
        "damage_received_total": analysis["damage_received_total"],
        "kast_rounds": analysis["kast_rounds"],
        "trend": analysis["trend"],
        "smurf": is_smurf,
        "last_match": last_match_info,
        "agent": analysis.get("agent", "Desconocido"),
        "top_agents": analysis.get("top_agents", []),
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