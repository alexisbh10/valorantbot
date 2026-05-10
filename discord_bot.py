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
        regular = requests.get("https://github.com/googlefonts/roboto/raw/main/src/hinted/Roboto-Regular.ttf", timeout=10)
        bold = requests.get("https://github.com/googlefonts/roboto/raw/main/src/hinted/Roboto-Bold.ttf", timeout=10)
        return (
            lambda s: ImageFont.truetype(io.BytesIO(bold.content), s),
            lambda s: ImageFont.truetype(io.BytesIO(regular.content), s),
        )
    except Exception:
        f = ImageFont.load_default()
        return lambda s: f, lambda s: f


_FB, _FR = _load_fonts()


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

    return {
        "rounds_played": rounds_played or None,
        "damage_dealt_total": damage_dealt_total or None,
        "damage_received_total": damage_received_total or None,
        "kast_rounds": kast_rounds or None,
        "adr": adr,
        "dda": dda,
        "kast": kast,
    }


def generar_tarjeta(s, modo_display, tiene_datos_db, db_stats, top_agents_db):
    acc1, acc2 = _rank_palette(s.get("rank", ""))
    W, H = 1100, 620
    PAD = 34
    BG = (9, 11, 17)
    PANEL = (15, 18, 28)
    PANEL_SOFT = (21, 25, 38)
    PANEL_ELEV = (27, 32, 47)
    TEXT = (245, 247, 251)
    MUTED = (150, 159, 179)
    FAINT = (104, 112, 132)
    LINE = (42, 48, 67)
    POS = (79, 209, 138)
    NEG = (236, 96, 96)

    def rounded_box(x1, y1, x2, y2, radius, fill, outline=None, width=1):
        draw.rounded_rectangle([x1, y1, x2, y2], radius=radius, fill=fill, outline=outline, width=width)

    def text(x, y, value, font, fill, anchor=None):
        draw.text((x, y), str(value), font=font, fill=fill, anchor=anchor)

    def fmt_num(v, digits=1, suffix=""):
        if v is None:
            return "—"
        try:
            return f"{round(float(v), digits)}{suffix}"
        except Exception:
            return f"{v}{suffix}"

    img = Image.new("RGBA", (W, H), BG)
    draw = ImageDraw.Draw(img)

    for i in range(H):
        t = i / H
        c = tuple(int(BG[j] * (1 - t) + (14, 18, 28)[j] * t) for j in range(3))
        draw.line([(0, i), (W, i)], fill=c, width=1)

    for r in range(300, 0, -10):
        a = int(24 * (1 - r / 300))
        c = tuple(min(255, int(acc1[j] * a / 255 + BG[j])) for j in range(3))
        draw.ellipse((-70, -50, r + 10, r + 30), fill=c)
    for r in range(250, 0, -10):
        a = int(16 * (1 - r / 250))
        c = tuple(min(255, int(acc2[j] * a / 255 + BG[j])) for j in range(3))
        draw.ellipse((W - r - 40, H - r - 130, W + 80, H + 10), fill=c)

    rounded_box(PAD, PAD, W - PAD, H - PAD, 28, PANEL, outline=(255, 255, 255, 16))
    rounded_box(PAD + 1, PAD + 1, W - PAD - 1, 146, 28, PANEL_SOFT)

    try:
        icon_url = s.get("rank_icon") or s.get("rankIcon") or ""
        if icon_url:
            ri_data = requests.get(icon_url, timeout=6)
            ri = Image.open(io.BytesIO(ri_data.content)).convert("RGBA")
            ri.thumbnail((88, 88), Image.LANCZOS)
            icon_layer = Image.new("RGBA", (92, 92), (0, 0, 0, 0))
            ix = (92 - ri.width) // 2
            iy = (92 - ri.height) // 2
            icon_layer.paste(ri, (ix, iy), ri)
            rounded_box(PAD + 18, PAD + 20, PAD + 110, PAD + 112, 24, PANEL_ELEV, outline=(255, 255, 255, 20))
            img.paste(icon_layer, (PAD + 18, PAD + 20), icon_layer)
    except Exception:
        pass

    header_x = PAD + 132
    text(header_x, PAD + 26, f"{s.get('nombre', '?')}#{s.get('tag', '?')}", _FB(44), TEXT)
    text(header_x, PAD + 80, f"{s.get('rank', 'Unranked')} · {s.get('rr', 0)} RR · Nivel {s.get('nivel', '?')} · {modo_display}", _FR(20), MUTED)

    try:
        card_url = s.get("card", "")
        if card_url:
            card_raw = Image.open(io.BytesIO(requests.get(card_url, timeout=6).content)).convert("RGBA")
            cw, ch = 132, 132
            card = card_raw.copy()
            card.thumbnail((cw, ch), Image.LANCZOS)
            layer = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
            px = (cw - card.width) // 2
            py = (ch - card.height) // 2
            layer.paste(card, (px, py), card)
            mask = Image.new("L", (cw, ch), 0)
            ImageDraw.Draw(mask).rounded_rectangle([0, 0, cw, ch], radius=24, fill=255)
            border = Image.new("RGBA", (cw + 8, ch + 8), (0, 0, 0, 0))
            ImageDraw.Draw(border).rounded_rectangle([0, 0, cw + 7, ch + 7], radius=26, fill=PANEL_ELEV, outline=(255, 255, 255, 20), width=1)
            layer.putalpha(mask)
            img.paste(border, (W - PAD - cw - 28, PAD + 14), border)
            img.paste(layer, (W - PAD - cw - 24, PAD + 18), layer)
    except Exception:
        pass

    kda_show = None
    acs_show = None
    if tiene_datos_db and db_stats:
        tk = db_stats.get("tk") or 0
        td = db_stats.get("td") or 0
        ta = db_stats.get("ta") or 0
        kda_show = round((tk + ta) / max(td, 1), 2) if db_stats.get("total_matches") else None
        acs_show = db_stats.get("acs_medio")
    adr_show = db_stats.get("adr_medio") if (tiene_datos_db and db_stats) else s.get("adr")
    kast_show = db_stats.get("kast_medio") if (tiene_datos_db and db_stats) else s.get("kast")
    dda_show = db_stats.get("dda_medio") if (tiene_datos_db and db_stats) else (s.get("dda") or s.get("damage_delta"))

    cards = [
        ("KDA", fmt_num(kda_show, 2) if kda_show is not None else str(s.get("kda", "0"))),
        ("ACS", fmt_num(acs_show) if acs_show is not None else str(s.get("acs", "0"))),
        ("ADR", fmt_num(adr_show)),
        ("HS%", f"{s.get('hs', 0)}%"),
        ("KAST", fmt_num(kast_show, suffix="%")),
    ]

    top_y = 168
    gap = 14
    card_w = int((W - PAD * 2 - gap * 4) / 5)
    for i, (label, value) in enumerate(cards):
        x1 = PAD + i * (card_w + gap)
        x2 = x1 + card_w
        rounded_box(x1, top_y, x2, top_y + 112, 22, PANEL_SOFT, outline=LINE)
        rounded_box(x1 + 12, top_y + 12, x1 + 58, top_y + 38, 13, PANEL_ELEV)
        text(x1 + 35, top_y + 26, label, _FM(14), MUTED, anchor="mm")
        text(x1 + 20, top_y + 56, value, _FB(32), TEXT)
        draw.line([(x1 + 18, top_y + 92), (x2 - 18, top_y + 92)], fill=(255, 255, 255, 10), width=1)
        text(x1 + 20, top_y + 97, "Actual", _FR(13), FAINT)

    mid_y = 300
    left_w = 520
    rounded_box(PAD, mid_y, PAD + left_w, H - PAD, 24, PANEL_SOFT, outline=LINE)
    rounded_box(PAD + left_w + 18, mid_y, W - PAD, H - PAD, 24, PANEL_SOFT, outline=LINE)

    text(PAD + 24, mid_y + 24, "Resumen de partidas", _FB(20), TEXT)
    text(PAD + 24, mid_y + 52, "Tu base manda cuando ya hay histórico guardado.", _FR(15), FAINT)

    delta_color = POS if (_safe_float(dda_show) >= 0) else NEG
    db_rows = [
        ("DDA / Ronda", fmt_num(dda_show), delta_color),
        ("Winrate", fmt_num(db_stats.get("winrate") if tiene_datos_db else None, suffix="%"), TEXT),
        ("Partidas", str(db_stats.get("total_matches")) if (tiene_datos_db and db_stats and db_stats.get("total_matches") is not None) else "—", TEXT),
        ("Tendencia", str(db_stats.get("trend", "—")) if (tiene_datos_db and db_stats and db_stats.get("trend") is not None) else str(s.get("trend", "—")), TEXT),
    ]
    row_y = mid_y + 98
    for idx, (label, value, color) in enumerate(db_rows):
        y1 = row_y + idx * 50
        rounded_box(PAD + 20, y1 - 10, PAD + left_w - 20, y1 + 28, 14, PANEL_ELEV if idx == 0 else PANEL, outline=(255,255,255,10))
        text(PAD + 38, y1, label, _FM(15), MUTED)
        text(PAD + left_w - 34, y1 - 1, value, _FB(23), color, anchor="ra")

    rx = PAD + left_w + 18
    text(rx + 24, mid_y + 24, "Última partida", _FB(20), TEXT)
    text(rx + 24, mid_y + 52, "Lectura rápida del último match detectado.", _FR(15), FAINT)
    lm = s.get("last_match", {}) or {}
    won = lm.get("won")
    result_txt = "Victoria" if won else "Derrota"
    result_col = POS if won else NEG
    rounded_box(rx + 24, mid_y + 88, rx + 168, mid_y + 126, 16, PANEL_ELEV)
    text(rx + 96, mid_y + 107, result_txt, _FM(20), result_col, anchor="mm")
    text(rx + 24, mid_y + 154, f"{lm.get('agente', '?')} · {lm.get('kills', 0)}/{lm.get('deaths', 0)}/{lm.get('assists', 0)} · ACS {lm.get('acs', 0)}", _FM(18), TEXT)
    text(rx + 24, mid_y + 188, f"ADR {fmt_num(lm.get('adr'))} · KAST {fmt_num(lm.get('kast'), suffix='%')} · DDA {fmt_num(lm.get('dda'))}", _FR(16), MUTED)
    text(rx + 24, mid_y + 220, f"Mapa: {s.get('mapa', '?')} · Modo: {s.get('modo', '?')}", _FR(16), MUTED)

    text(rx + 24, mid_y + 266, "Agentes más jugados", _FM(15), FAINT)
    agents = [a for a in top_agents_db if a != "Desconocido"][:5]
    badge_y = mid_y + 294
    cur_x = rx + 24
    for agent in agents:
        tw = draw.textbbox((0, 0), agent, font=_FM(15))[2]
        bw = tw + 30
        rounded_box(cur_x, badge_y, cur_x + bw, badge_y + 34, 17, PANEL_ELEV, outline=(255, 255, 255, 16))
        text(cur_x + 15, badge_y + 8, agent, _FM(15), TEXT)
        cur_x += bw + 10

    mask_img = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask_img).rounded_rectangle([0, 0, W, H], radius=30, fill=255)
    img.putalpha(mask_img)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


