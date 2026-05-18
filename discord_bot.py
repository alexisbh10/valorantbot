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

import json


MODOS_DISCORD = [
    app_commands.Choice(name="Competitivo (Ranked 5v5)", value="Competitive"),
    app_commands.Choice(name="Skirmish (1v1)", value="Skirmish 1v1"),
    app_commands.Choice(name="Skirmish (2v2)", value="Skirmish 2v2"),
    app_commands.Choice(name="No Competitivo (Unrated)", value="Unrated"),
    app_commands.Choice(name="Swiftplay", value="Swiftplay"),
    app_commands.Choice(name="Todos los modos", value="%")
]

LINEUPS_BASE = "https://lineupsvalorant.com/?agent="

AGENTES_VALORANT = [
    "Astra", "Breach", "Brimstone", "Chamber", "Clove", "Cypher", "Deadlock",
    "Fade", "Gekko", "Harbor", "Iso", "Jett", "KAY/O", "Killjoy", "Neon",
    "Omen", "Phoenix", "Raze", "Reyna", "Sage", "Skye", "Sova", "Tejo",
    "Viper", "Vyse", "Yoru"
]

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
TRACKER_URL = os.getenv("TRACKER_URL", "http://localhost:8000")
DATABASE_URL = os.getenv("DATABASE_URL")

logging.basicConfig(level=logging.INFO)
bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
CANAL_ALERTAS_ID = 1496883989867139102


FONTS_DIR = "/app/assets/fonts"

def _bc_eb(s): return ImageFont.truetype(f"{FONTS_DIR}/BarlowCondensed-ExtraBold.ttf", s)
def _bc_b(s):  return ImageFont.truetype(f"{FONTS_DIR}/BarlowCondensed-Bold.ttf", s)
def _bc_m(s):  return ImageFont.truetype(f"{FONTS_DIR}/BarlowCondensed-Medium.ttf", s)
def _bc_r(s):  return ImageFont.truetype(f"{FONTS_DIR}/BarlowCondensed-Regular.ttf", s)


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

    _adr_raw = s.get("adr") or lm.get("adr")
    adr = round(damage_dealt_total / rounds_played, 2) if rounds_played > 0 and damage_dealt_total > 0 else \
        round(_safe_float(_adr_raw), 2) if _adr_raw is not None and _safe_float(_adr_raw) > 0 else None

    _dda_raw = s.get("damage_delta") or s.get("dda") or lm.get("damage_delta") or lm.get("dda")
    dda = round((damage_dealt_total - damage_received_total) / rounds_played, 2) if rounds_played > 0 and (damage_dealt_total or damage_received_total) else \
        round(_safe_float(_dda_raw), 2) if _dda_raw is not None else None

    _kast_raw = s.get("kast") or lm.get("kast")
    kast = round((kast_rounds / rounds_played) * 100, 2) if rounds_played > 0 and kast_rounds > 0 else \
        round(_safe_float(_kast_raw), 2) if _kast_raw is not None and _safe_float(_kast_raw) > 0 else None
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

def mix(c1, c2, t):
    return tuple(int(c1[i]*(1-t) + c2[i]*t) for i in range(3))

def fmt_num(v, digits=1, suffix=""):
    if v is None: return "—"
    try: return f"{round(float(v), digits)}{suffix}"
    except: return f"{v}{suffix}"

