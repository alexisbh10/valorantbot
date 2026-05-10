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
        if time.time() - ts < 300: # 5 minutos de caché
            return data
    return None

def set_cache(k, v):
    cache[k] = (v, time.time())

def safe_get(url, headers):
    try:
        r = requests.get(url, headers=headers, timeout=20)
        if not r.content:
            print(f"[safe_get] Respuesta vacía: {url}")
            return r.status_code, {}
        try:
            data = r.json()
        except Exception:
            print(f"[safe_get] JSON inválido (HTTP {r.status_code}): {r.text[:300]}")
            data = {}
        return r.status_code, data
    except requests.exceptions.Timeout:
        print(f"[safe_get] Timeout: {url}")
        return 408, {}
    except Exception as e:
        print(f"[safe_get] Error: {e}")
        return 500, {}

def analyze_matches(matches, puuid, username, tag):
    EMPTY = {"kda": 0, "winrate": 0, "trend": "➖", "hs": 0, "adr": 0, "acs": 0,
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
        # ── Encontrar al jugador en all_players ──────────────────────────────
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

        st   = player.get("stats", {})
        k    = int(st.get("kills", 0) or 0)
        d    = int(st.get("deaths", 0) or 0)
        a    = int(st.get("assists", 0) or 0)
        hs   = int(st.get("headshots", 0) or 0)
        bs   = int(st.get("bodyshots", 0) or 0)
        ls   = int(st.get("legshots", 0) or 0)
        sc   = int(st.get("score", 0) or 0)
        r    = int(m.get("metadata", {}).get("rounds_played", 1) or 1)
        my_puuid = player.get("puuid") or ""

        kills     += k
        deaths    += d
        assists   += a
        headshots += hs
        bodyshots += bs
        legshots  += ls
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

        # ── Rondas: KAST + daño hecho/recibido ───────────────────────────────
        match_rounds = m.get("rounds", [])

        if not match_rounds:
            # Sin datos de ronda: fallback con stats globales
            kast_total += r
            survived_est = max(0, r - d)
            kast_ok += min(k + a + survived_est, r)
            # Daño desde damage_made del jugador
            dmg_made = int(player.get("damage_made") or st.get("damage_made") or 0)
            damage_made_total += dmg_made
        else:
            kast_total += len(match_rounds)
            for rnd in match_rounds:
                try:
                    ps_list    = rnd.get("player_stats", [])
                    kill_events = rnd.get("kill_events", [])  # Henrik alias

                    # Encontrar el player_stats de esta ronda para nuestro jugador
                    my_ps = None
                    for ps in ps_list:
                        if (my_puuid and ps.get("player_puuid") == my_puuid) or (
                            str(ps.get("player_display_name") or "").split("#")[0].lower() == username.lower()
                        ):
                            my_ps = ps
                            break

                    # Sin datos de ronda para este jugador → no contabilizar
                    if my_ps is None:
                        kast_total -= 1
                        continue

                    # ── Daño hecho (mis entradas damage[]) ───────────────────
                    for dmg in (my_ps.get("damage") or []):
                        damage_made_total += int(dmg.get("damage", 0) or 0)

                    # ── Daño recibido (busco en otros player_stats donde receiver == yo)
                    for other_ps in ps_list:
                        if other_ps is my_ps:
                            continue
                        for dmg in (other_ps.get("damage") or []):
                            recv = dmg.get("receiver_puuid") or ""
                            recv_name = str(dmg.get("receiver_display_name") or "").split("#")[0].lower()
                            if (my_puuid and recv == my_puuid) or recv_name == username.lower():
                                damage_received_total += int(dmg.get("damage", 0) or 0)

                    # ── KAST ─────────────────────────────────────────────────
                    # Kills de esta ronda (lista de objetos kill en my_ps)
                    my_kills_rnd = my_ps.get("kills") or []
                    rnd_k = len(my_kills_rnd) if isinstance(my_kills_rnd, list) else int(my_kills_rnd or 0)

                    # Todos los kills de la ronda (para A, S, T)
                    # Henrik v3: kill objects están en my_ps["kills"] de CADA jugador
                    all_kills_rnd = []
                    for ps in ps_list:
                        raw = ps.get("kills") or []
                        if isinstance(raw, list):
                            all_kills_rnd.extend(raw)

                    # A: aparezco en assistants de cualquier kill
                    rnd_a = sum(
                        1 for ke in all_kills_rnd
                        if any(
                            (my_puuid and str(ast) == my_puuid) or
                            str(ast).split("#")[0].lower() == username.lower()
                            for ast in (ke.get("assistants") or [])
                            if ast
                        )
                    )

                    # S: no aparezco como victim
                    survived = not any(
                        (my_puuid and ke.get("victim_puuid") == my_puuid) or
                        str(ke.get("victim_display_name") or "").split("#")[0].lower() == username.lower()
                        for ke in all_kills_rnd
                    )

                    # T: morí pero alguien mató a mi asesino en ≤5s
                    traded = False
                    if not survived:
                        my_death = next(
                            (ke for ke in all_kills_rnd if
                             (my_puuid and ke.get("victim_puuid") == my_puuid) or
                             str(ke.get("victim_display_name") or "").split("#")[0].lower() == username.lower()),
                            None
                        )
                        if my_death:
                            killer = my_death.get("killer_puuid", "")
                            t0     = int(my_death.get("kill_time_in_round") or 0)
                            traded = any(
                                ke.get("victim_puuid") == killer and
                                abs(int(ke.get("kill_time_in_round") or 0) - t0) <= 5000
                                for ke in all_kills_rnd
                            )

                    if rnd_k > 0 or rnd_a > 0 or survived or traded:
                        kast_ok += 1

                except Exception as e:
                    print(f"[KAST] Error ronda: {e}")
                    continue

        total_matches += 1

    if total_matches == 0:
        return EMPTY

    total_shots = headshots + bodyshots + legshots

    trend = "Estable ➖"
    if len(kdas_history) >= 4:
        chron = list(reversed(kdas_history))
        mid = len(chron) // 2
        p1 = sum(chron[:mid]) / mid
        p2 = sum(chron[mid:]) / (len(chron) - mid)
        if p2 > p1 + 0.3:   trend = "Mejorando 📈"
        elif p2 < p1 - 0.3: trend = "Empeorando 📉"

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
    rank_icon = mmr_data.get("images", {}).get("small", "")

    # 3. OBTIENE EL HISTORIAL
    if puuid:
        match_url = f"https://api.henrikdev.xyz/valorant/v3/by-puuid/matches/{region}/{puuid}?size=10"
    else:
        match_url = f"https://api.henrikdev.xyz/valorant/v3/matches/{region}/{safe_user}/{safe_tag}?size=10"

    match_status, match_json = safe_get(match_url, headers)
    
    if match_status == 429: return None, "Rate Limit de Riot (Espera unos minutos)"
    if match_status == 408: return None, "Timeout (La API tardó demasiado en responder)"
    if match_status != 200: return None, f"Error cargando el historial de partidas (HTTP {match_status})"

    matches_sucias = match_json.get("data", [])

    # 🔥 FILTRO DE NUEVA TEMPORADA 🔥
    # 30 de abril de 2026 a las 05:00 CEST (que son las 03:00 UTC)
    inicio_temporada = datetime.datetime(2026, 4, 30, 3, 0, tzinfo=datetime.timezone.utc).timestamp()
    
    matches = []
    for m in matches_sucias:
        game_start = m.get("metadata", {}).get("game_start", 0)
        # Solo dejamos pasar las partidas que ocurrieron después del parche
        if game_start >= inicio_temporada:
            matches.append(m)

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
        "rank_icon": rank_icon,
        "rr": rr,
        "mapa": mapa,
        "modo": modo,
        "kda": analysis["kda"],
        "winrate": analysis["winrate"],
        "hs": analysis["hs"],
        "adr": analysis["adr"],
        "acs": analysis["acs"],
        "kast": analysis.get("kast", 0),
        "damage_delta": analysis.get("damage_delta", 0),
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