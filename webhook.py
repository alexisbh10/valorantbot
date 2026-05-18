import requests
import os
import time
import urllib.parse
import traceback
from fastapi import FastAPI, HTTPException, Request
from collections import Counter
import datetime
import asyncpg
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

HENRIK_API_KEY = os.getenv("HENRIK_API_KEY", "")
cache = {}

DB_POOL = None

async def get_db():
    global DB_POOL
    if DB_POOL is None:
        DB_POOL = await asyncpg.create_pool(os.getenv("DATABASE_URL"))
    return DB_POOL

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
        p_name  = p.get("name", "")
        p_tag   = p.get("tag", "")
        if (puuid and p_puuid == puuid) or \
           (p_name.lower() == username.lower() and p_tag.lower() == tag.lower()):
            return p
    return None

def get_team_win(match, player):
    team  = (player.get("team") or "").lower()
    teams = match.get("teams", {}) or {}
    if team and isinstance(teams, dict):
        return teams.get(team, {}).get("has_won", False)
    return False

def extract_tracker_like_match_metrics(match, player):
    try:
        stats         = player.get("stats", {}) or {}
        metadata      = match.get("metadata", {}) or {}
        all_rounds    = match.get("rounds") or []
        
        rounds_played = metadata.get("rounds_played") or metadata.get("rounds") or len(all_rounds) or 1
        score         = stats.get("score", 0) or 0
        
        puuid  = player.get("puuid", "") or ""
        p_name = player.get("name", "").lower()

        damage_dealt_total    = 0
        damage_received_total = 0
        kast_rounds           = 0

        for rnd in all_rounds:
            player_stats = rnd.get("player_stats") or []

            my_ps = None
            for ps in player_stats:
                ps_puuid = ps.get("player_puuid", "") or ""
                if puuid and ps_puuid == puuid:
                    my_ps = ps
                    break
                if not puuid:
                    name_check = (ps.get("player_display_name") or "").lower()
                    if p_name and p_name in name_check:
                        my_ps = ps
                        break

            if my_ps is None:
                continue

            # ADR: La API usa damage_events
            for dmg in (my_ps.get("damage_events") or []):
                damage_dealt_total += int(dmg.get("damage", 0) or 0)

            # DDA: La API usa damage_events
            for ps in player_stats:
                ps_puuid_other = ps.get("player_puuid", "") or ""
                if puuid and ps_puuid_other == puuid:
                    continue
                for dmg in (ps.get("damage_events") or []):
                    receiver = dmg.get("receiver_puuid", "") or ""
                    if puuid and receiver == puuid:
                        damage_received_total += int(dmg.get("damage", 0) or 0)

            # KAST
            my_kills   = my_ps.get("kills", 0)
            my_assists = my_ps.get("assists", 0)
            had_kill   = my_kills > 0
            had_assist = my_assists > 0

            died_this_round = False
            my_death_time   = None
            killer_puuid    = None

            for ps in player_stats:
                ps_puuid_other = ps.get("player_puuid", "") or ""
                if puuid and ps_puuid_other == puuid:
                    continue
                # La API usa kill_events para el array de kills
                for kill in (ps.get("kill_events") or []):
                    if (kill.get("victim_puuid", "") or "") == puuid:
                        died_this_round = True
                        my_death_time   = kill.get("kill_time_in_round")
                        killer_puuid    = ps_puuid_other

            survived = not died_this_round

            traded = False
            if died_this_round and my_death_time is not None and killer_puuid:
                for ps in player_stats:
                    for kill in (ps.get("kill_events") or []):
                        if (kill.get("victim_puuid", "") or "") == killer_puuid:
                            trade_time = kill.get("kill_time_in_round")
                            if trade_time is not None and 0 <= (trade_time - my_death_time) <= 5000:
                                traded = True

            if had_kill or had_assist or survived or traded:
                kast_rounds += 1

        has_round_data = len(all_rounds) > 0
        
        adr  = round(damage_dealt_total / rounds_played, 2) if has_round_data else None
        dda  = round((damage_dealt_total - damage_received_total) / rounds_played, 2) if has_round_data else None
        kast = round((kast_rounds / rounds_played) * 100, 2) if has_round_data else None
        acs  = round(score / rounds_played, 1) if rounds_played else 0

        return {
            "rounds_played":         rounds_played,
            "damage_dealt_total":    damage_dealt_total if has_round_data else None,
            "damage_received_total": damage_received_total if has_round_data else None,
            "kast_rounds":           kast_rounds if has_round_data else None,
            "adr":                   adr,
            "dda":                   dda,
            "kast":                  kast,
            "acs":                   acs,
        }

    except Exception as e:
        print(f"[extract_metrics ERROR] {e}\n{traceback.format_exc()}")
        return {
            "rounds_played": 1, "damage_dealt_total": None,
            "damage_received_total": None, "kast_rounds": None,
            "adr": None, "dda": None, "kast": None, "acs": 0,
        }