def generar_tarjeta(s, modo_display, tiene_datos_db, db_stats, top_agents_db, matches=None):
    acc1, acc2 = _rank_palette(s.get("rank", ""))
    W, H = 1180, 680
    PAD = 44

    TEXT  = (244, 247, 252, 255)
    MUTED = (160, 168, 185, 255)
    FAINT = (255, 255, 255, 22)
    POS   = (92,  224, 152, 255)
    NEG   = (239, 106, 106, 255)
    WARN  = (255, 185, 70,  255)

    def text(x, y, val, font, fill, anchor=None):
        draw.text((x, y), str(val), font=font, fill=fill, anchor=anchor)

    def soft_badge(x1, y1, x2, y2, fill, outline=None):
        draw.rounded_rectangle([x1,y1,x2,y2], radius=16, fill=fill, outline=outline, width=1)

    # ── FONDO: imagen del mapa + gradiente de rango ───────────────────────────
    MAP_SPLASHES = {
        "Ascent":    "https://media.valorant-api.com/maps/7eaecc1b-4337-bbf6-6ab9-04b8f06b3319/splash.png",
        "Bind":      "https://media.valorant-api.com/maps/2c9d57ec-4431-9c5e-11ef-ba7ae662c694/splash.png",
        "Haven":     "https://media.valorant-api.com/maps/2bee0dc9-4ffe-519b-1cbd-7825631b7aa5/splash.png",
        "Split":     "https://media.valorant-api.com/maps/d960549e-485c-e861-8d71-aa9d1aed12a2/splash.png",
        "Fracture":  "https://media.valorant-api.com/maps/b529448b-4d60-346e-e89e-00a4c527a405/splash.png",
        "Breeze":    "https://media.valorant-api.com/maps/2fb9a4fd-47a7-3e68-9c03-d38d1b7caabd/splash.png",
        "Icebox":    "https://media.valorant-api.com/maps/e2ad5c54-4114-a870-9641-8ea21279579a/splash.png",
        "Pearl":     "https://media.valorant-api.com/maps/fd267378-4d1d-484f-ff52-77821ed10dc2/splash.png",
        "Lotus":     "https://media.valorant-api.com/maps/2fe4ed3a-450a-01be-2339-95a5b1ac8d53/splash.png",
        "Sunset":    "https://media.valorant-api.com/maps/92584fbe-486a-b1b2-9faa-39b0f486b498/splash.png",
        "Abyss":     "https://media.valorant-api.com/maps/224b0a95-48b9-f703-1bd8-67aca101a61f/splash.png",
    }

    # Extraer subdivisión del rango para ajustar opacidad del overlay
    rank_str = s.get("rank", "")
    subdivision = 1
    for part in rank_str.split():
        if part in ("1", "2", "3"):
            subdivision = int(part)
            break
    # 1 = más oscuro/saturado, 3 = más claro/brillante
    overlay_alpha = {1: 0.82, 2: 0.74, 3: 0.66}.get(subdivision, 0.74)

    mapa_nombre = s.get("mapa", "")
    map_url = MAP_SPLASHES.get(mapa_nombre)
    fondo_ok = False
    if map_url:
        try:
            mapa_img = Image.open(io.BytesIO(requests.get(map_url, timeout=6).content)).convert("RGBA")
            mapa_img = mapa_img.resize((W, H), Image.Resampling.LANCZOS)
            # Desaturar levemente para no competir con el texto
            import PIL.ImageEnhance
            mapa_img = PIL.ImageEnhance.Color(mapa_img).enhance(0.55)
            img = mapa_img.copy()
            fondo_ok = True
        except:
            pass

    if not fondo_ok:
        img = Image.new("RGBA", (W, H))

    draw = ImageDraw.Draw(img)

    # Overlay gradiente del rango encima del mapa
    overlay = Image.new("RGBA", (W, H))
    od = ImageDraw.Draw(overlay)
    top_bg    = mix(acc1, (8, 10, 16), overlay_alpha)
    bottom_bg = mix(acc2, (3, 4, 8),  overlay_alpha + 0.06)
    for y in range(H):
        t = y / max(H-1, 1)
        c = mix(top_bg, bottom_bg, t)
        od.line([(0,y),(W,y)], fill=(*c, 210), width=1)
    img = Image.alpha_composite(img.convert("RGBA"), overlay)

    # Glow de esquinas
    glow = Image.new("RGBA", (W, H), (0,0,0,0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((-200,-140,360,340), fill=(*acc1,25))
    gd.ellipse((W-360,H-300,W+100,H+100), fill=(*acc2,20))
    img = Image.alpha_composite(img, glow)
    draw = ImageDraw.Draw(img)

    # ── HEADER ──────────────────────────────────────────────────────────────
    icon_x, icon_y, icon_size = PAD, 20, 90
    try:
        icon_url = s.get("rank_icon") or ""
        if icon_url:
            ri = Image.open(io.BytesIO(requests.get(icon_url,timeout=6).content)).convert("RGBA").resize((icon_size,icon_size))
            img.paste(ri,(icon_x,icon_y),ri)
            draw = ImageDraw.Draw(img)
    except: pass

    hx = icon_x + icon_size + 18
    nombre = s.get('nombre','?')
    tag    = s.get('tag','?')
    draw.text((hx, 16), nombre, font=_bc_eb(54), fill=TEXT)
    name_w = draw.textlength(nombre, font=_bc_eb(54))
    draw.text((hx + name_w + 8, 28), f"#{tag}", font=_bc_m(34), fill=MUTED)
    draw.text((hx, 80), f"{s.get('rank','Unranked')}  ·  {s.get('rr',0)} RR  ·  Nivel {s.get('nivel','?')}", font=_bc_m(22), fill=MUTED)
    draw.text((hx, 106), modo_display, font=_bc_r(18), fill=(*acc1,210))

    try:
        profile_url = s.get("card") or s.get("player_card") or s.get("avatar") or ""
        if profile_url:
            pf = Image.open(io.BytesIO(requests.get(profile_url,timeout=6).content)).convert("RGBA")
            sw,sh = 200,108
            sc = min(sw/pf.width, sh/pf.height)
            pf = pf.resize((int(pf.width*sc),int(pf.height*sc)),Image.Resampling.LANCZOS)
            img.paste(pf,(W-PAD-sw+(sw-pf.width)//2, 11+(sh-pf.height)//2), pf)
            draw = ImageDraw.Draw(img)
    except: pass

    DIV1 = 132
    draw.line([(PAD,DIV1),(W-PAD,DIV1)], fill=(255,255,255,28), width=1)

    # ── METRICS BAR ─────────────────────────────────────────────────────────
    wr_val = float(db_stats.get("winrate") or s.get("winrate") or 0)
    wr_col = POS if wr_val >= 50 else WARN if wr_val >= 45 else NEG

    metrics = [
        ("KDA", fmt_num(db_stats.get("kda") if tiene_datos_db else s.get("kda"), 2),          None,   True),
        ("ACS", fmt_num(db_stats.get("acs_medio") if tiene_datos_db else s.get("acs"), 1),    None,   False),
        ("HS",  fmt_num(db_stats.get("hs_medio") if tiene_datos_db else s.get("hs"), 1, "%"), None,   False),
        ("WR",  fmt_num(wr_val, 1, "%"),                                                       wr_col, False),
        ("ADR", fmt_num(db_stats.get("adr_medio") if tiene_datos_db else s.get("adr"), 1),    None,   False),
    ]

    MY = DIV1 + 12
    col_w = (W - PAD*2) // 5
    for i, (label, value, accent, is_hero) in enumerate(metrics):
        x = PAD + i * col_w
        draw.text((x, MY+2),  label, font=_bc_m(14), fill=MUTED)
        draw.text((x, MY+20), value, font=_bc_eb(38 if is_hero else 30), fill=accent or TEXT)
        if i < len(metrics)-1:
            draw.line([(x+col_w-2, MY+4),(x+col_w-2, MY+62)], fill=(255,255,255,16), width=1)

    DIV2 = MY + 74
    draw.line([(PAD,DIV2),(W-PAD,DIV2)], fill=(255,255,255,22), width=1)

    # ── BODY ────────────────────────────────────────────────────────────────
    BY = DIV2 + 20
    MID = 548
    RX  = MID + 38

    # ── Racha desde matches ──────────────────────────────────────────────────
    racha = 0
    racha_tipo = None
    for m in (matches or [])[:10]:
        resultado = m.get("won")
        if resultado is None:
            continue
        tipo = "W" if resultado else "L"
        if racha_tipo is None:
            racha_tipo = tipo
        if tipo == racha_tipo:
            racha += 1
        else:
            break

    # LEFT — Resumen
    draw.text((PAD, BY), "Resumen", font=_bc_eb(28), fill=TEXT)
    played = db_stats.get("total_matches", 0) if tiene_datos_db else 0
    draw.text((PAD, BY+34), f"{played} partidas analizadas", font=_bc_r(16), fill=MUTED)

    dda_val = db_stats.get("dda_medio") if tiene_datos_db else None
    try:
        dda_col = POS if dda_val and float(dda_val) > 0 else NEG if dda_val and float(dda_val) < 0 else TEXT
    except:
        dda_col = TEXT

    resumen = [
        ("KAST",             fmt_num(db_stats.get("kast_medio"),1,"%") if tiene_datos_db else "—", TEXT),
        ("DDA",              fmt_num(dda_val,1) if tiene_datos_db else "—",                        dda_col),
        ("Agente principal", (db_stats.get("main_agent") or s.get("agent") or "?") if tiene_datos_db else "—", TEXT),
    ]

    if racha_tipo and racha > 0:
        racha_col = POS if racha_tipo == "W" else NEG
        racha_txt = f"▲ {racha} VICTORIA{'S' if racha > 1 else ''}" if racha_tipo == "W" else f"▼ {racha} DERROTA{'S' if racha > 1 else ''}"
        resumen.append(("RACHA ACTUAL", racha_txt, racha_col))

    row_h = 58
    for idx, (lab, val, col) in enumerate(resumen):
        ry = BY + 80 + idx * row_h
        draw.text((PAD, ry),    lab, font=_bc_r(14), fill=MUTED)
        draw.text((PAD, ry+18), val, font=_bc_b(22), fill=col)
        if idx < len(resumen)-1:
            draw.line([(PAD, ry+row_h-6),(MID-18, ry+row_h-6)], fill=FAINT, width=1)

    draw.line([(MID,BY),(MID,H-PAD)], fill=(255,255,255,18), width=1)

    # RIGHT — Última partida
    lm = s.get("last_match",{}) or {}
    draw.text((RX, BY), "Última partida", font=_bc_eb(28), fill=TEXT)
    result_color = POS if lm.get("won") else NEG
    draw.text((W-PAD, BY+8), "Victoria" if lm.get("won") else "Derrota", font=_bc_eb(24), fill=result_color, anchor="ra")

    kda_str = f"{lm.get('kills',0)}/{lm.get('deaths',0)}/{lm.get('assists',0)}"
    draw.text((RX, BY+34), kda_str, font=_bc_eb(52), fill=TEXT)

    ag_last = lm.get("agente","")
    if ag_last:
        aw = max(90, 24 + int(draw.textlength(ag_last, font=_bc_m(15))))
        ax = RX + int(draw.textlength(kda_str, font=_bc_eb(52))) + 14
        ay = BY + 48
        soft_badge(ax, ay, ax+aw, ay+30, (*mix(acc1,(20,20,20),0.6),100), (*acc1,80))
        draw.text((ax+aw//2, ay+5), ag_last, font=_bc_m(15), fill=TEXT, anchor="ma")

    lm_y = BY + 102

    # DDA última partida en color
    lm_dda_val = lm.get("dda")
    try:
        lm_dda_col = POS if lm_dda_val is not None and float(lm_dda_val) > 0 \
                     else NEG if lm_dda_val is not None and float(lm_dda_val) < 0 \
                     else TEXT
    except:
        lm_dda_col = TEXT

    lm_metrics = [
        ("ACS",  fmt_num(lm.get("acs"),1),      TEXT),
        ("HS",   fmt_num(lm.get("hs"),1,"%"),    TEXT),
        ("ADR",  fmt_num(lm.get("adr"),1),       TEXT),
        ("KAST", fmt_num(lm.get("kast"),1,"%"),  TEXT),
        ("DDA",  fmt_num(lm_dda_val,1),          lm_dda_col),
    ]
    lm_col_w = (W - PAD - RX) // len(lm_metrics)
    for i,(lab,val,col) in enumerate(lm_metrics):
        lx = RX + i * lm_col_w
        draw.text((lx, lm_y),    lab, font=_bc_r(13), fill=MUTED)
        draw.text((lx, lm_y+16), val, font=_bc_b(20), fill=col)

    draw.line([(RX, lm_y+44),(W-PAD, lm_y+44)], fill=FAINT, width=1)

    # Mapa — dentro de última partida
    mapa_y = lm_y + 54
    draw.text((RX, mapa_y),    "MAPA", font=_bc_r(13), fill=MUTED)
    draw.text((RX, mapa_y+16), s.get("mapa","?"), font=_bc_b(20), fill=TEXT)

    draw.line([(RX, mapa_y+44),(W-PAD, mapa_y+44)], fill=FAINT, width=1)

    asy = mapa_y + 56
    draw.text((RX, asy), "Agentes más usados", font=_bc_eb(22), fill=TEXT)

    agents = top_agents_db[:5] if top_agents_db else (s.get("top_agents") or [])[:5]
    agents = [a for a in agents if a] or [s.get("agent","Desconocido")]

    bx, by_ = RX, asy + 32
    for ag in agents:
        ag_font = _bc_m(15)
        aw2 = max(90, 24 + int(draw.textlength(ag, font=ag_font)))
        if bx + aw2 > W - PAD - 10:
            bx = RX; by_ += 46
        soft_badge(bx, by_, bx+aw2, by_+36, (*mix(acc1,(20,20,20),0.6),100), (*acc1,60))
        draw.text((bx+aw2//2, by_+6), ag, font=ag_font, fill=TEXT, anchor="ma")
        bx += aw2 + 8

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
        SELECT
            p.match_id, p.kills, p.deaths, p.assists, p.acs, p.won, p.mapa, p.modo,
            p.agente, p.adr, p.kast, p.dda, p.rounds_played, p.damage_dealt_total,
            p.damage_received_total, p.kast_rounds, p.hs, p.fecha
        FROM partidas p
        JOIN jugadores j
          ON p.jugador_nombre = j.nombre AND p.jugador_tag = j.tag
        WHERE j.server_id = $1
          AND p.jugador_nombre = $2
          AND p.jugador_tag = $3
          AND ($4 = '%' OR LOWER(p.modo) = LOWER($4))
        ORDER BY p.fecha DESC
        LIMIT 120
        """,
        str(interaction.guild_id), nombre, tag, modo_busqueda,
    )

    filtered_rows = rows
    if not filtered_rows:
        await interaction.followup.send(f"❌ No hay partidas guardadas para **{nombre}#{tag}** en **{modo_display}**.")
        return

    tk = sum((r["kills"] or 0) for r in filtered_rows)
    td = sum((r["deaths"] or 0) for r in filtered_rows)
    ta = sum((r["assists"] or 0) for r in filtered_rows)

    db_stats = {
        "tk": tk,
        "td": td,
        "ta": ta,
        "kda": round((tk + ta) / max(td, 1), 2),
        "acs_medio": round(sum(float(r["acs"] or 0) for r in filtered_rows) / len(filtered_rows), 1),
        "adr_medio": round(sum(float(r["adr"] or 0) for r in filtered_rows) / len(filtered_rows), 1),
        "dda_medio": round(sum(float(r["dda"] or 0) for r in filtered_rows) / len(filtered_rows), 1),
        "hs_medio": round(sum(float(r["hs"] or 0) for r in filtered_rows) / len(filtered_rows), 1),
        "winrate": round(sum(1 for r in filtered_rows if r["won"]) * 100.0 / len(filtered_rows), 1),
        "total_matches": len(filtered_rows),
    }

    def _adr_row(r):
        return float(r["adr"] or 0)

    def _dda_row(r):
        return float(r["dda"] or 0)

    def _kast_row(r):
        if r["kast"] is not None:
            return float(r["kast"])
        return None

    db_stats = {
        "tk": tk,
        "td": td,
        "ta": ta,
        "kda": round((tk + ta) / max(td, 1), 2),
        "acs_medio": round(sum(float(r["acs"] or 0) for r in filtered_rows) / len(filtered_rows), 1),
        "adr_medio": round(sum(_adr_row(r) for r in filtered_rows) / len(filtered_rows), 1),
        "dda_medio": round(sum(_dda_row(r) for r in filtered_rows) / len(filtered_rows), 1),
        "hs_medio": round(sum(float(r["hs"] or 0) for r in filtered_rows) / len(filtered_rows), 1),
        "winrate": round(sum(1 for r in filtered_rows if r["won"]) * 100.0 / len(filtered_rows), 1),
        "total_matches": len(filtered_rows),
    }

    kast_vals = [_kast_row(r) for r in filtered_rows]
    kast_vals = [v for v in kast_vals if v is not None]
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
    s["kda"] = db_stats["kda"]
    s["adr"]     = db_stats["adr_medio"]      
    s["acs"]     = db_stats["acs_medio"]      
    s["hs"]      = db_stats["hs_medio"]       
    s["winrate"] = db_stats["winrate"]        
    s["dda"]     = db_stats["dda_medio"]      
    s["kast"]    = db_stats.get("kast_medio") 
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

    print(f"DEBUG stats keys: {list(s.keys())}")
    print(f"DEBUG last_match keys: {list((s.get('last_match') or {}).keys())}")
    try:
        buf = await asyncio.wait_for(
            asyncio.to_thread(generar_tarjeta, s, modo_display, tiene_datos_db, db_stats, top_agents_db, filtered_rows),
            timeout=20
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

# ── Helpers PIL compartidos para gráficas ────────────────────────────────────
_BG     = (10,  11, 17)
_PANEL  = (15,  17, 25)
_BORDER = (42,  48, 67)
_TEXT_G = (245, 247, 251)
_MUTED_G= (150, 163, 179)
_TEAL   = (79,  209, 197)
_RED_G  = (252, 129, 129)
_GOLD   = (246, 224, 94)
_GREEN_G= (104, 211, 145)
_PURPLE = (167, 139, 250)
_BLUE_G = (118, 228, 247)
import math as _math

CHART_COLORS = [_TEAL,_RED_G,_GOLD,_GREEN_G,_PURPLE,_BLUE_G,(251,211,141),(246,135,179),(154,230,180)]

def _gl(a,b,t): return tuple(int(a[i]*(1-t)+b[i]*t) for i in range(3))
def _rr2(d,x1,y1,x2,y2,r=6,fill=None,outline=None,w=1):
    d.rounded_rectangle([x1,y1,x2,y2],radius=r,fill=fill,outline=outline,width=w)

def _chart_base(W, H):
    img = Image.new("RGBA",(W,H))
    d   = ImageDraw.Draw(img)
    for y in range(H):
        t = y/max(H-1,1)
        c = _gl(_BG, tuple(max(0,v-6) for v in _BG), t)
        d.line([(0,y),(W,y)], fill=(*c,255))
    for cx,cy,rx,ry,col,al in [(-40,-30,260,200,_TEAL,14),(W+40,H+30,220,180,_RED_G,10)]:
        g = Image.new("RGBA",(W,H),(0,0,0,0))
        gd= ImageDraw.Draw(g)
        for i in range(6,0,-1):
            f=i/6
            gd.ellipse([cx-rx*f,cy-ry*f,cx+rx*f,cy+ry*f],fill=(*col,int(al*f*0.4)))
        img = Image.alpha_composite(img,g)
    return img

def _cheader(draw, W, PAD, title, sub=""):
    draw.text((PAD,14), title, font=_bc_eb(32), fill=(*_TEXT_G,240))
    if sub: draw.text((PAD,52), sub, font=_bc_r(18), fill=(*_MUTED_G,200))


# ── GRÁFICA 1: Evolución ACS / DDA / HS ─────────────────────────────────────

def gen_evolucion(rows, nombre_jugador):
    if not rows: return None
    W,H,PAD = 1180,660,44
    img  = _chart_base(W,H)
    draw = ImageDraw.Draw(img)
    fechas  = [r["fecha"].strftime("%d/%m") if hasattr(r.get("fecha",""),"strftime") else "" for r in rows]
    acs_v   = [float(r["acs"])    if r["acs"]        is not None else None for r in rows]
    dda_v   = [float(r["dda"])    if r["dda"]        is not None else None for r in rows]
    hs_v    = [float(r["hs"])     if r.get("hs")     is not None else None for r in rows]
    n       = len(rows)
    _cheader(draw, W, PAD, f"Evolución · {nombre_jugador}", f"{n} partidas  ·  ACS / DDA / HS%")
    panels  = [("ACS",acs_v,_TEAL,None),("DDA",dda_v,_RED_G,0.0),("HS%",hs_v,_GOLD,None)]
    TOP0    = 80; p_h = (H-TOP0-PAD)//3; GAP = 8
    for pi,(label,vals,color,zero) in enumerate(panels):
        pt = TOP0+pi*p_h+(GAP if pi>0 else 0); pb = pt+p_h-GAP
        lx = PAD+54; rx = W-PAD-12
        _rr2(draw,PAD,pt-4,W-PAD,pb+4,fill=(*_PANEL,180),outline=(*_BORDER,60))
        clean = [(i,v) for i,v in enumerate(vals) if v is not None]
        if not clean:
            draw.text((lx+8,(pt+pb)//2),"Sin datos",font=_bc_r(16),fill=(*_MUTED_G,150),anchor="lm"); continue
        xs,ys = zip(*clean)
        vmn,vmx,vmed = min(ys),max(ys),sum(ys)/len(ys)
        rng = max(vmx-vmn,1)
        def tp(i,v): return lx+(i/max(n-1,1))*(rx-lx), pb-((v-vmn)/rng)*(pb-pt-8)-4
        if zero is not None and vmn<=zero<=vmx:
            zy=pb-((zero-vmn)/rng)*(pb-pt-8)-4
            draw.line([(lx,zy),(rx,zy)],fill=(*_MUTED_G,60),width=1)
        my=pb-((vmed-vmn)/rng)*(pb-pt-8)-4
        draw.line([(lx,my),(rx,my)],fill=(*color,50),width=1)
        draw.text((rx+6,my),fmt_num(vmed,1),font=_bc_r(13),fill=(*_MUTED_G,180),anchor="lm")
        fl=Image.new("RGBA",(W,H),(0,0,0,0)); fld=ImageDraw.Draw(fl)
        pts=[(lx,pb)]+[tp(i,v) for i,v in clean]+[(tp(xs[-1],ys[-1])[0],pb)]
        fld.polygon(pts,fill=(*color,18)); img=Image.alpha_composite(img,fl); draw=ImageDraw.Draw(img)
        for i in range(len(xs)-1):
            lc=_gl(color,_GREEN_G,0.35) if ys[i+1]>=ys[i] else _gl(color,_RED_G,0.35)
            draw.line([tp(xs[i],ys[i]),tp(xs[i+1],ys[i+1])],fill=(*lc,220),width=3)
        for i,v in clean:
            px_,py_=tp(i,v); dc=_GREEN_G if v>=vmed else _RED_G
            draw.ellipse([px_-5,py_-5,px_+5,py_+5],fill=(*dc,200))
            draw.ellipse([px_-3,py_-3,px_+3,py_+3],fill=(*_TEXT_G,230))
        draw.text((PAD+8,(pt+pb)//2),label,font=_bc_eb(22),fill=(*color,230),anchor="lm")
        if pi==len(panels)-1:
            step=max(1,n//12)
            for i in range(0,n,step):
                px_,_=tp(i,vmn)
                draw.text((px_,pb+8),fechas[i] if i<len(fechas) else "",font=_bc_r(13),fill=(*_MUTED_G,160),anchor="mt")
    buf=io.BytesIO(); img.convert("RGB").save(buf,format="PNG",optimize=True); buf.seek(0); return buf


# ── GRÁFICA 2: Heatmap por mapa ──────────────────────────────────────────────

def gen_heatmap_mapas(rows):
    ms={}
    for r in rows:
        m=r["mapa"] or "?"
        if m not in ms: ms[m]={"acs":[],"won":[],"dda":[],"n":0}
        ms[m]["n"]+=1
        if r["acs"] is not None: ms[m]["acs"].append(float(r["acs"]))
        ms[m]["won"].append(1 if r["won"] else 0)
        if r["dda"] is not None: ms[m]["dda"].append(float(r["dda"]))
    mapas=sorted(ms.keys())
    if not mapas: return None
    cols=["MAPA","PARTIDAS","ACS","WR %","DDA"]; col_w=[180,110,110,100,110]
    ROW_H=52; HEAD_H=72; PAD=44
    W=PAD*2+sum(col_w)+20; H=HEAD_H+ROW_H*len(mapas)+PAD+20
    img=_chart_base(W,H); draw=ImageDraw.Draw(img)
    _cheader(draw,W,PAD,"Rendimiento por mapa")
    cx=PAD
    for col,cw in zip(cols,col_w):
        draw.text((cx+cw//2,HEAD_H-14),col,font=_bc_m(16),fill=(*_MUTED_G,200),anchor="mm"); cx+=cw
    all_acs=[sum(ms[m]["acs"])/len(ms[m]["acs"]) for m in mapas if ms[m]["acs"]]
    all_wr =[sum(ms[m]["won"])/len(ms[m]["won"])*100 for m in mapas]
    all_dda=[sum(ms[m]["dda"])/len(ms[m]["dda"]) if ms[m]["dda"] else None for m in mapas]
    def ncol(val,vals,hi=True):
        cl=[v for v in vals if v is not None]
        if not cl or max(cl)==min(cl): return _MUTED_G
        t=(val-min(cl))/(max(cl)-min(cl))
        if not hi: t=1-t
        return _GREEN_G if t>0.66 else _GOLD if t>0.33 else _RED_G
    for ri,m in enumerate(mapas):
        st=ms[m]; ry=HEAD_H+ri*ROW_H
        _rr2(draw,PAD,ry+3,W-PAD,ry+ROW_H-3,r=6,fill=(*(_PANEL if ri%2==0 else _BG),160))
        av=sum(st["acs"])/len(st["acs"]) if st["acs"] else None
        wv=sum(st["won"])/len(st["won"])*100
        dv=sum(st["dda"])/len(st["dda"]) if st["dda"] else None
        row=[(m,None),(str(st["n"]),_MUTED_G),(fmt_num(av,0),ncol(av,all_acs) if av else _MUTED_G),
             (fmt_num(wv,1,"%"),ncol(wv,all_wr)),(fmt_num(dv,1) if dv is not None else "—",ncol(dv,[v for v in all_dda if v is not None]) if dv is not None else _MUTED_G)]
        cx=PAD
        for ci,((txt,col),cw) in enumerate(zip(row,col_w)):
            draw.text((cx+cw//2,ry+ROW_H//2),txt,font=_bc_b(20) if ci==0 else _bc_m(20),fill=(*(col or _TEXT_G),230),anchor="mm"); cx+=cw
    buf=io.BytesIO(); img.convert("RGB").save(buf,format="PNG",optimize=True); buf.seek(0); return buf


# ── GRÁFICA 3: Donut agentes ─────────────────────────────────────────────────

def gen_pie_agentes(agent_rows, titulo="Agentes jugados"):
    ags=[r["agente"] for r in agent_rows if r["agente"] not in (None,"Desconocido")]
    cts=[r["count"]  for r in agent_rows if r["agente"] not in (None,"Desconocido")]
    if not ags: return None
    W,H=900,480; PAD=40; CX,CY=260,H//2; RO=170; RI=90
    img=_chart_base(W,H); draw=ImageDraw.Draw(img)
    _cheader(draw,W,PAD,titulo,f"{sum(cts)} partidas · {len(ags)} agentes")
    total=sum(cts); start=-90.0
    for i,(ag,cnt) in enumerate(zip(ags,cts)):
        col=CHART_COLORS[i%len(CHART_COLORS)]; ang=cnt/total*360
        s=Image.new("RGBA",(W,H),(0,0,0,0)); ds=ImageDraw.Draw(s)
        ds.pieslice([CX-RO,CY-RO,CX+RO,CY+RO],start,start+ang,fill=(*col,210))
        ds.ellipse([CX-RI,CY-RI,CX+RI,CY+RI],fill=(0,0,0,0))
        img=Image.alpha_composite(img,s); draw=ImageDraw.Draw(img)
        if cnt/total>0.05:
            mid=start+ang/2
            lx=CX+(RI+(RO-RI)*0.55)*_math.cos(_math.radians(mid))
            ly=CY+(RI+(RO-RI)*0.55)*_math.sin(_math.radians(mid))
            draw.text((lx,ly),f"{cnt/total*100:.0f}%",font=_bc_b(16),fill=(*_TEXT_G,230),anchor="mm")
        start+=ang
    draw.ellipse([CX-RI,CY-RI,CX+RI,CY+RI],fill=(*_PANEL,255))
    draw.text((CX,CY-12),str(total),font=_bc_eb(34),fill=(*_TEXT_G,240),anchor="mm")
    draw.text((CX,CY+18),"partidas",font=_bc_r(16),fill=(*_MUTED_G,200),anchor="mm")
    
    # Área de lista derecha alineada perfectamente
    LX=CX+RO+40
    BAR_W = 210 # Tamaño fijo y limpio para la barra horizontal
    
    for i,(ag,cnt) in enumerate(zip(ags,cts)):
        col=CHART_COLORS[i%len(CHART_COLORS)]
        ly=95+i*48 # Control del espaciado de filas
        if ly+24>H-PAD: break
        
        # 1. Cuadrado de color del agente
        _rr2(draw,LX,ly+2,LX+16,ly+18,r=4,fill=(*col,220))
        
        # 2. Nombre del agente (Alineado a la izquierda en el mismo eje horizontal)
        draw.text((LX+24,ly+10),ag,font=_bc_b(18),fill=(*_TEXT_G,230),anchor="lm")
        
        # 3. Cálculo del porcentaje exacto y renderizado de la barra de progreso
        pct = cnt/total
        bar_start_x = LX + 130 # Eje X estático donde comienzan todas las barras
        
        # Fondo sutil de la barra (100%)
        draw.rounded_rectangle([bar_start_x, ly+6, bar_start_x+BAR_W, ly+14], radius=4, fill=(*col,40))
        # Relleno real acorde al porcentaje
        w_bar = max(int(BAR_W*pct), 8)
        draw.rounded_rectangle([bar_start_x, ly+6, bar_start_x+w_bar, ly+14], radius=4, fill=(*col,200))
        
        # 4. Texto de porcentaje (Alineado al extremo derecho de la tarjeta)
        draw.text((W-PAD, ly+10),f"{pct*100:.0f}%",font=_bc_m(17),fill=(*_MUTED_G,200),anchor="rm")

    buf=io.BytesIO(); img.convert("RGB").save(buf,format="PNG",optimize=True); buf.seek(0); return buf

# ── GRÁFICA 4: Comparativa barras ────────────────────────────────────────────

def gen_barra_comparativa(stats_a, nombre_a, stats_b, nombre_b):
    mets=["ACS","KDA","ADR","KAST %","DDA","WR %","HS %"]
    def kda(s): return round((float(s.get("tk") or 0)+float(s.get("ta") or 0))/max(float(s.get("td") or 1),1),2)
    va=[float(stats_a.get("acs_medio") or 0),kda(stats_a),float(stats_a.get("adr_medio") or 0),
        float(stats_a.get("kast_medio") or 0),float(stats_a.get("dda_medio") or 0),
        float(stats_a.get("winrate") or 0),float(stats_a.get("hs_medio") or 0)]
    vb=[float(stats_b.get("acs_medio") or 0),kda(stats_b),float(stats_b.get("adr_medio") or 0),
        float(stats_b.get("kast_medio") or 0),float(stats_b.get("dda_medio") or 0),
        float(stats_b.get("winrate") or 0),float(stats_b.get("hs_medio") or 0)]
    
    # Aumentamos HEAD_H a 125 para dar espacio vertical y evitar solapamientos
    n=len(mets); ROW_H=70; PAD=44; HEAD_H=125; W=1000; H=HEAD_H+n*ROW_H+PAD
    img=_chart_base(W,H); draw=ImageDraw.Draw(img)
    _cheader(draw,W,PAD,f"{nombre_a}  vs  {nombre_b}","Comparativa de métricas competitivas")
    
    # Reducimos el espacio central muerto para que las barras sean más largas y legibles
    MID=W//2; BAR_MAX=MID-PAD-65 
    
    # Movemos las leyendas hacia abajo (Y=82) para que nunca toquen el título principal
    _rr2(draw,MID-140,82,MID-10,106,r=4,fill=(*_TEAL,180))
    draw.text((MID-75,94),nombre_a[:16],font=_bc_m(16),fill=(*_TEXT_G,230),anchor="mm")
    _rr2(draw,MID+10,82,MID+140,106,r=4,fill=(*_RED_G,180))
    draw.text((MID+75,94),nombre_b[:16],font=_bc_m(16),fill=(*_TEXT_G,230),anchor="mm")
    
    for i,(met,a,b) in enumerate(zip(mets,va,vb)):
        ry=HEAD_H+i*ROW_H
        if i%2==0: _rr2(draw,PAD,ry+4,W-PAD,ry+ROW_H-4,r=6,fill=(*_PANEL,140))
        draw.text((MID,ry+ROW_H//2),met,font=_bc_eb(22),fill=(*_MUTED_G,200),anchor="mm")
        
        vmx=max(abs(a),abs(b),0.01)
        
        # Barra Jugador A (Teal / Izquierda)
        ba=max(int(BAR_MAX*abs(a)/vmx), 8) 
        _rr2(draw,MID-65-ba,ry+18,MID-65,ry+ROW_H-18,r=4,fill=(*_TEAL,200))
        # Número dentro de la barra (color blanco para contraste)
        draw.text((MID-75,ry+ROW_H//2),fmt_num(a,1),font=_bc_b(20),fill=(255,255,255,255),anchor="rm")
        
        # Barra Jugador B (Rojo / Derecha)
        bb=max(int(BAR_MAX*abs(b)/vmx), 8)
        _rr2(draw,MID+65,ry+18,MID+65+bb,ry+ROW_H-18,r=4,fill=(*_RED_G,200))
        # Número dentro de la barra (color blanco para contraste)
        draw.text((MID+75,ry+ROW_H//2),fmt_num(b,1),font=_bc_b(20),fill=(255,255,255,255),anchor="lm")
        
    buf=io.BytesIO(); img.convert("RGB").save(buf,format="PNG",optimize=True); buf.seek(0); return buf


# ── GRÁFICA 5: Precisión HS% ─────────────────────────────────────────────────

def gen_precision(rows, nombre_jugador):
    hd=[(r["fecha"].strftime("%d/%m") if hasattr(r.get("fecha",""),"strftime") else "",float(r["hs"]))
        for r in rows if r.get("hs") is not None]
    if not hd: return None
    fechas,vals=zip(*hd); n=len(vals); media=sum(vals)/n
    movil=[sum(vals[max(0,i-1):i+2])/len(vals[max(0,i-1):i+2]) for i in range(n)]
    W,H,PAD=1180,380,44
    img=_chart_base(W,H); draw=ImageDraw.Draw(img)
    _cheader(draw,W,PAD,f"Precisión HS% · {nombre_jugador}",
             f"Media {media:.1f}%   Mejor {max(vals):.1f}%   Peor {min(vals):.1f}%   {n} partidas")
    LEFT=PAD+54; RIGHT=W-PAD-16; TOP=80; BOT=H-46
    vmn=max(0,min(vals)-6); vmx=max(vals)+6; rng=max(vmx-vmn,1)
    def tp(i,v): return LEFT+(i/max(n-1,1))*(RIGHT-LEFT), BOT-((v-vmn)/rng)*(BOT-TOP)
    for ti in range(5):
        tv=vmn+(rng/4)*ti; ty=BOT-((tv-vmn)/rng)*(BOT-TOP)
        draw.line([(LEFT,ty),(RIGHT,ty)],fill=(*_BORDER,40),width=1)
        draw.text((LEFT-8,ty),f"{tv:.0f}%",font=_bc_r(13),fill=(*_MUTED_G,160),anchor="rm")
    my=BOT-((media-vmn)/rng)*(BOT-TOP)
    draw.line([(LEFT,my),(RIGHT,my)],fill=(*_MUTED_G,50),width=1)
    draw.text((RIGHT+6,my),f"{media:.1f}%",font=_bc_m(14),fill=(*_MUTED_G,200),anchor="lm")
    fl=Image.new("RGBA",(W,H),(0,0,0,0)); fld=ImageDraw.Draw(fl)
    fld.polygon([(LEFT,BOT)]+[tp(i,v) for i,v in enumerate(vals)]+[(RIGHT,BOT)],fill=(*_GOLD,22))
    img=Image.alpha_composite(img,fl); draw=ImageDraw.Draw(img)
    for i in range(n-1):
        lc=_gl(_GOLD,_GREEN_G,0.4) if vals[i+1]>vals[i] else _gl(_GOLD,_RED_G,0.4)
        draw.line([tp(i,vals[i]),tp(i+1,vals[i+1])],fill=(*lc,220),width=3)
    for i in range(n-1):
        x0,y0=tp(i,movil[i]); x1,y1=tp(i+1,movil[i+1])
        for s in range(6):
            if s%2==0:
                draw.line([(x0+(x1-x0)*s/6,y0+(y1-y0)*s/6),(x0+(x1-x0)*(s+1)/6,y0+(y1-y0)*(s+1)/6)],fill=(*_RED_G,180),width=2)
    for i,v in enumerate(vals):
        px_,py_=tp(i,v); dc=_GREEN_G if v>=media else _RED_G
        draw.ellipse([px_-5,py_-5,px_+5,py_+5],fill=(*dc,200))
        draw.ellipse([px_-3,py_-3,px_+3,py_+3],fill=(*_TEXT_G,230))
    step=max(1,n//12)
    for i in range(0,n,step):
        px_,_=tp(i,vmn)
        draw.text((px_,BOT+6),fechas[i] if i<len(fechas) else "",font=_bc_r(13),fill=(*_MUTED_G,160),anchor="mt")
    lx=W-PAD-220; ly=12
    _rr2(draw,lx-10,ly-2,W-PAD,ly+62,r=8,fill=(*_PANEL,220))
    draw.line([(lx,ly+16),(lx+28,ly+16)],fill=(*_GOLD,210),width=3)
    draw.text((lx+36,ly+10),"HS% real",font=_bc_m(16),fill=(*_TEXT_G,230))
    for s in range(4): draw.line([(lx+s*8,ly+44),(lx+s*8+6,ly+44)],fill=(*_RED_G,180),width=2)
    draw.text((lx+36,ly+38),"Media móvil",font=_bc_m(16),fill=(*_TEXT_G,220))
    buf=io.BytesIO(); img.convert("RGB").save(buf,format="PNG",optimize=True); buf.seek(0); return buf


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
            description="Stats de la última semana en Competitivo.",
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

    buf_evol = await asyncio.to_thread(gen_evolucion, rows, f"{nombre}#{tag}")
    archivos.append(discord.File(fp=buf_evol, filename="evolucion.png"))

    buf_hm = await asyncio.to_thread(gen_heatmap_mapas, rows)
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
    buf_pie = await asyncio.to_thread(gen_pie_agentes, agent_rows, f"Agentes — {nombre}#{tag}")
    if buf_pie:
        archivos.append(discord.File(fp=buf_pie, filename="agentes.png"))

    if modo_busqueda == "Competitive":
        buf_prec = await asyncio.to_thread(gen_precision, rows, f"{nombre}#{tag}")
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

    buf = await asyncio.to_thread(gen_barra_comparativa, dict(s1), f"{nombre1}#{tag1}", dict(s2), f"{nombre2}#{tag2}")
    archivo = discord.File(fp=buf, filename="comparar.png")

    def fmt(v, suf=""):
        return f"{round(float(v),1)}{suf}" if v is not None else "—"

    kda1 = round((float(s1["tk"] or 0) + float(s1["ta"] or 0)) / max(float(s1["td"] or 1),1), 2)
    kda2 = round((float(s2["tk"] or 0) + float(s2["ta"] or 0)) / max(float(s2["td"] or 1),1), 2)

    embed = discord.Embed(title=f"⚔️ {nombre1}#{tag1}  vs  {nombre2}#{tag2}", color=0x4fd1c5)
    embed.set_image(url="attachment://comparar.png")
    await interaction.followup.send(file=archivo, embed=embed)

@bot.tree.command(name="lineups", description="Muestra lineups de un agente")
@app_commands.describe(agente="Nombre del agente")
async def lineups(interaction: discord.Interaction, agente: str):
    await interaction.response.defer()
    url = f"{LINEUPS_BASE}{urllib.parse.quote(agente)}"
    embed = discord.Embed(
        title=f"📚 Lineups de {agente}",
        description=f"[Abrir lineups]({url})",
        color=0x4fd1c5,
    )
    await interaction.followup.send(embed=embed)

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

    buf_pie = await asyncio.to_thread(gen_pie_agentes, agent_rows_all, f"Agentes más jugados — {modo_display}")

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