import discord
from discord.ext import commands
from discord.ext import tasks
import requests
import os
import logging
import asyncio
import urllib.parse
import asyncpg
import io
from PIL import Image, ImageDraw, ImageFont
from dotenv import load_dotenv
from discord import app_commands

MODOS_DISCORD = [
    app_commands.Choice(name="Competitivo (Ranked 5v5)", value="Competitive"),
    app_commands.Choice(name="Skirmish (1v1)", value="Skirmish 1v1"),
    app_commands.Choice(name="Skirmish (2v2)", value="Skirmish 2v2"),
    app_commands.Choice(name="No Competitivo (Unrated)", value="Unrated"),
    app_commands.Choice(name="Swiftplay", value="Swiftplay"),
    app_commands.Choice(name="Todos los modos", value="%")
]

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
TRACKER_URL = os.getenv("TRACKER_URL", "http://localhost:8000")
DATABASE_URL = os.getenv("DATABASE_URL")

logging.basicConfig(level=logging.INFO)
bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
CANAL_ALERTAS_ID = 1496883989867139102


def _load_fonts():
    try:
        return (
            lambda s: ImageFont.truetype("assets/fonts/Inter-SemiBold.ttf", s),
            lambda s: ImageFont.truetype("assets/fonts/Inter-Regular.ttf", s),
            lambda s: ImageFont.truetype("assets/fonts/Inter-Medium.ttf", s),
        )
    except Exception:
        f = ImageFont.load_default()
        return lambda s: f, lambda s: f, lambda s: f

_FB, _FR, _FM = _load_fonts()


def _rank_palette(rank):
    r = (rank or "").lower()
    palettes = {
        "radiant": ((255, 228, 80), (255, 200, 30)),
        "immortal": ((220, 70, 100), (180, 30, 65)),
        "ascendant": ((55, 210, 130), (20, 155, 80)),
        "diamond": ((170, 105, 240), (100, 45, 195)),
        "platinum": ((75, 185, 235), (30, 115, 185)),
        "gold": ((240, 190, 55), (190, 135, 20)),
        "silver": ((195, 195, 205), (130, 130, 145)),
        "bronze": ((200, 125, 55), (140, 80, 20)),
        "iron": ((115, 115, 120), (70, 70, 75)),
    }
    for key, pal in palettes.items():
        if key in r:
            return pal
    return ((255, 70, 85), (200, 20, 40))