def analyze_matches(matches, puuid, username, tag):
    if not matches:
        return {
            "kda": 0, "winrate": 0, "trend": "➖", "hs": 0, "adr": 0, "acs": 0,
            "agent": "Desconocido", "top_agents": [], "kast": None, "dda": None,
            "rounds_played": 0, "damage_dealt_total": 0,
            "damage_received_total": 0, "kast_rounds": None,
        }

    kills = deaths = assists = wins = 0
    headshots = bodyshots = legshots = 0
    damage = rounds = score = damage_received = 0
    kdas_history  = []
    agents_played = []
    total_matches = 0
    total_kast_rounds = 0
    has_kast_data = False

    for m in matches[:10]:
        try:
            players = m.get("players", {}).get("all_players", [])
            player  = find_player(players, puuid, username, tag)
            if not player:
                continue

            agent = player.get("character")
            if agent:
                agents_played.append(agent)

            stats = player.get("stats", {}) or {}
            k  = stats.get("kills", 0)   or 0
            d  = stats.get("deaths", 1)  or 1
            a  = stats.get("assists", 0) or 0
            hs = stats.get("headshots", 0) or 0
            bs = stats.get("bodyshots", 0) or 0
            ls = stats.get("legshots", 0)  or 0

            # ¡ESTA ES LA LÍNEA QUE SE HABÍA BORRADO!
            match_metrics = extract_tracker_like_match_metrics(m, player)
            r = match_metrics["rounds_played"] or 0

            kills     += k
            deaths    += d
            assists   += a
            headshots += hs
            bodyshots += bs
            legshots  += ls
            
            # Sumamos el daño de forma segura
            if match_metrics["damage_dealt_total"] is not None:
                damage += match_metrics["damage_dealt_total"]
            if match_metrics["damage_received_total"] is not None:
                damage_received += match_metrics["damage_received_total"]
                
            rounds += r
            score  += (stats.get("score", 0) or 0)
            kdas_history.append((k + a) / max(d, 1))

            if get_team_win(m, player):
                wins += 1

            if match_metrics["kast_rounds"] is not None:
                total_kast_rounds += match_metrics["kast_rounds"]
                has_kast_data = True

            total_matches += 1

        except Exception as e:
            print(f"[analyze_matches ERROR en partida] {e}\n{traceback.format_exc()}")
            continue

    if total_matches == 0:
        return {
            "kda": 0, "winrate": 0, "trend": "➖", "hs": 0, "adr": 0, "acs": 0,
            "agent": "Desconocido", "top_agents": [], "kast": None, "dda": None,
            "rounds_played": 0, "damage_dealt_total": 0,
            "damage_received_total": 0, "kast_rounds": None,
        }

    total_shots = headshots + bodyshots + legshots
    trend = "Estable ➖"
    if len(kdas_history) >= 4:
        chronological = list(reversed(kdas_history))
        mid = len(chronological) // 2
        p1  = sum(chronological[:mid]) / mid
        p2  = sum(chronological[mid:]) / (len(chronological) - mid)
        if p2 > p1 + 0.3:
            trend = "Mejorando 📈"
        elif p2 < p1 - 0.3:
            trend = "Empeorando 📉"

    agent_counts = Counter(agents_played)
    top_agents   = [agent for agent, _ in agent_counts.most_common()]
    most_played  = top_agents[0] if top_agents else "Desconocido"

    return {
        "kda":     round((kills + assists) / max(deaths, 1), 2),
        "winrate": round((wins / total_matches) * 100, 1),
        "trend":   trend,
        "hs":      round((headshots / max(total_shots, 1)) * 100, 1) if total_shots else 0,
        "adr":     round(damage / max(rounds, 1), 2) if rounds else 0,
        "acs":     round(score  / max(rounds, 1), 1) if rounds else 0,
        "kast":    round((total_kast_rounds / rounds) * 100, 2) if (has_kast_data and rounds) else None,
        "dda":     round((damage - damage_received) / max(rounds, 1), 2) if rounds else 0,
        "rounds_played":         rounds,
        "damage_dealt_total":    damage,
        "damage_received_total": damage_received,
        "kast_rounds":           total_kast_rounds if has_kast_data else None,
        "agent":      most_played,
        "top_agents": top_agents,
    }