@bot.event
async def on_ready():
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
    print("✅ Base de datos lista y estructurada.")
    print(f"✅ Bot listo en Discord: {bot.user}")
    await bot.tree.sync()
    if not vigilante_partidas.is_running():
        vigilante_partidas.start()


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
            modo_formateado = s.get("modo", "Unrated").capitalize()
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
                    adr, kast, dda, rounds_played, damage_dealt_total, damage_received_total, kast_rounds
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18)
                """,
                match_id, nombre, tag, k, d, a, acs, won, mapa, modo_formateado, agente,
                tracker_metrics["adr"], tracker_metrics["kast"], tracker_metrics["dda"],
                tracker_metrics["rounds_played"], tracker_metrics["damage_dealt_total"],
                tracker_metrics["damage_received_total"], tracker_metrics["kast_rounds"],
            )

            if es_primera_vez:
                continue

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
    await interaction.response.defer()
    modo_busqueda = modo.value if modo else "Competitive"
    modo_display = modo.name if modo else "Competitivo"
    if modo_busqueda == "%":
        modo_display = "Todos los modos"

    s, err = await fetch_stats(nombre, tag, region)
    if err or not s:
        await interaction.followup.send(f"❌ Fallo al buscar a {nombre}#{tag}: {err}")
        return

    db_stats = await bot.db.fetchrow(
        """
        SELECT
            SUM(kills) as tk,
            SUM(deaths) as td,
            SUM(assists) as ta,
            AVG(acs) as acs_medio,
            AVG(CASE WHEN rounds_played > 0 AND damage_dealt_total IS NOT NULL
                     THEN damage_dealt_total::numeric / rounds_played
                     ELSE adr END) as adr_medio,
            AVG(CASE WHEN rounds_played > 0 AND kast_rounds IS NOT NULL
                     THEN (kast_rounds::numeric * 100.0) / rounds_played
                     ELSE kast END) as kast_medio,
            AVG(CASE WHEN rounds_played > 0 AND damage_dealt_total IS NOT NULL AND damage_received_total IS NOT NULL
                     THEN (damage_dealt_total::numeric - damage_received_total::numeric) / rounds_played
                     ELSE dda END) as dda_medio,
            COUNT(CASE WHEN won THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0) as winrate,
            COUNT(*) as total_matches
        FROM partidas
        WHERE jugador_nombre = $1 AND jugador_tag = $2 AND modo ILIKE $3
        """,
        nombre, tag, modo_busqueda,
    )

    agent_rows = await bot.db.fetch(
        """
        SELECT agente, COUNT(*) as count
        FROM partidas
        WHERE jugador_nombre = $1 AND jugador_tag = $2 AND modo ILIKE $3
        GROUP BY agente
        ORDER BY count DESC
        """,
        nombre, tag, modo_busqueda,
    )

    top_agents_db = [r["agente"] for r in agent_rows]
    tiene_datos_db = db_stats and db_stats["total_matches"] > 0
    buf = await asyncio.to_thread(generar_tarjeta, s, modo_display, tiene_datos_db, db_stats or {}, top_agents_db)
    archivo = discord.File(fp=buf, filename="stats.png")

    embed = discord.Embed(color=0x9333EA if s.get("smurf") else 0xFF4655)
    embed.set_image(url="attachment://stats.png")
    if tiene_datos_db and top_agents_db:
        links = []
        for agent in top_agents_db:
            if agent == "Desconocido":
                continue
            links.append(f"[{agent}](https://lineupsvalorant.com/?agent={urllib.parse.quote(agent)})")
        if links:
            embed.add_field(name="📚 Setups", value=" · ".join(links), inline=False)

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
               COUNT(CASE WHEN p.won THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0) as winrate,
               (
                   SELECT agente FROM partidas p2
                   WHERE p2.jugador_nombre = p.jugador_nombre AND p2.jugador_tag = p.jugador_tag AND p2.modo ILIKE $2
                   GROUP BY agente ORDER BY COUNT(*) DESC LIMIT 1
               ) as main_agent
        FROM partidas p
        JOIN jugadores j ON p.jugador_nombre = j.nombre AND p.jugador_tag = j.tag
        WHERE j.server_id = $1 AND p.modo ILIKE $2
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
        stats_txt = f"**ACS:** {acs_val} | **KDA:** {kda_val} | **Partidas:** {p['total_matches']}"
        if extras:
            stats_txt += "\n" + " | ".join(extras)
        main_agent = p["main_agent"] or "Desconocido"
        embed.add_field(name=f"{medalla} {p['nombre']}#{p['tag']} ({main_agent})", value=stats_txt, inline=False)

    await interaction.followup.send(embed=embed)


bot.run(TOKEN)