def _safe_float(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _safe_int(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _calc_tracker_metrics_from_stats(s):
    lm = s.get("last_match", {}) or {}
    rounds_played = _safe_int(s.get("rounds_played") or s.get("rounds") or lm.get("rounds_played") or lm.get("rounds"))
    damage_dealt_total = _safe_int(s.get("damage_dealt_total") or s.get("damage_dealt") or s.get("damage_done") or lm.get("damage_dealt_total") or lm.get("damage_dealt") or lm.get("damage_done"))
    damage_received_total = _safe_int(s.get("damage_received_total") or s.get("damage_received") or lm.get("damage_received_total") or lm.get("damage_received"))
    kast_rounds = _safe_int(s.get("kast_rounds") or lm.get("kast_rounds"))

    adr = round(damage_dealt_total / rounds_played, 2) if rounds_played > 0 and damage_dealt_total > 0 else (round(_safe_float(s.get("adr") or lm.get("adr")), 2) if (s.get("adr") is not None or lm.get("adr") is not None) else None)
    dda = round((damage_dealt_total - damage_received_total) / rounds_played, 2) if rounds_played > 0 and (damage_dealt_total or damage_received_total) else (round(_safe_float(s.get("damage_delta") or s.get("dda") or lm.get("damage_delta") or lm.get("dda")), 2) if (s.get("damage_delta") is not None or s.get("dda") is not None or lm.get("damage_delta") is not None or lm.get("dda") is not None) else None)
    kast = round((kast_rounds / rounds_played) * 100, 2) if rounds_played > 0 and kast_rounds > 0 else (round(_safe_float(s.get("kast") or lm.get("kast")), 2) if (s.get("kast") is not None or lm.get("kast") is not None) else None)
    hs_raw = lm.get("hs") if lm.get("hs") is not None else s.get("hs")
    hs_value = round(_safe_float(hs_raw), 2) if hs_raw is not None else None

    return {
        "rounds_played": rounds_played or None,
        "damage_dealt_total": damage_dealt_total or None,
        "damage_received_total": damage_received_total or None,
        "kast_rounds": kast_rounds or None,
        "adr": adr,
        "dda": dda,
        "kast": kast,
        "hs": hs_value,
    }


def generar_tarjeta(s, modo_display, tiene_datos_db, db_stats, top_agents_db):
    acc1, acc2 = _rank_palette(s.get("rank", ""))
    W, H = 1180, 680
    PAD = 40

    TEXT = (244, 247, 252, 255)
    MUTED = (170, 178, 194, 255)
    FAINT = (255, 255, 255, 26)
    POS = (92, 224, 152, 255)
    NEG = (239, 106, 106, 255)

    def mix(c1, c2, t):
        return tuple(int(c1[i] * (1 - t) + c2[i] * t) for i in range(3))

    def text(x, y, value, font, fill, anchor=None):
        draw.text((x, y), str(value), font=font, fill=fill, anchor=anchor)

    def fmt_num(v, digits=1, suffix=""):
        if v is None:
            return "—"
        try:
            return f"{round(float(v), digits)}{suffix}"
        except Exception:
            return f"{v}{suffix}"

    def soft_badge(x1, y1, x2, y2, fill, outline=None):
        draw.rounded_rectangle([x1, y1, x2, y2], radius=18, fill=fill, outline=outline, width=1)

    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    top_bg = mix(acc1, (10, 12, 18), 0.68)
    bottom_bg = mix(acc2, (4, 6, 10), 0.84)
    for y in range(H):
        t = y / max(H - 1, 1)
        c = mix(top_bg, bottom_bg, t)
        draw.line([(0, y), (W, y)], fill=(*c, 255), width=1)

    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((-220, -160, 340, 320), fill=(*acc1, 34))
    gd.ellipse((W - 380, H - 320, W + 120, H + 120), fill=(*acc2, 28))
    img = Image.alpha_composite(img, glow)
    draw = ImageDraw.Draw(img)

    draw.line((PAD, 126, W - PAD, 126), fill=(255, 255, 255, 34), width=1)
    draw.line((PAD, 248, W - PAD, 248), fill=(255, 255, 255, 24), width=1)

    try:
        icon_url = s.get("rank_icon") or s.get("rankIcon") or ""
        if icon_url:
            ri_data = requests.get(icon_url, timeout=6)
            ri = Image.open(io.BytesIO(ri_data.content)).convert("RGBA").resize((86, 86))
            img.paste(ri, (PAD, 24), ri)
    except Exception:
        pass

    header_x = PAD + 104
    text(header_x, 26, f"{s.get('nombre', '?')}#{s.get('tag', '?')}", _FB(38), TEXT)
    text(header_x, 72, f"{s.get('rank', 'Unranked')} · {s.get('rr', 0)} RR · Nivel {s.get('nivel', '?')}", _FM(20), MUTED)
    text(header_x, 102, modo_display, _FR(16), MUTED)

    text(W - PAD, 34, "VALORANT STATS", _FB(18), TEXT, anchor="ra")
    text(W - PAD, 76, s.get("trend", "Estable"), _FM(16), MUTED, anchor="ra")

    metrics = [
        ("KDA", fmt_num(s.get("kda"), 2), None),
        ("ACS", fmt_num(db_stats.get("acs_medio") if tiene_datos_db else s.get("acs"), 1), None),
        ("HS", fmt_num(db_stats.get("hs_medio") if tiene_datos_db else s.get("hs"), 1, "%"), None),
        ("WR", fmt_num(db_stats.get("winrate") if tiene_datos_db else s.get("winrate"), 1, "%"),
         POS if float(db_stats.get("winrate") or s.get("winrate") or 0) >= 50 else NEG),
        ("ADR", fmt_num(db_stats.get("adr_medio") if tiene_datos_db else s.get("adr"), 1), None),
    ]

    col_w = (W - PAD * 2) // 5
    for i, (label, value, accent) in enumerate(metrics):
        x = PAD + i * col_w
        text(x, 154, label, _FM(15), MUTED)
        text(x, 188, value, _FB(30), accent or TEXT)
        draw.line((x, 232, x + col_w - 20, 232), fill=(255, 255, 255, 26), width=1)

    left_x = PAD
    right_x = 610
    base_y = 286

    text(left_x, base_y, "Resumen", _FB(26), TEXT)
    played = db_stats.get("total_matches", 0) if tiene_datos_db else 0
    text(left_x, base_y + 44, f"Partidas analizadas: {played}", _FR(17), MUTED)

    pairs = [
        ("KAST", fmt_num(db_stats.get("kast_medio"), 1, "%") if tiene_datos_db else "—"),
        ("DDA", fmt_num(db_stats.get("dda_medio"), 1) if tiene_datos_db else "—"),
        ("Main agent", (db_stats.get("main_agent") or s.get("agent") or "Desconocido") if isinstance(db_stats, dict) else (s.get("agent") or "Desconocido")),
        ("Mapa", s.get("mapa", "Desconocido")),
    ]

    y0 = base_y + 108
    for idx, (lab, val) in enumerate(pairs):
        y = y0 + idx * 60
        text(left_x, y, lab, _FM(16), MUTED)
        text(left_x + 190, y - 1, val, _FB(19), TEXT)
        if idx < len(pairs) - 1:
            draw.line((left_x, y + 34, 540, y + 34), fill=FAINT, width=1)

    lm = s.get("last_match", {}) or {}
    text(right_x, base_y, "Última partida", _FB(26), TEXT)
    text(right_x, base_y + 46, f"{lm.get('kills', 0)}/{lm.get('deaths', 0)}/{lm.get('assists', 0)}", _FB(38), TEXT)
    text(
        right_x,
        base_y + 94,
        f"ACS {fmt_num(lm.get('acs'),1)} · HS {fmt_num(lm.get('hs'),1,'%')} · ADR {fmt_num(lm.get('adr'),1)}",
        _FR(17),
        MUTED
    )
    result_text = "Victoria" if lm.get("won") else "Derrota"
    result_color = POS if lm.get("won") else NEG
    text(W - PAD, base_y + 52, result_text, _FB(26), result_color, anchor="ra")

    draw.line((right_x, base_y + 140, W - PAD, base_y + 140), fill=FAINT, width=1)

    text(right_x, base_y + 180, "Lineups / agentes", _FB(26), TEXT)

    agents = top_agents_db[:5] if top_agents_db else (s.get("top_agents") or [])[:5]
    agents = [a for a in agents if a]
    if not agents:
        agents = [s.get("agent", "Desconocido")]

    badge_x = right_x
    badge_y = base_y + 228
    row_limit = W - PAD - 20

    for ag in agents:
        w = max(120, 30 + int(len(ag) * 11))
        if badge_x + w > row_limit:
            badge_x = right_x
            badge_y += 52

        fill_col = (*mix(acc1, (255, 255, 255), 0.45), 82)
        soft_badge(badge_x, badge_y, badge_x + w, badge_y + 40, fill_col, outline=(255, 255, 255, 56))
        text(badge_x + 14, badge_y + 9, ag, _FM(16), TEXT)
        badge_x += w + 10

    text(right_x, H - 46, "Los setups completos siguen también en el embed", _FR(14), (220, 224, 232, 210))

    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf


@bot.event
async def on_ready():
    if not hasattr(bot, "db") or bot.db is None:
        bot.db = await asyncpg.create_pool(DATABASE_URL)
        print("✅ Bot conectado a PostgreSQL")
    print("🛠️ Verificando estructura de la base de datos...")
    await bot.db.execute("""
        CREATE TABLE IF NOT EXISTS jugadores (
            id SERIAL PRIMARY KEY,
            server_id VARCHAR(50) NOT NULL,
            nombre VARCHAR(50) NOT NULL,
            tag VARCHAR(10) NOT NULL,
            UNIQUE (server_id, nombre, tag)
        );

        CREATE TABLE IF NOT EXISTS partidas (
            match_id VARCHAR(100) NOT NULL,
            jugador_nombre VARCHAR(50) NOT NULL,
            jugador_tag VARCHAR(10) NOT NULL,
            kills INTEGER,
            deaths INTEGER,
            assists INTEGER,
            acs INTEGER,
            won BOOLEAN,
            mapa VARCHAR(50),
            modo VARCHAR(50),
            agente VARCHAR(50) DEFAULT 'Desconocido',
            adr NUMERIC(6,2),
            kast NUMERIC(5,2),
            dda NUMERIC(6,2),
            rounds_played INTEGER,
            damage_dealt_total INTEGER,
            damage_received_total INTEGER,
            kast_rounds INTEGER,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (match_id, jugador_nombre, jugador_tag)
        );
    """)
    await bot.db.execute("ALTER TABLE partidas ADD COLUMN IF NOT EXISTS adr NUMERIC(6,2);")
    await bot.db.execute("ALTER TABLE partidas ADD COLUMN IF NOT EXISTS kast NUMERIC(5,2);")
    await bot.db.execute("ALTER TABLE partidas ADD COLUMN IF NOT EXISTS dda NUMERIC(6,2);")
    await bot.db.execute("ALTER TABLE partidas ADD COLUMN IF NOT EXISTS rounds_played INTEGER;")
    await bot.db.execute("ALTER TABLE partidas ADD COLUMN IF NOT EXISTS damage_dealt_total INTEGER;")
    await bot.db.execute("ALTER TABLE partidas ADD COLUMN IF NOT EXISTS damage_received_total INTEGER;")
    await bot.db.execute("ALTER TABLE partidas ADD COLUMN IF NOT EXISTS kast_rounds INTEGER;")
    await bot.db.execute("ALTER TABLE jugadores ADD COLUMN IF NOT EXISTS ultimo_rango VARCHAR(30);")
    await bot.db.execute("ALTER TABLE partidas ADD COLUMN IF NOT EXISTS hs NUMERIC(5,2);")
    print("✅ Base de datos lista y estructurada.")
    print(f"✅ Bot listo en Discord: {bot.user}")
    try:
        guild_id = os.getenv("DISCORD_GUILD_ID")
        if guild_id:
            guild_obj = discord.Object(id=int(guild_id))
            synced = await bot.tree.sync(guild=guild_obj)
            print(f"✅ Slash commands sincronizados en guild {guild_id}: {len(synced)}")
        else:
            synced = await bot.tree.sync()
            print(f"✅ Slash commands sincronizados globalmente: {len(synced)}")
    except Exception as e:
        print(f"❌ Error sincronizando slash commands: {e}")
    if not vigilante_partidas.is_running():
        vigilante_partidas.start()
    if not resumen_semanal.is_running():
        resumen_semanal.start()


@tasks.loop(minutes=5)
async def vigilante_partidas():
    await bot.wait_until_ready()
    try:
        canal = await bot.fetch_channel(CANAL_ALERTAS_ID)
    except Exception:
        print("⚠️ ERROR: No se puede encontrar el canal de alertas.")
        return

    jugadores = await bot.db.fetch("SELECT DISTINCT nombre, tag FROM jugadores")
    if not jugadores:
        return

    for j in jugadores:
        nombre, tag = j["nombre"], j["tag"]
        s, err = await fetch_stats(nombre, tag)
        await asyncio.sleep(4)
        if err or not s or not s.get("last_match"):
            continue

        lm = s["last_match"]
        match_id = lm.get("id")
        existe = await bot.db.fetchval(
            "SELECT 1 FROM partidas WHERE match_id = $1 AND jugador_nombre = $2 AND jugador_tag = $3",
            match_id, nombre, tag,
        )
        if match_id and not existe:
            k = lm.get("kills", 0)
            d = lm.get("deaths", 1)
            a = lm.get("assists", 0)
            acs = lm.get("acs", 0)
            won = lm.get("won", False)
            agente = lm.get("agente", "Desconocido")
            mapa = s.get("mapa", "Desconocido")
            modo_raw = (s.get("modo") or "Unrated").strip()
            modo_formateado = "Competitive" if modo_raw.lower() == "competitive" else modo_raw
            total_partidas = await bot.db.fetchval(
                "SELECT COUNT(*) FROM partidas WHERE jugador_nombre = $1 AND jugador_tag = $2",
                nombre, tag,
            )
            es_primera_vez = total_partidas == 0

            tracker_metrics = _calc_tracker_metrics_from_stats(s)
            await bot.db.execute(
                """
                INSERT INTO partidas (
                    match_id, jugador_nombre, jugador_tag, kills, deaths, assists, acs, won, mapa, modo, agente,
                    adr, kast, dda, rounds_played, damage_dealt_total, damage_received_total, kast_rounds, hs
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19)
                """,
                match_id, nombre, tag, k, d, a, acs, won, mapa, modo_formateado, agente,
                tracker_metrics["adr"], tracker_metrics["kast"], tracker_metrics["dda"],
                tracker_metrics["rounds_played"], tracker_metrics["damage_dealt_total"],
                tracker_metrics["damage_received_total"], tracker_metrics["kast_rounds"],
                s.get("last_match", {}).get("hs") if s.get("last_match", {}).get("hs") is not None else (tracker_metrics.get("hs") if tracker_metrics.get("hs") is not None else s.get("hs")),
            )

            if es_primera_vez:
                continue

            await _check_racha(nombre, tag, canal)
            nuevo_rango = s.get("rank")
            await _check_rango(nombre, tag, nuevo_rango, canal)

            resultado = "VICTORIA" if won else "DERROTA"
            color_borde = 0x00FF00 if won else 0xFF0000
            nombre_real = s.get("nombre") or nombre
            tag_real = s.get("tag") or tag
            title = f"🎮 Nueva partida de {nombre_real}#{tag_real}"
            desc = f"Acaba de jugar **{modo_formateado}** en **{mapa}** con **{agente}**."

            embed = discord.Embed(title=title, description=desc, color=color_borde)
            embed.add_field(name="Resultado", value=f"**{resultado}**", inline=True)
            embed.add_field(name="K/D/A", value=f"{k}/{d}/{a}", inline=True)
            embed.add_field(name="ACS", value=str(acs), inline=True)
            if tracker_metrics["adr"] is not None:
                embed.add_field(name="ADR", value=str(round(tracker_metrics["adr"], 1)), inline=True)
            if tracker_metrics["kast"] is not None:
                embed.add_field(name="KAST", value=f"{round(tracker_metrics['kast'], 1)}%", inline=True)
            if tracker_metrics["dda"] is not None:
                embed.add_field(name="DDA", value=str(round(tracker_metrics["dda"], 1)), inline=True)
            if s.get("card"):
                embed.set_thumbnail(url=s.get("card"))
            await canal.send(embed=embed)


async def fetch_stats(nombre, tag, region="eu"):
    def _request():
        try:
            r = requests.post(
                f"{TRACKER_URL.rstrip('/')}/tracker",
                json={"username": nombre, "tag": tag, "region": region},
                timeout=30,
            )
            if not r.content:
                return None, "El servidor de stats no respondió (respuesta vacía)."
            try:
                data = r.json()
            except Exception:
                return None, f"Respuesta inválida del webhook (HTTP {r.status_code}): {r.text[:200]}"
            if not data.get("success"):
                return None, data.get("error", "Error de la API")
            return data.get("stats", {}), None
        except requests.exceptions.ConnectionError:
            return None, f"No se puede conectar al webhook ({TRACKER_URL}). ¿Está activo?"
        except requests.exceptions.Timeout:
            return None, "El webhook tardó demasiado en responder (timeout 30s)."
        except Exception as e:
            return None, str(e)

    return await asyncio.to_thread(_request)


@bot.tree.command(name="stats", description="Muestra las estadísticas de un jugador de Valorant")
@app_commands.choices(modo=MODOS_DISCORD)
async def stats(interaction: discord.Interaction, nombre: str, tag: str, region: str = "eu", modo: app_commands.Choice[str] = None):
    await interaction.response.defer(thinking=True)
    modo_busqueda = modo.value if modo else "Competitive"
    modo_display = modo.name if modo else "Competitivo"
    if modo_busqueda == "%":
        modo_display = "Todos los modos"

    s, err = await fetch_stats(nombre, tag, region)
    if err or not s:
        await interaction.followup.send(f"❌ Fallo al buscar a {nombre}#{tag}: {err}")
        return

    rows = await bot.db.fetch(
        """
        SELECT p.match_id, p.kills, p.deaths, p.assists, p.acs, p.won, p.mapa, p.modo, p.agente,
               p.adr, p.kast, p.dda, p.rounds_played, p.damage_dealt_total, p.damage_received_total,
               p.kast_rounds, p.hs, p.fecha
        FROM partidas p
        JOIN jugadores j ON p.jugador_nombre = j.nombre AND p.jugador_tag = j.tag
        WHERE j.server_id = $1 AND p.jugador_nombre = $2 AND p.jugador_tag = $3
        ORDER BY p.fecha DESC
        LIMIT 120
        """,
        str(interaction.guild_id), nombre, tag,
    )

    filtered_rows = rows if modo_busqueda == "%" else [r for r in rows if str(r["modo"]).lower() == modo_busqueda.lower()]
    if not filtered_rows:
        await interaction.followup.send(f"❌ No hay partidas guardadas para **{nombre}#{tag}** en **{modo_display}**.")
        return

    db_stats = {
        "tk": sum((r["kills"] or 0) for r in filtered_rows),
        "td": sum((r["deaths"] or 0) for r in filtered_rows),
        "ta": sum((r["assists"] or 0) for r in filtered_rows),
        "acs_medio": round(sum(float(r["acs"] or 0) for r in filtered_rows) / len(filtered_rows), 1),
        "adr_medio": round(sum(float(r["adr"] or 0) for r in filtered_rows) / len(filtered_rows), 1),
        "dda_medio": round(sum(float(r["dda"] or 0) for r in filtered_rows) / len(filtered_rows), 1),
        "hs_medio": round(sum(float(r["hs"] or 0) for r in filtered_rows) / len(filtered_rows), 1),
        "winrate": round(sum(1 for r in filtered_rows if r["won"]) * 100.0 / len(filtered_rows), 1),
        "total_matches": len(filtered_rows),
    }

    kast_vals = [float(r["kast"]) for r in filtered_rows if r["kast"] is not None]
    db_stats["kast_medio"] = round(sum(kast_vals) / len(kast_vals), 1) if kast_vals else None

    agent_counts = {}
    for r in filtered_rows:
        ag = r["agente"] or "Desconocido"
        agent_counts[ag] = agent_counts.get(ag, 0) + 1
    top_agents_db = [a for a, _ in sorted(agent_counts.items(), key=lambda x: x[1], reverse=True)]
    db_stats["main_agent"] = top_agents_db[0] if top_agents_db else "Desconocido"

    latest = filtered_rows[0]
    s["mapa"] = latest["mapa"] or s.get("mapa")
    s["modo"] = latest["modo"] or s.get("modo")
    s["last_match"] = {
        "id": latest["match_id"],
        "kills": latest["kills"] or 0,
        "deaths": latest["deaths"] or 0,
        "assists": latest["assists"] or 0,
        "acs": float(latest["acs"] or 0),
        "adr": float(latest["adr"] or 0),
        "dda": float(latest["dda"] or 0),
        "kast": float(latest["kast"]) if latest["kast"] is not None else None,
        "hs": float(latest["hs"] or 0),
        "won": bool(latest["won"]),
        "agente": latest["agente"] or "Desconocido",
        "rounds_played": latest["rounds_played"],
        "damage_dealt_total": latest["damage_dealt_total"],
        "damage_received_total": latest["damage_received_total"],
        "kast_rounds": latest["kast_rounds"],
    }

    tiene_datos_db = bool(db_stats["total_matches"] > 0)

    try:
        buf = await asyncio.wait_for(
            asyncio.to_thread(generar_tarjeta, s, modo_display, tiene_datos_db, db_stats, top_agents_db),
            timeout=20,
        )
        archivo = discord.File(fp=buf, filename="stats.png")
    except Exception as e:
        logging.exception("Error generando tarjeta /stats")
        await interaction.followup.send(f"❌ Error generando la tarjeta de stats: {e}")
        return

    embed = discord.Embed(color=0xFF4655)
    embed.set_image(url="attachment://stats.png")
    await interaction.followup.send(file=archivo, embed=embed)


@bot.tree.command(name="add", description="Guarda a un colega en la base de datos del servidor")
async def add(interaction: discord.Interaction, nombre: str, tag: str):
    server_id = str(interaction.guild_id)
    try:
        await bot.db.execute(
            "INSERT INTO jugadores (server_id, nombre, tag) VALUES ($1, $2, $3)",
            server_id, nombre, tag,
        )
        await interaction.response.send_message(f"✅ Añadido a la lista de la temporada: **{nombre}#{tag}**")
    except asyncpg.exceptions.UniqueViolationError:
        await interaction.response.send_message(f"⚠️ {nombre}#{tag} ya está en la lista.")


@bot.tree.command(name="leaderboard", description="Ranking de los colegas del servidor")
@app_commands.choices(modo=MODOS_DISCORD)
async def leaderboard(interaction: discord.Interaction, modo: app_commands.Choice[str] = None):
    server_id = str(interaction.guild_id)
    modo_busqueda = modo.value if modo else "Competitive"
    modo_display = modo.name if modo else "Competitivo"
    if modo_busqueda == "%":
        modo_display = "Todos los modos"

    amigos = await bot.db.fetch("SELECT nombre, tag FROM jugadores WHERE server_id = $1", server_id)
    if not amigos:
        await interaction.response.send_message("❌ No hay nadie en la lista. Usad `/add` primero.")
        return

    await interaction.response.defer()
    scores = await bot.db.fetch(
        """
        SELECT p.jugador_nombre as nombre, p.jugador_tag as tag,
               AVG(p.acs) as acs_medio,
               AVG(CASE WHEN p.rounds_played > 0 AND p.damage_dealt_total IS NOT NULL
                        THEN p.damage_dealt_total::numeric / p.rounds_played
                        ELSE p.adr END) as adr_medio,
               AVG(CASE WHEN p.rounds_played > 0 AND p.kast_rounds IS NOT NULL
                        THEN (p.kast_rounds::numeric * 100.0) / p.rounds_played
                        ELSE p.kast END) as kast_medio,
               AVG(CASE WHEN p.rounds_played > 0 AND p.damage_dealt_total IS NOT NULL AND p.damage_received_total IS NOT NULL
                        THEN (p.damage_dealt_total::numeric - p.damage_received_total::numeric) / p.rounds_played
                        ELSE p.dda END) as dda_medio,
               SUM(p.kills) as tk, SUM(p.deaths) as td, SUM(p.assists) as ta,
               COUNT(*) as total_matches,
               AVG(p.hs) as hs_medio,
               COUNT(CASE WHEN p.won THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0) as winrate,
               (
                   SELECT agente FROM partidas p2
                   WHERE p2.jugador_nombre = p.jugador_nombre AND p2.jugador_tag = p.jugador_tag AND ($2 = '%' OR LOWER(p2.modo) = LOWER($2))
                   GROUP BY agente ORDER BY COUNT(*) DESC LIMIT 1
               ) as main_agent
        FROM partidas p
        JOIN jugadores j ON p.jugador_nombre = j.nombre AND p.jugador_tag = j.tag
        WHERE j.server_id = $1 AND ($2 = '%' OR LOWER(p.modo) = LOWER($2))
        GROUP BY p.jugador_nombre, p.jugador_tag
        ORDER BY acs_medio DESC
        """,
        server_id, modo_busqueda,
    )

    if not scores:
        await interaction.followup.send(f"❌ Todavía no hay partidas de **{modo_display}** en este servidor.")
        return

    embed = discord.Embed(title=f"🏆 Leaderboard ({modo_display})", color=0xFFD700)
    for i, p in enumerate(scores):
        medalla = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else "🔹"
        acs_val = round(p["acs_medio"], 1) if p["acs_medio"] is not None else 0
        kda_val = round((p["tk"] + p["ta"]) / max(p["td"], 1), 2)
        extras = []
        if p["adr_medio"] is not None:
            extras.append(f"ADR {round(p['adr_medio'], 1)}")
        if p["kast_medio"] is not None:
            extras.append(f"KAST {round(p['kast_medio'], 1)}%")
        if p["dda_medio"] is not None:
            extras.append(f"DDA {round(p['dda_medio'], 1)}")
        if p["winrate"] is not None:
            extras.append(f"WR {round(p['winrate'], 1)}%")
        if p.get("hs_medio") is not None:
            extras.append(f"HS {round(p['hs_medio'], 1)}%")
        stats_txt = f"**ACS:** {acs_val} | **KDA:** {kda_val} | **Partidas:** {p['total_matches']}"
        if extras:
            stats_txt += "\n" + " | ".join(extras)
        main_agent = p["main_agent"] or "Desconocido"
        embed.add_field(name=f"{medalla} {p['nombre']}#{p['tag']} ({main_agent})", value=stats_txt, inline=False)

    await interaction.followup.send(embed=embed)

# ─────────────────────────────────────────────
# CHART HELPERS
# ─────────────────────────────────────────────

def _gen_evolucion(rows, nombre_jugador):
    """Genera gráfica de línea: ACS, DDA y HS% a lo largo de partidas."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.ticker as ticker

    fechas = [r["fecha"].strftime("%d/%m") for r in rows]
    acs_vals = [float(r["acs"]) if r["acs"] is not None else None for r in rows]
    dda_vals = [float(r["dda"]) if r["dda"] is not None else None for r in rows]
    hs_vals  = [float(r["hs"]) if r.get("hs") is not None else None for r in rows]
    indices  = list(range(len(rows)))

    fig, axes = plt.subplots(3, 1, figsize=(10, 7), facecolor="#0a0b11")
    fig.suptitle(f"Evolución de {nombre_jugador}", color="#f5f7fb", fontsize=14, fontweight="bold", y=0.98)

    configs = [
        (axes[0], acs_vals, "ACS",  "#4fd1c5", "#0a4040"),
        (axes[1], dda_vals, "DDA",  "#fc8181", "#400a0a"),
        (axes[2], hs_vals,  "HS%",  "#f6e05e", "#3d3300"),
    ]

    for ax, vals, label, color, fill_color in configs:
        clean_x = [i for i, v in zip(indices, vals) if v is not None]
        clean_v = [v for v in vals if v is not None]
        ax.set_facecolor("#0f1119")
        for spine in ax.spines.values():
            spine.set_color("#2a3043")
        ax.tick_params(colors="#96a3b3", labelsize=8)
        ax.yaxis.set_major_formatter(ticker.FormatStrFormatter("%.0f"))
        ax.set_ylabel(label, color=color, fontsize=9, fontweight="bold")
        if clean_x:
            ax.fill_between(clean_x, clean_v, alpha=0.15, color=fill_color)
            ax.plot(clean_x, clean_v, color=color, linewidth=2, marker="o", markersize=4)
            ax.set_xlim(-0.5, len(indices) - 0.5)
        ax.set_xticks(indices)
        ax.set_xticklabels(fechas, rotation=45, ha="right", fontsize=7, color="#96a3b3")
        ax.grid(axis="y", color="#1e2535", linewidth=0.7)
        if label == "DDA":
            ax.axhline(0, color="#555", linewidth=0.8, linestyle="--")

    plt.tight_layout(rect=[0, 0, 1, 0.97])
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf


def _gen_heatmap_mapas(rows):
    """Genera heatmap: mapas × métricas (ACS, WR, DDA)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    mapa_stats = {}
    for r in rows:
        m = r["mapa"] or "?"
        if m not in mapa_stats:
            mapa_stats[m] = {"acs": [], "won": [], "dda": []}
        if r["acs"] is not None:
            mapa_stats[m]["acs"].append(float(r["acs"]))
        mapa_stats[m]["won"].append(1 if r["won"] else 0)
        if r["dda"] is not None:
            mapa_stats[m]["dda"].append(float(r["dda"]))

    mapas = sorted(mapa_stats.keys())
    if not mapas:
        return None

    metricas = ["ACS medio", "Winrate %", "DDA medio"]
    data = []
    for m in mapas:
        s_ = mapa_stats[m]
        acs_m = sum(s_["acs"]) / len(s_["acs"]) if s_["acs"] else 0
        wr_m  = sum(s_["won"]) / len(s_["won"]) * 100 if s_["won"] else 0
        dda_m = sum(s_["dda"]) / len(s_["dda"]) if s_["dda"] else 0
        data.append([acs_m, wr_m, dda_m])

    arr = np.array(data, dtype=float)
    # normalise each column 0–1 for color
    normed = np.zeros_like(arr)
    for c in range(arr.shape[1]):
        col = arr[:, c]
        mn, mx = col.min(), col.max()
        normed[:, c] = (col - mn) / (mx - mn) if mx != mn else 0.5

    fig, ax = plt.subplots(figsize=(7, max(3, len(mapas) * 0.65)), facecolor="#0a0b11")
    ax.set_facecolor("#0f1119")
    im = ax.imshow(normed, aspect="auto", cmap="RdYlGn", vmin=0, vmax=1)
    ax.set_xticks(range(len(metricas)))
    ax.set_xticklabels(metricas, color="#f5f7fb", fontsize=10)
    ax.set_yticks(range(len(mapas)))
    ax.set_yticklabels(mapas, color="#f5f7fb", fontsize=10)
    for spine in ax.spines.values():
        spine.set_color("#2a3043")
    ax.tick_params(colors="#96a3b3")
    for r_i in range(len(mapas)):
        for c_i in range(len(metricas)):
            val = arr[r_i, c_i]
            txt = f"{val:.0f}" if c_i != 1 else f"{val:.0f}%"
            ax.text(c_i, r_i, txt, ha="center", va="center", fontsize=9,
                    color="white", fontweight="bold")
    ax.set_title("Rendimiento por mapa", color="#f5f7fb", fontsize=12, pad=10)
    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf


def _gen_pie_agentes(agent_rows, titulo="Agentes jugados"):
    """Genera pie chart de agentes."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    agentes = [r["agente"] for r in agent_rows if r["agente"] != "Desconocido"]
    counts  = [r["count"]  for r in agent_rows if r["agente"] != "Desconocido"]
    if not agentes:
        return None

    COLORS = ["#4fd1c5","#fc8181","#f6e05e","#68d391","#76e4f7",
              "#a78bfa","#f687b3","#fbd38d","#9ae6b4","#bee3f8"]

    fig, ax = plt.subplots(figsize=(6, 5), facecolor="#0a0b11")
    wedges, texts, autotexts = ax.pie(
        counts, labels=agentes, autopct="%1.0f%%",
        colors=COLORS[:len(agentes)], startangle=140,
        textprops={"color": "#f5f7fb", "fontsize": 10},
        wedgeprops={"linewidth": 1.5, "edgecolor": "#0a0b11"},
    )
    for at in autotexts:
        at.set_fontsize(9)
        at.set_color("#0a0b11")
        at.set_fontweight("bold")
    ax.set_title(titulo, color="#f5f7fb", fontsize=13, fontweight="bold", pad=14)
    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf


def _gen_barra_comparativa(stats_a, nombre_a, stats_b, nombre_b):
    """Genera gráfica de barras horizontales comparando dos jugadores."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    metricas = ["ACS", "KDA", "ADR", "KAST %", "DDA", "WR %", "HS %"]
    vals_a = [
        float(stats_a.get("acs_medio") or 0),
        round((float(stats_a.get("tk") or 0) + float(stats_a.get("ta") or 0)) / max(float(stats_a.get("td") or 1), 1), 2),
        float(stats_a.get("adr_medio") or 0),
        float(stats_a.get("kast_medio") or 0),
        float(stats_a.get("dda_medio") or 0),
        float(stats_a.get("winrate") or 0),
        float(stats_a.get("hs_medio") or 0),
    ]
    vals_b = [
        float(stats_b.get("acs_medio") or 0),
        round((float(stats_b.get("tk") or 0) + float(stats_b.get("ta") or 0)) / max(float(stats_b.get("td") or 1), 1), 2),
        float(stats_b.get("adr_medio") or 0),
        float(stats_b.get("kast_medio") or 0),
        float(stats_b.get("dda_medio") or 0),
        float(stats_b.get("winrate") or 0),
        float(stats_b.get("hs_medio") or 0),
    ]

    y = np.arange(len(metricas))
    bar_h = 0.32
    fig, ax = plt.subplots(figsize=(9, 5), facecolor="#0a0b11")
    ax.set_facecolor("#0f1119")
    bars_a = ax.barh(y + bar_h/2, vals_a, bar_h, color="#4fd1c5", label=nombre_a)
    bars_b = ax.barh(y - bar_h/2, vals_b, bar_h, color="#fc8181", label=nombre_b)
    ax.set_yticks(y)
    ax.set_yticklabels(metricas, color="#f5f7fb", fontsize=11)
    ax.tick_params(axis="x", colors="#96a3b3", labelsize=9)
    for spine in ax.spines.values():
        spine.set_color("#2a3043")
    ax.grid(axis="x", color="#1e2535", linewidth=0.7)
    ax.legend(facecolor="#0f1119", edgecolor="#2a3043", labelcolor="#f5f7fb", fontsize=10)
    ax.set_title(f"{nombre_a}  vs  {nombre_b}", color="#f5f7fb", fontsize=13, fontweight="bold", pad=12)
    for bar in bars_a:
        w = bar.get_width()
        ax.text(w + 0.5, bar.get_y() + bar.get_height()/2, f"{w:.1f}", va="center", color="#4fd1c5", fontsize=8)
    for bar in bars_b:
        w = bar.get_width()
        ax.text(w + 0.5, bar.get_y() + bar.get_height()/2, f"{w:.1f}", va="center", color="#fc8181", fontsize=8)
    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf


def _gen_precision(rows, nombre_jugador):
    """Genera gráfica de precisión HS% por partida con media móvil."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    hs_data = [(r["fecha"].strftime("%d/%m"), float(r["hs"])) for r in rows if r.get("hs") is not None]
    if not hs_data:
        return None

    fechas, vals = zip(*hs_data)
    indices = list(range(len(vals)))
    media_movil = np.convolve(vals, np.ones(3)/3, mode="same")

    fig, ax = plt.subplots(figsize=(10, 3.5), facecolor="#0a0b11")
    ax.set_facecolor("#0f1119")
    for spine in ax.spines.values():
        spine.set_color("#2a3043")
    ax.fill_between(indices, vals, alpha=0.12, color="#f6e05e")
    ax.plot(indices, vals, color="#f6e05e", linewidth=1.5, marker="o", markersize=4, label="HS% real")
    ax.plot(indices, media_movil, color="#fc8181", linewidth=2, linestyle="--", label="Media móvil (3)")
    ax.axhline(sum(vals)/len(vals), color="#888", linewidth=0.9, linestyle=":", label=f"Media global ({sum(vals)/len(vals):.1f}%)")
    ax.set_xticks(indices)
    ax.set_xticklabels(fechas, rotation=45, ha="right", fontsize=7, color="#96a3b3")
    ax.tick_params(axis="y", colors="#96a3b3", labelsize=9)
    ax.grid(axis="y", color="#1e2535", linewidth=0.7)
    ax.set_title(f"Precisión (HS%) — {nombre_jugador}", color="#f5f7fb", fontsize=12, fontweight="bold")
    ax.legend(facecolor="#0f1119", edgecolor="#2a3043", labelcolor="#f5f7fb", fontsize=9)
    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf


# ─────────────────────────────────────────────
# RACHA: lógica interna
# ─────────────────────────────────────────────

async def _check_racha(nombre, tag, canal):
    ultimas = await bot.db.fetch(
        """
        SELECT won FROM partidas
        WHERE jugador_nombre = $1 AND jugador_tag = $2
        ORDER BY fecha DESC LIMIT 5
        """,
        nombre, tag,
    )
    if len(ultimas) < 3:
        return
    resultados = [r["won"] for r in ultimas]
    if all(resultados[:3]):
        await canal.send(
            f"🔥 **¡{nombre}#{tag} está en racha!** 3 victorias seguidas. Que no se le suba a la cabeza. 🏆"
        )
    elif not any(resultados[:3]):
        await canal.send(
            f"💀 **{nombre}#{tag} lleva 3 derrotas seguidas.** Alguien que le diga que respire. 🫂"
        )


# ─────────────────────────────────────────────
# ALERTA DE RANGO: guardamos rango en jugadores
# ─────────────────────────────────────────────

async def _check_rango(nombre, tag, nuevo_rango, canal):
    row = await bot.db.fetchrow(
        "SELECT ultimo_rango FROM jugadores WHERE nombre = $1 AND tag = $2",
        nombre, tag,
    )
    if row is None:
        return
    viejo = row["ultimo_rango"]
    if viejo and viejo != nuevo_rango:
        if nuevo_rango and viejo:
            ranks_order = [
                "Iron 1","Iron 2","Iron 3",
                "Bronze 1","Bronze 2","Bronze 3",
                "Silver 1","Silver 2","Silver 3",
                "Gold 1","Gold 2","Gold 3",
                "Platinum 1","Platinum 2","Platinum 3",
                "Diamond 1","Diamond 2","Diamond 3",
                "Ascendant 1","Ascendant 2","Ascendant 3",
                "Immortal 1","Immortal 2","Immortal 3",
                "Radiant",
            ]
            vi = ranks_order.index(viejo) if viejo in ranks_order else -1
            ni = ranks_order.index(nuevo_rango) if nuevo_rango in ranks_order else -1
            if vi >= 0 and ni >= 0:
                if ni > vi:
                    await canal.send(f"📈 **¡{nombre}#{tag} ha subido de rango!** {viejo} → **{nuevo_rango}** 🎉")
                else:
                    await canal.send(f"📉 **{nombre}#{tag} ha bajado de rango.** {viejo} → **{nuevo_rango}** 😬")
    await bot.db.execute(
        "UPDATE jugadores SET ultimo_rango = $1 WHERE nombre = $2 AND tag = $3",
        nuevo_rango, nombre, tag,
    )


# ─────────────────────────────────────────────
# RESUMEN SEMANAL AUTOMÁTICO
# ─────────────────────────────────────────────

@tasks.loop(hours=1)
async def resumen_semanal():
    await bot.wait_until_ready()
    import datetime
    now = datetime.datetime.utcnow()
    if now.weekday() != 0 or now.hour != 8:
        return
    try:
        canal = await bot.fetch_channel(CANAL_ALERTAS_ID)
    except Exception:
        return

    server_ids = await bot.db.fetch("SELECT DISTINCT server_id FROM jugadores")
    for srv in server_ids:
        sid = srv["server_id"]
        rows = await bot.db.fetch(
            """
            SELECT p.jugador_nombre as nombre, p.jugador_tag as tag,
                   AVG(p.acs) as acs_medio,
                   COUNT(*) as partidas,
                   COUNT(CASE WHEN p.won THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0) as winrate,
                   AVG(CASE WHEN p.rounds_played > 0 AND p.damage_dealt_total IS NOT NULL AND p.damage_received_total IS NOT NULL
                            THEN (p.damage_dealt_total::numeric - p.damage_received_total::numeric) / p.rounds_played
                            ELSE p.dda END) as dda_medio
            FROM partidas p
            JOIN jugadores j ON p.jugador_nombre = j.nombre AND p.jugador_tag = j.tag
            WHERE j.server_id = $1
              AND p.modo ILIKE 'Competitive'
              AND p.fecha >= NOW() - INTERVAL '7 days'
            GROUP BY p.jugador_nombre, p.jugador_tag
            ORDER BY acs_medio DESC
            """,
            sid,
        )
        if not rows:
            continue

        embed = discord.Embed(
            title="📅 Resumen semanal del servidor",
            description="Las stats de la última semana en Competitivo.",
            color=0xFFD700,
        )
        mvp = rows[0]
        embed.add_field(
            name=f"👑 MVP de la semana: {mvp['nombre']}#{mvp['tag']}",
            value=f"ACS: **{round(mvp['acs_medio'],1)}** · WR: **{round(mvp['winrate'],1)}%** · Partidas: **{mvp['partidas']}**",
            inline=False,
        )
        for r in rows[1:]:
            embed.add_field(
                name=f"🔹 {r['nombre']}#{r['tag']}",
                value=f"ACS {round(r['acs_medio'],1)} · WR {round(r['winrate'],1)}% · {r['partidas']} partidas · DDA {round(r['dda_medio'],1) if r['dda_medio'] else '—'}",
                inline=False,
            )
        await canal.send(embed=embed)


# ─────────────────────────────────────────────
# PATCH VIGILANTE: añadir racha + rango check
# ─────────────────────────────────────────────

# El vigilante ya está definido arriba; aquí extendemos on_ready para arrancar resumen_semanal

_old_on_ready = bot.extra_events.get("on_ready", [])


# ─────────────────────────────────────────────
# NUEVOS COMANDOS v1.0.1
# ─────────────────────────────────────────────

@bot.tree.command(name="sync", description="Sincroniza los slash commands en este servidor")
async def sync_cmd(interaction: discord.Interaction):
    synced = await bot.tree.sync(guild=discord.Object(id=interaction.guild_id))
    await interaction.response.send_message(f"✅ {len(synced)} comandos sincronizados en este servidor.", ephemeral=True)

@bot.tree.command(name="remove", description="Deja de vigilar a un jugador del servidor")
async def remove(interaction: discord.Interaction, nombre: str, tag: str):
    server_id = str(interaction.guild_id)
    deleted = await bot.db.execute(
        "DELETE FROM jugadores WHERE server_id = $1 AND nombre = $2 AND tag = $3",
        server_id, nombre, tag,
    )
    if deleted == "DELETE 1":
        await interaction.response.send_message(f"🗑️ **{nombre}#{tag}** eliminado de la vigilancia de este servidor.")
    else:
        await interaction.response.send_message(f"⚠️ No encontré a **{nombre}#{tag}** en la lista de este servidor.")


@bot.tree.command(name="graficas", description="Muestra gráficas de evolución, precisión y mapas de un jugador")
@app_commands.choices(modo=MODOS_DISCORD)
async def graficas(interaction: discord.Interaction, nombre: str, tag: str, modo: app_commands.Choice[str] = None):
    await interaction.response.defer()
    server_id = str(interaction.guild_id)
    modo_busqueda = "Competitive"

    rows = await bot.db.fetch(
        """
        SELECT p.fecha, p.acs, p.dda, p.won, p.mapa, p.agente,
               p.hs
        FROM partidas p
        JOIN jugadores j ON p.jugador_nombre = j.nombre AND p.jugador_tag = j.tag
        WHERE j.server_id = $1 AND p.jugador_nombre = $2 AND p.jugador_tag = $3 AND ($4 = '%' OR LOWER(p.modo) = LOWER($4))
        ORDER BY p.fecha ASC
        LIMIT 40
        """,
        server_id, nombre, tag, modo_busqueda,
    )

    if not rows:
        await interaction.followup.send(f"❌ No hay partidas guardadas para **{nombre}#{tag}** en ese modo.")
        return

    archivos = []

    buf_evol = await asyncio.to_thread(_gen_evolucion, rows, f"{nombre}#{tag}")
    archivos.append(discord.File(fp=buf_evol, filename="evolucion.png"))

    buf_hm = await asyncio.to_thread(_gen_heatmap_mapas, rows)
    if buf_hm:
        archivos.append(discord.File(fp=buf_hm, filename="mapas.png"))

    agent_rows = await bot.db.fetch(
        """
        SELECT p.agente, COUNT(*) as count
        FROM partidas p
        JOIN jugadores j ON p.jugador_nombre = j.nombre AND p.jugador_tag = j.tag
        WHERE j.server_id = $1 AND p.jugador_nombre = $2 AND p.jugador_tag = $3 AND ($4 = '%' OR LOWER(p.modo) = LOWER($4))
        GROUP BY p.agente ORDER BY count DESC
        """,
        server_id, nombre, tag, modo_busqueda,
    )
    buf_pie = await asyncio.to_thread(_gen_pie_agentes, agent_rows, f"Agentes — {nombre}#{tag}")
    if buf_pie:
        archivos.append(discord.File(fp=buf_pie, filename="agentes.png"))

    if modo_busqueda == "Competitive":
        buf_prec = await asyncio.to_thread(_gen_precision, rows, f"{nombre}#{tag}")
        if buf_prec:
            archivos.append(discord.File(fp=buf_prec, filename="precision.png"))

    embed = discord.Embed(
        title=f"📊 Gráficas de {nombre}#{tag}",
        description=f"Últimas {len(rows)} partidas en modo {modo.name if modo else 'Competitivo'}",
        color=0x4fd1c5,
    )
    await interaction.followup.send(embed=embed, files=archivos)


@bot.tree.command(name="comparar", description="Compara las stats competitivas de dos jugadores del servidor")
async def comparar(
    interaction: discord.Interaction,
    nombre1: str, tag1: str,
    nombre2: str, tag2: str,
):
    await interaction.response.defer()
    server_id = str(interaction.guild_id)
    modo_busqueda = "Competitive"

    async def _get_stats(nom, tg):
        return await bot.db.fetchrow(
            """
            SELECT AVG(p.acs) as acs_medio,
                   SUM(p.kills) as tk, SUM(p.deaths) as td, SUM(p.assists) as ta,
                   AVG(CASE WHEN p.rounds_played > 0 AND p.damage_dealt_total IS NOT NULL
                            THEN p.damage_dealt_total::numeric / p.rounds_played ELSE p.adr END) as adr_medio,
                   AVG(CASE WHEN p.rounds_played > 0 AND p.kast_rounds IS NOT NULL
                            THEN (p.kast_rounds::numeric * 100.0) / p.rounds_played ELSE p.kast END) as kast_medio,
                   AVG(CASE WHEN p.rounds_played > 0 AND p.damage_dealt_total IS NOT NULL AND p.damage_received_total IS NOT NULL
                            THEN (p.damage_dealt_total::numeric - p.damage_received_total::numeric) / p.rounds_played
                            ELSE p.dda END) as dda_medio,
                   AVG(p.hs) as hs_medio,
                   COUNT(CASE WHEN p.won THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0) as winrate,
                   COUNT(*) as total_matches
            FROM partidas p
            JOIN jugadores j ON p.jugador_nombre = j.nombre AND p.jugador_tag = j.tag
            WHERE j.server_id = $1 AND p.jugador_nombre = $2 AND p.jugador_tag = $3 AND ($4 = '%' OR LOWER(p.modo) = LOWER($4))
            """,
            server_id, nom, tg, modo_busqueda,
        )

    s1, s2 = await asyncio.gather(_get_stats(nombre1, tag1), _get_stats(nombre2, tag2))

    if not s1 or not s1["total_matches"]:
        await interaction.followup.send(f"❌ No hay datos para **{nombre1}#{tag1}**.")
        return
    if not s2 or not s2["total_matches"]:
        await interaction.followup.send(f"❌ No hay datos para **{nombre2}#{tag2}**.")
        return

    buf = await asyncio.to_thread(_gen_barra_comparativa, dict(s1), f"{nombre1}#{tag1}", dict(s2), f"{nombre2}#{tag2}")
    archivo = discord.File(fp=buf, filename="comparar.png")

    def fmt(v, suf=""):
        return f"{round(float(v),1)}{suf}" if v is not None else "—"

    kda1 = round((float(s1["tk"] or 0) + float(s1["ta"] or 0)) / max(float(s1["td"] or 1),1), 2)
    kda2 = round((float(s2["tk"] or 0) + float(s2["ta"] or 0)) / max(float(s2["td"] or 1),1), 2)

    embed = discord.Embed(title=f"⚔️ {nombre1}#{tag1}  vs  {nombre2}#{tag2}", color=0x4fd1c5)
    embed.set_image(url="attachment://comparar.png")
    embed.add_field(name=f"📊 {nombre1}#{tag1}",
        value=f"ACS {fmt(s1['acs_medio'])} · KDA {kda1} · ADR {fmt(s1['adr_medio'])} · KAST {fmt(s1['kast_medio'],'%')} · DDA {fmt(s1['dda_medio'])} · WR {fmt(s1['winrate'],'%')} · HS {fmt(s1['hs_medio'],'%')} · {s1['total_matches']} partidas",
        inline=False)
    embed.add_field(name=f"📊 {nombre2}#{tag2}",
        value=f"ACS {fmt(s2['acs_medio'])} · KDA {kda2} · ADR {fmt(s2['adr_medio'])} · KAST {fmt(s2['kast_medio'],'%')} · DDA {fmt(s2['dda_medio'])} · WR {fmt(s2['winrate'],'%')} · HS {fmt(s2['hs_medio'],'%')} · {s2['total_matches']} partidas",
        inline=False)
    await interaction.followup.send(file=archivo, embed=embed)


@bot.tree.command(name="temporada", description="Resumen competitivo de la temporada del servidor")
async def temporada(interaction: discord.Interaction, modo: app_commands.Choice[str] = None):
    await interaction.response.defer()
    server_id = str(interaction.guild_id)
    modo_busqueda = "Competitive"
    modo_display = modo.name if modo else "Competitivo"

    rows = await bot.db.fetch(
        """
        SELECT p.jugador_nombre as nombre, p.jugador_tag as tag,
               AVG(p.acs) as acs_medio,
               COUNT(*) as partidas,
               COUNT(CASE WHEN p.won THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0) as winrate,
               AVG(CASE WHEN p.rounds_played > 0 AND p.damage_dealt_total IS NOT NULL AND p.damage_received_total IS NOT NULL
                        THEN (p.damage_dealt_total::numeric - p.damage_received_total::numeric) / p.rounds_played
                        ELSE p.dda END) as dda_medio
        FROM partidas p
        JOIN jugadores j ON p.jugador_nombre = j.nombre AND p.jugador_tag = j.tag
        WHERE j.server_id = $1 AND ($2 = '%' OR LOWER(p.modo) = LOWER($2))
        GROUP BY p.jugador_nombre, p.jugador_tag
        ORDER BY acs_medio DESC
        """,
        server_id, modo_busqueda,
    )

    if not rows:
        await interaction.followup.send(f"❌ Todavía no hay datos de **{modo_display}** en este servidor.")
        return

    agent_rows_all = await bot.db.fetch(
        """
        SELECT p.agente, COUNT(*) as count
        FROM partidas p
        JOIN jugadores j ON p.jugador_nombre = j.nombre AND p.jugador_tag = j.tag
        WHERE j.server_id = $1 AND ($2 = '%' OR LOWER(p.modo) = LOWER($2)) AND p.agente != 'Desconocido'
        GROUP BY p.agente ORDER BY count DESC LIMIT 8
        """,
        server_id, modo_busqueda,
    )

    buf_pie = await asyncio.to_thread(_gen_pie_agentes, agent_rows_all, f"Agentes más jugados — {modo_display}")

    embed = discord.Embed(
        title=f"🏆 Temporada — {modo_display}",
        description="Rankings actuales del servidor.",
        color=0xFFD700,
    )

    mvp = rows[0]
    embed.add_field(
        name=f"👑 MVP: {mvp['nombre']}#{mvp['tag']}",
        value=f"ACS **{round(mvp['acs_medio'],1)}** · WR **{round(mvp['winrate'],1)}%** · {mvp['partidas']} partidas",
        inline=False,
    )
    most_games = max(rows, key=lambda r: r["partidas"])
    best_wr = max((r for r in rows if r["partidas"] >= 3), key=lambda r: float(r["winrate"] or 0), default=None)
    best_dda = max((r for r in rows if r["dda_medio"] is not None), key=lambda r: float(r["dda_medio"]), default=None)

    embed.add_field(name="🎮 Más partidas", value=f"{most_games['nombre']}#{most_games['tag']} ({most_games['partidas']})", inline=True)
    if best_wr:
        embed.add_field(name="🏅 Mejor winrate", value=f"{best_wr['nombre']}#{best_wr['tag']} ({round(float(best_wr['winrate']),1)}%)", inline=True)
    if best_dda:
        embed.add_field(name="💥 Mejor DDA", value=f"{best_dda['nombre']}#{best_dda['tag']} ({round(float(best_dda['dda_medio']),1)})", inline=True)

    ranking_txt = ""
    for i, r in enumerate(rows):
        med = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"{i+1}."
        ranking_txt += f"{med} **{r['nombre']}#{r['tag']}** — ACS {round(r['acs_medio'],1)} · WR {round(float(r['winrate'] or 0),1)}%\n"
    embed.add_field(name="📋 Ranking completo", value=ranking_txt or "—", inline=False)

    archivos = []
    if buf_pie:
        archivos.append(discord.File(fp=buf_pie, filename="agentes_temporada.png"))
        embed.set_image(url="attachment://agentes_temporada.png")

    await interaction.followup.send(embed=embed, files=archivos)


# ─────────────────────────────────────────────
# PATCH on_ready: arrancar resumen_semanal
# ─────────────────────────────────────────────


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    logging.exception("Slash command error", exc_info=error)
    msg = f"❌ Error ejecutando el comando: {error}"
    try:
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
    except Exception:
        pass

bot.run(TOKEN)