def obtener_stats(username, tag, region="eu"):
    key    = f"{username.lower()}#{tag.lower()}"
    cached = get_cache(key)
    if cached:
        return cached, None

    headers  = {"Authorization": HENRIK_API_KEY} if HENRIK_API_KEY else {}
    safe_user = urllib.parse.quote(username)
    safe_tag  = urllib.parse.quote(tag)

    acc_status, acc_json = safe_get(
        f"https://api.henrikdev.xyz/valorant/v1/account/{safe_user}/{safe_tag}", headers
    )
    if acc_status == 429:
        return None, "Rate Limit (La API de Riot está saturada)"
    if acc_status == 404:
        return None, "Jugador no encontrado (Riot ID cambiado o erróneo)"
    if acc_status != 200:
        return None, f"Error cargando cuenta (HTTP {acc_status})"

    acc       = acc_json.get("data", {})
    puuid     = acc.get("puuid")
    real_name = acc.get("name") or username
    real_tag  = acc.get("tag")  or tag

    mmr_status, mmr_json = safe_get(
        f"https://api.henrikdev.xyz/valorant/v1/mmr/{region}/{safe_user}/{safe_tag}", headers
    )
    mmr_data  = mmr_json.get("data", {}) if mmr_status == 200 else {}
    rank      = mmr_data.get("currenttierpatched", "Unranked")
    rr        = mmr_data.get("ranking_in_tier", 0)
    rank_icon = (
        mmr_data.get("images", {}).get("large") or
        mmr_data.get("images", {}).get("small") or
        mmr_data.get("images", {}).get("triangle_down") or ""
    )

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

    matches_sucias   = match_json.get("data", []) or []
    inicio_temporada = datetime.datetime(2026, 4, 30, 3, 0, tzinfo=datetime.timezone.utc).timestamp()
    matches = [
        m for m in matches_sucias
        if (m.get("metadata", {}) or {}).get("game_start", 0) >= inicio_temporada
    ]

    last_match   = matches[0] if matches else {}
    mapa         = (last_match.get("metadata") or {}).get("map",  "Desconocido")
    modo         = (last_match.get("metadata") or {}).get("mode", "Desconocido")
    match_id     = (last_match.get("metadata") or {}).get("matchid", "")

    last_match_info = {}
    if last_match:
        players = last_match.get("players", {}).get("all_players", [])
        p = find_player(players, puuid, username, tag)
        if p:
            try:
                s             = p.get("stats", {}) or {}
                match_metrics = extract_tracker_like_match_metrics(last_match, p)
                won           = get_team_win(last_match, p)
                hs_last       = s.get("headshots", 0) or 0
                bs_last       = s.get("bodyshots",  0) or 0
                ls_last       = s.get("legshots",   0) or 0
                total_shots_last = hs_last + bs_last + ls_last
                last_match_info = {
                    "id":                   match_id,
                    "kills":                s.get("kills",   0),
                    "deaths":               s.get("deaths",  1),
                    "assists":              s.get("assists", 0),
                    "acs":                  match_metrics["acs"],
                    "won":                  won,
                    "agente":               p.get("character", "Desconocido"),
                    "rounds_played":        match_metrics["rounds_played"],
                    "damage_dealt_total":   match_metrics["damage_dealt_total"],
                    "damage_received_total":match_metrics["damage_received_total"],
                    "kast_rounds":          match_metrics["kast_rounds"],
                    "adr":                  match_metrics["adr"],
                    "dda":                  match_metrics["dda"],
                    "kast":                 match_metrics["kast"],
                    "hs":                   round((hs_last / max(total_shots_last, 1)) * 100, 2),
                }
            except Exception as e:
                print(f"[last_match_info ERROR] {e}\n{traceback.format_exc()}")

    analysis = analyze_matches(matches, puuid, username, tag)
    is_smurf = (
        analysis["kda"] > 1.8 and
        analysis["winrate"] > 65 and
        any(r in rank.lower() for r in ["iron", "bronze", "silver", "gold"])
    )

    stats = {
        "nombre":                real_name,
        "tag":                   real_tag,
        "nivel":                 acc.get("account_level", 0),
        "card":                  (acc.get("card") or {}).get("small", ""),
        "rank":                  rank,
        "rr":                    rr,
        "rank_icon":             rank_icon,
        "mapa":                  mapa,
        "modo":                  modo,
        "kda":                   analysis["kda"],
        "winrate":               analysis["winrate"],
        "hs":                    analysis["hs"],
        "adr":                   analysis["adr"],
        "acs":                   analysis["acs"],
        "kast":                  analysis["kast"],
        "dda":                   analysis["dda"],
        "rounds_played":         analysis["rounds_played"],
        "damage_dealt_total":    analysis["damage_dealt_total"],
        "damage_received_total": analysis["damage_received_total"],
        "kast_rounds":           analysis["kast_rounds"],
        "trend":                 analysis["trend"],
        "smurf":                 is_smurf,
        "last_match":            last_match_info,
        "agent":                 analysis.get("agent",      "Desconocido"),
        "top_agents":            analysis.get("top_agents", []),
    }

    set_cache(key, stats)
    return stats, None

@app.post("/tracker")
async def tracker(request: Request):
    try:
        body     = await request.json()
        username = body.get("username")
        tag      = body.get("tag")
        region   = body.get("region", "eu")

        if not username or not tag:
            raise HTTPException(status_code=400, detail="Falta username o tag")

        stats, err = obtener_stats(username, tag, region)
        if err:
            return {"success": False, "error": err}
        return {"success": True, "stats": stats}

    except HTTPException:
        raise
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[/tracker ERROR] {e}\n{tb}")
        return {"success": False, "error": f"Error interno del webhook: {e}"}
    

# ─── ADMIN ROUTES ───────────────────────────────────────────
@app.get("/admin/jugadores")
async def admin_get_jugadores(secret: str = ""):
    if secret != os.getenv("ADMIN_SECRET", ""):
        raise HTTPException(status_code=403, detail="Forbidden")
    db = await get_db()
    rows = await db.fetch("SELECT * FROM jugadores ORDER BY id")
    return [dict(r) for r in rows]

@app.put("/admin/jugadores/{jugador_id}")
async def admin_update_jugador(jugador_id: int, req: Request, secret: str = ""):
    if secret != os.getenv("ADMIN_SECRET", ""):
        raise HTTPException(status_code=403, detail="Forbidden")
    b = await req.json()
    db = await get_db()
    await db.execute(
        "UPDATE jugadores SET nombre=$1, tag=$2, ultimo_rango=$3 WHERE id=$4",
        b["nombre"], b["tag"], b.get("ultimo_rango"), jugador_id
    )

    return {"ok": True}

@app.get("/admin/partidas")
async def admin_get_partidas(jugador: str = "", modo: str = "", secret: str = ""):
    if secret != os.getenv("ADMIN_SECRET", ""):
        raise HTTPException(status_code=403, detail="Forbidden")
    db = await get_db()
    q = "SELECT * FROM partidas WHERE 1=1"
    params = []
    if jugador:
        params.append(f"%{jugador}%")
        q += f" AND jugador_nombre ILIKE ${len(params)}"
    if modo:
        params.append(modo)
        q += f" AND modo = ${len(params)}"
    q += " ORDER BY fecha DESC LIMIT 200"
    rows = await db.fetch(q, *params)
    return [dict(r) for r in rows]

@app.put("/admin/partidas/{match_id}/{nombre}/{tag}")
async def admin_update_partida(match_id: str, nombre: str, tag: str, req: Request, secret: str = ""):
    if secret != os.getenv("ADMIN_SECRET", ""):
        raise HTTPException(status_code=403, detail="Forbidden")
    b = await req.json()
    db = await get_db()
    await db.execute("""
        UPDATE partidas SET
            kills=$1, deaths=$2, assists=$3, acs=$4, won=$5,
            mapa=$6, modo=$7, agente=$8,
            adr=$9, kast=$10, dda=$11,
            rounds_played=$12, damage_dealt_total=$13,
            damage_received_total=$14, kast_rounds=$15, hs=$16
        WHERE match_id=$17 AND jugador_nombre=$18 AND jugador_tag=$19
    """,
        b.get("kills"), b.get("deaths"), b.get("assists"),
        b.get("acs"), b.get("won"),
        b.get("mapa"), b.get("modo"), b.get("agente"),
        b.get("adr"), b.get("kast"), b.get("dda"),
        b.get("rounds_played"), b.get("damage_dealt_total"),
        b.get("damage_received_total"), b.get("kast_rounds"), b.get("hs"),
        match_id, nombre, tag
    )
    return {"ok": True}

@app.delete("/admin/partidas/{match_id}/{nombre}/{tag}")
async def admin_delete_partida(match_id: str, nombre: str, tag: str, secret: str = ""):
    if secret != os.getenv("ADMIN_SECRET", ""):
        raise HTTPException(status_code=403, detail="Forbidden")
    db = await get_db()
    await db.execute(
        "DELETE FROM partidas WHERE match_id=$1 AND jugador_nombre=$2 AND jugador_tag=$3",
        match_id, nombre, tag)
    return {"ok": True}