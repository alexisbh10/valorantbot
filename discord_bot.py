import discord
from discord.ext import commands, tasks
from discord import app_commands
import requests
import os
import logging
import asyncio
import urllib.parse
import asyncpg
import io
import math as _math
from collections import Counter
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
from dotenv import load_dotenv
from google import genai

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
TRACKER_URL = os.getenv("TRACKER_URL", "http://localhost:10000")
DATABASE_URL = os.getenv("DATABASE_URL")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

logging.basicConfig(level=logging.INFO)
bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())

CANAL_ALERTAS_ID = 1496883989867139102

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

_BG      = (10,  11, 17)
_PANEL   = (15,  17, 25)
_BORDER  = (42,  48, 67)
_TEXT_G  = (245, 247, 251)
_MUTED_G = (150, 163, 179)
_TEAL    = (79,  209, 197)
_RED_G   = (252, 129, 129)
_GOLD    = (246, 224, 94)
_GREEN_G = (104, 211, 145)
_PURPLE  = (167, 139, 250)
_BLUE_G  = (118, 228, 247)
CHART_COLORS = [_TEAL, _RED_G, _GOLD, _GREEN_G, _PURPLE, _BLUE_G, (251,211,141), (246,135,179), (154,230,180)]

FONTS_DIR = "assets/fonts"

def _cargar_fuente_proyecto(nombre_fuente, tamano):
    ruta_completa = f"{FONTS_DIR}/{nombre_fuente}"
    try:
        return ImageFont.truetype(ruta_completa, tamano)
    except OSError:
        return ImageFont.load_default()

def _bc_eb(s): return _cargar_fuente_proyecto("BarlowCondensed-ExtraBold.ttf", s)
def _bc_b(s):  return _cargar_fuente_proyecto("BarlowCondensed-Bold.ttf", s)
def _bc_m(s):  return _cargar_fuente_proyecto("BarlowCondensed-Medium.ttf", s)
def _bc_r(s):  return _cargar_fuente_proyecto("BarlowCondensed-Regular.ttf", s)

def mix(c1, c2, t): return tuple(int(c1[i]*(1-t) + c2[i]*t) for i in range(3))
def _gl(a, b, t): return tuple(int(a[i]*(1-t)+b[i]*t) for i in range(3))
def _rr2(d,x1,y1,x2,y2,r=6,fill=None,outline=None,w=1):
    d.rounded_rectangle([x1,y1,x2,y2],radius=r,fill=fill,outline=outline,width=w)

def _safe_float(v, default=0.0):
    try: return float(v)
    except (TypeError, ValueError): return default

def _safe_int(v, default=0):
    try: return int(v)
    except (TypeError, ValueError): return default

def fmt_num(v, digits=1, suffix=""):
    if v is None: return "—"
    try: return f"{round(float(v), digits)}{suffix}"
    except: return f"{v}{suffix}"

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
        if key in r: return pal
    return ((255, 70, 85), (200, 20, 40))

# ==============================================================================
# ENGINES GRÁFICOS COMPLEMENTARIOS (PIL CANVAS v1.0.4)
# ==============================================================================
def gen_banner_notificacion(titulo, mensaje, color_neon=_TEAL):
    W, H = 750, 160
    img = Image.new("RGBA", (W, H))
    draw = ImageDraw.Draw(img)
    for y in range(H):
        t = y / (H - 1)
        c = _gl(_BG, (18, 22, 32), t)
        draw.line([(0, y), (W, y)], fill=(*c, 255))
    _rr2(draw, 14, 14, W - 14, H - 14, r=10, fill=(15, 18, 26, 200), outline=_BORDER, w=1)
    _rr2(draw, 22, 24, 28, H - 24, r=3, fill=color_neon)
    draw.text((44, 28), titulo, font=_bc_eb(26), fill=_TEXT_G)
    if draw.textlength(mensaje, font=_bc_r(18)) > (W - 80):
        palabras = mensaje.split(" ")
        linea1, linea2 = "", ""
        for p in palabras:
            if draw.textlength(linea1 + " " + p, font=_bc_r(18)) < (W - 90):
                linea1 += " " + p
            else:
                linea2 += " " + p
        draw.text((44, 68), linea1.strip(), font=_bc_r(18), fill=_MUTED_G)
        if linea2:
            draw.text((44, 94), linea2.strip(), font=_bc_r(18), fill=_MUTED_G)
    else:
        draw.text((44, 72), mensaje, font=_bc_r(19), fill=_MUTED_G)
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf

def gen_canvas_tabla(titulo, subtitulo, cabeceras, filas, cw):
    PAD = 44; ROW_H = 54; HEAD_H = 110; W = PAD * 2 + sum(cw); H = HEAD_H + len(filas) * ROW_H + PAD
    img = _chart_base(W, H); draw = ImageDraw.Draw(img)
    _cheader(draw, W, PAD, titulo, subtitulo)
    cx = PAD
    for c, width in zip(cabeceras, cw):
        draw.text((cx + width // 2, HEAD_H - 18), str(c).upper(), font=_bc_m(15), fill=(*_MUTED_G, 220), anchor="mm")
        cx += width
    for ri, f in enumerate(filas):
        ry = HEAD_H + ri * ROW_H
        _rr2(draw, PAD, ry + 3, W - PAD, ry + ROW_H - 3, r=6, fill=(*(_PANEL if ri % 2 == 0 else _BG), 160))
        cx = PAD
        for ci, cell in enumerate(f):
            txt = str(cell)
            draw.text((cx + cw[ci] // 2, ry + ROW_H // 2), txt, font=_bc_b(18) if ci <= 1 else _bc_m(18), fill=(*_TEXT_G, 240), anchor="mm")
            cx += cw[ci]
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf

def gen_canvas_temporada(titulo, mvp_txt, boxes, ranking_filas, cw):
    W, H, PAD = 1180, 720, 44; img = _chart_base(W, H); draw = ImageDraw.Draw(img)
    _cheader(draw, W, PAD, titulo, "Estadísticas Globales del Servidor")
    _rr2(draw, PAD, 90, W - PAD, 160, r=8, fill=(*_PANEL, 225), outline=_TEAL, w=1)
    draw.text((PAD + 24, 104), "👑 MVP TEMPORAL", font=_bc_eb(16), fill=_GOLD)
    draw.text((PAD + 24, 124), mvp_txt, font=_bc_b(22), fill=_TEXT_G)
    bw = (W - PAD * 2 - 32) // 3
    for bi, (b_title, b_val) in enumerate(boxes):
        bx = PAD + bi * (bw + 16)
        _rr2(draw, bx, 176, bx + bw, 246, r=6, fill=(*_PANEL, 140), outline=_BORDER, w=1)
        draw.text((bx + 16, 188), b_title.upper(), font=_bc_m(13), fill=_MUTED_G)
        draw.text((bx + 16, 208), b_val, font=_bc_b(20), fill=_TEAL)
    ry = 270; draw.text((PAD, ry), "RANKING GENERAL", font=_bc_eb(22), fill=_TEXT_G)
    ry += 35; cx = PAD
    cabeceras = ["POS", "JUGADOR", "ACS MEDIO", "WINRATE", "PARTIDAS"]
    for c, width in zip(cabeceras, cw):
        draw.text((cx + width // 2, ry), c, font=_bc_m(14), fill=_MUTED_G, anchor="mm")
        cx += width
    for ri, f in enumerate(ranking_filas[:7]):
        ry += 48; _rr2(draw, PAD, ry - 16, W - PAD, ry + 24, r=4, fill=(*(_PANEL if ri % 2 == 0 else _BG), 120))
        cx = PAD
        for ci, cell in enumerate(f):
            txt = str(cell)
            draw.text((cx + cw[ci] // 2, ry + 4), txt, font=_bc_b(17) if ci <= 1 else _bc_m(17), fill=(*_TEXT_G, 240), anchor="mm")
            cx += cw[ci]
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf

# ==============================================================================
# NUEVO RENDERIZADOR COMPACTO DINÁMICO v1.0.4: BANNERS SEGÚN MAPA Y MODO DE JUEGO
# ==============================================================================
def gen_gif_notificacion(titulo, mensaje, color_neon=_TEAL):
    W, H = 680, 210
    frames = []
    
    jugador_name = titulo.replace("🎮 NUEVA PARTIDA DE ", "").replace("🎮 PARTiDA DE ", "")
    resultado_txt = "PARTIDA"
    mapa_txt = "Desconocido"
    modo_txt = "Competitive"
    agente_txt = "Agente"
    k, d, a, acs = "0", "0", "0", "0"
    
    try:
        if " en " in mensaje:
            partes_kda = mensaje.split(". KDA: ")
            detalles = partes_kda[0]
            
            if "VICTORIA" in detalles:
                resultado_txt = "VICTORIA"
                detalles = detalles.replace("VICTORIA en ", "")
            elif "DERROTA" in detalles:
                resultado_txt = "DERROTA"
                detalles = detalles.replace("DERROTA en ", "")
                
            partes_mapa = detalles.split(" con ")
            mapa_sucio = partes_mapa[0]
            if len(partes_mapa) > 1:
                agente_txt = partes_mapa[1]
                
            if " (" in mapa_sucio:
                ms = mapa_sucio.split(" (")
                mapa_txt = ms[0].strip()
                modo_txt = ms[1].replace(")", "").strip()
            else:
                mapa_txt = mapa_sucio.strip()
                
            if len(partes_kda) > 1:
                stats_split = partes_kda[1].split(" | ACS: ")
                kda_nums = stats_split[0].split("/")
                k, d, a = kda_nums[0], kda_nums[1], kda_nums[2]
                if len(stats_split) > 1:
                    acs = stats_split[1]
    except Exception as e:
        print(f"[PARSE ERROR HUD]: {e}")

    # Descarga e inyección dinámica del splash-art del mapa de Valorant de fondo
    mapa_img_base = None
    map_url = MAP_SPLASHES.get(mapa_txt)
    if map_url:
        try:
            mapa_img_base = Image.open(io.BytesIO(requests.get(map_url, timeout=5).content)).convert("RGBA")
            mapa_img_base = mapa_img_base.resize((W, H), Image.Resampling.LANCZOS)
            mapa_img_base = ImageEnhance.Brightness(mapa_img_base).enhance(0.24)
        except:
            mapa_img_base = None

    color_resultado = _GREEN_G if resultado_txt == "VICTORIA" else _RED_G if resultado_txt == "DERROTA" else _TEAL

    # Variación cromática de la cinta del HUD según el modo detectado
    color_modo_cinta = _TEAL
    if "compet" in modo_txt.lower(): color_modo_cinta = _PURPLE
    elif "swift" in modo_txt.lower(): color_modo_cinta = _BLUE_G
    elif "unrat" in modo_txt.lower(): color_modo_cinta = _GOLD
    elif "skirm" in modo_txt.lower(): color_modo_cinta = _RED_G

    for f in range(16):
        frame_img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(frame_img)
        
        if mapa_img_base is not None:
            frame_img.paste(mapa_img_base, (0,0))
        else:
            for y in range(H):
                c_base = _gl(_BG, (20, 26, 38), y / (H - 1))
                draw.line([(0, y), (W, y)], fill=(*c_base, 255))

        # Animación de respiración neón en bucle infinito sobre el contorno externo
        desplazamiento_anim = _math.sin((f * 4) * (_math.pi / 45)) * 4
        overlay_neon = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay_neon)
        _rr2(od, 16, 16, W - 16, H - 16, r=12, fill=None, outline=(*color_resultado, int(160 + desplazamiento_anim * 10)), w=2)
        frame_img = Image.alpha_composite(frame_img, overlay_neon)
        draw = ImageDraw.Draw(frame_img)
            
        _rr2(draw, 18, 18, W - 18, H - 18, r=10, fill=(12, 15, 22, 210), outline=_BORDER, w=1)
        offset_x = max(0, int(32 - (f * 4))) if f < 8 else 0
        
        # Panel izquierdo: Medalla redonda animada
        centro_x, centro_y, radio_b = 85, H // 2, 48
        pulsacion_alfa = int(120 + _math.sin(f * (_math.pi / 8)) * 70)
        draw.ellipse([centro_x - radio_b, centro_y - radio_b, centro_x + radio_b, centro_y + radio_b], fill=(*color_resultado, 25), outline=(*color_resultado, pulsacion_alfa), width=2)
        inicial = agente_txt[0].upper() if agente_txt else "V"
        draw.text((centro_x, centro_y - 2), inicial, font=_bc_eb(42), fill=_TEXT_G, anchor="mm")
        
        # Panel central: Identidad, Resultado y Modo
        pos_central_x = 160 + offset_x
        draw.text((pos_central_x, 34), jugador_name.upper(), font=_bc_m(20), fill=_MUTED_G)
        draw.text((pos_central_x, 58), resultado_txt, font=_bc_eb(46), fill=color_resultado)
        
        # Inyección de cinta adaptativa del modo de juego
        draw.polygon([(pos_central_x, 126), (pos_central_x + 10, 116), (pos_central_x + 280, 116), (pos_central_x + 270, 126)], fill=(*color_modo_cinta, 180))
        draw.text((pos_central_x + 15, 120), f"{modo_txt.upper()}: {mapa_txt.upper()}", font=_bc_b(13), fill=_BG, anchor="lm")
        draw.text((pos_central_x + 15, 146), f"AGENTE ACTIVO: {agente_txt.upper()}", font=_bc_r(15), fill=_TEXT_G)

        # Panel derecho: Marcador numérico cerrado
        box_x1, box_y1, box_x2, box_y2 = W - 220, 28, W - 28, H - 28
        _rr2(draw, box_x1, box_y1, box_x2, box_y2, r=6, fill=(8, 10, 14, 215), outline=_BORDER, w=1)
        
        draw.text((box_x1 + 45, 46), "K/D/A", font=_bc_m(14), fill=_MUTED_G, anchor="mm")
        draw.text((box_x1 + 145, 46), "ACS", font=_bc_m(14), fill=_MUTED_G, anchor="mm")
        draw.line([(box_x1 + 95, box_y1 + 10), (box_x1 + 95, box_y2 - 10)], fill=(255,255,255,15), width=1)
        
        kda_nums_txt = f"{k}/{d}/{a}"
        fuente_kda = _bc_eb(28) if len(kda_nums_txt) <= 7 else _bc_eb(24)
        draw.text((box_x1 + 45, 96), kda_nums_txt, font=fuente_kda, fill=_TEXT_G, anchor="mm")
        draw.text((box_x1 + 145, 96), str(acs), font=_bc_eb(34), fill=_GOLD, anchor="mm")
        
        try: ratio = round((int(k) + int(a)) / max(int(d), 1), 2)
        except: ratio = 0.0
        draw.text((box_x1 + 95, 142), f"RATIO KDA: {ratio}", font=_bc_r(13), fill=_GREEN_G if ratio >= 1.2 else _MUTED_G, anchor="mm")
        
        frames.append(frame_img.convert("P", palette=Image.Palette.ADAPTIVE))

    buf = io.BytesIO()
    frames[0].save(
        buf,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=65,
        loop=0,
        optimize=True
    )
    buf.seek(0)
    return buf

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

async def _check_racha(nombre, tag, canal):
    ultimas = await bot.db.fetch(
        """
        SELECT won FROM partidas
        WHERE jugador_nombre ILIKE $1 AND jugador_tag ILIKE $2
        ORDER BY fecha DESC LIMIT 5
        """,
        nombre, tag,
    )
    if len(ultimas) < 3: return
    resultados = [r["won"] for r in ultimas]
    if all(resultados[:3]):
        buf = gen_banner_notificacion("🔥 JUGADOR EN RACHA", f"¡{nombre}#{tag} lleva 3 victorias seguidas! Tiembla VCT.", _GREEN_G)
        await canal.send(file=discord.File(fp=buf, filename="racha.png"))
    elif not any(resultados[:3]):
        buf = gen_banner_notificacion("💀 RACHA DE DERROTAS", f"{nombre}#{tag} lleva 3 derrotas seguidas. Alguien que le esconda el ratón.", _RED_G)
        await canal.send(file=discord.File(fp=buf, filename="derrotas.png"))

async def _check_rango(nombre, tag, nuevo_rango, canal):
    row = await bot.db.fetchrow(
        "SELECT ultimo_rango FROM jugadores WHERE nombre ILIKE $1 AND tag ILIKE $2",
        nombre, tag,
    )
    if row is None: return
    viejo = row["ultimo_rango"]
    if viejo and viejo != nuevo_rango and nuevo_rango:
        ranks_order = [
            "Iron 1","Iron 2","Iron 3", "Bronze 1","Bronze 2","Bronze 3",
            "Silver 1","Silver 2","Silver 3", "Gold 1","Gold 2","Gold 3",
            "Platinum 1","Platinum 2","Platinum 3", "Diamond 1","Diamond 2","Diamond 3",
            "Ascendant 1","Ascendant 2","Ascendant 3", "Immortal 1","Immortal 2","Immortal 3",
            "Radiant",
        ]
        vi = ranks_order.index(viejo) if viejo in ranks_order else -1
        ni = ranks_order.index(nuevo_rango) if nuevo_rango in ranks_order else -1
        if vi >= 0 and ni >= 0:
            if ni > vi:
                buf = gen_banner_notificacion("📈 ¡UPGRADE DE RANGO!", f"{nombre}#{tag} ha ascendido: {viejo} ➔ {nuevo_rango} 🎉", _GREEN_G)
                await canal.send(file=discord.File(fp=buf, filename="rank_up.png"))
            else:
                buf = gen_banner_notificacion("📉 ¡DOWNGRADE DE RANGO!", f"{nombre}#{tag} ha caido de rango: {viejo} ➔ {nuevo_rango} 😬", _RED_G)
                await canal.send(file=discord.File(fp=buf, filename="rank_down.png"))
    await bot.db.execute(
        "UPDATE jugadores SET ultimo_rango = $1 WHERE nombre ILIKE $2 AND tag ILIKE $3",
        nuevo_rango, nombre, tag,
    )

# ==============================================================================
# HUB DE INTERACTIVIDAD MÓVIL (discord.ui.View COMPONENTES)
# ==============================================================================
class StatsInteractiveHub(discord.ui.View):
    def __init__(self, rows_db, j_nombre, j_tag):
        super().__init__(timeout=180) # Botones activos en memoria durante 3 minutos
        self.rows = rows_db
        self.nombre = j_nombre
        self.tag = j_tag

    @discord.ui.button(label="📊 Evolución", style=discord.ButtonStyle.success)
    async def b_evolucion(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        buf = await asyncio.to_thread(gen_evolucion, self.rows, f"{self.nombre}#{self.tag}")
        archivo = discord.File(fp=buf, filename="evolucion.png")
        await interaction.followup.send(file=archivo, ephemeral=True)

    @discord.ui.button(label="🗺️ Mapas", style=discord.ButtonStyle.primary)
    async def b_mapas(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        buf = await asyncio.to_thread(gen_heatmap_mapas, self.rows)
        if buf:
            await interaction.followup.send(file=discord.File(fp=buf, filename="mapas.png"), ephemeral=True)
        else:
            await interaction.followup.send("❌ No hay registros de mapas suficientes para compilar.", ephemeral=True)

    @discord.ui.button(label="🤖 Análisis IA", style=discord.ButtonStyle.secondary)
    async def b_coach(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        if not GEMINI_API_KEY:
            await interaction.followup.send("❌ IA Desconectada temporalmente por el servidor.", ephemeral=True)
            return
            
        last = self.rows[0]
        prompt = f"Actúa como un entrenador de eSports de Valorant muy sarcástico. Analiza la última partida de {self.nombre}: Agente: {last['agente']}, Resultado: {'Victoria' if last['won'] else 'Derrota'}, KDA: {last['kills']}/{last['deaths']}/{last['assists']}, ACS: {last['acs']}. Haz un roasteo lapidario de 1 línea."
        try:
            client = genai.Client(api_key=GEMINI_API_KEY.strip())
            response = await asyncio.to_thread(client.models.generate_content, model='gemini-2.5-flash', contents=prompt)
            buf = gen_banner_notificacion(f"🤖 ROAST IA PARA {self.nombre.upper()}", response.text.strip(), _PURPLE)
            await interaction.followup.send(file=discord.File(fp=buf, filename="coach.png"), ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Error con el enlace neuronal IA: {e}", ephemeral=True)

# ==============================================================================
# SINCRO Y CONFIGURACIONES CENTRALES DE DISCORD
# ==============================================================================
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
            bot.tree.copy_global_to(guild=guild_obj)
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

# ==============================================================================
# RESUMEN SEMANAL DE CONTROL AUTOMÁTICO
# ==============================================================================
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
        if not rows: continue

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

# ==============================================================================
# SLASH COMMAND INTERACTIVE IMPLEMENTATIONS
# ==============================================================================
@bot.tree.command(name="add", description="Guarda a un colega en la base de datos del servidor")
async def add(interaction: discord.Interaction, nombre: str, tag: str):
    await interaction.response.defer(); server_id = str(interaction.guild_id)
    try:
        await bot.db.execute("INSERT INTO jugadores (server_id, nombre, tag) VALUES ($1, $2, $3)", server_id, nombre, tag)
        buf = gen_banner_notificacion("✅ JUGADOR REGISTRADO", f"Añadido correctamente al radar de alertas: {nombre}#{tag}", _GREEN_G)
        await interaction.followup.send(file=discord.File(fp=buf, filename="add_ok.png"))
    except asyncpg.exceptions.UniqueViolationError:
        buf = gen_banner_notificacion("⚠️ JUGADOR EXISTENTE", f"El agente {nombre}#{tag} ya está en la lista de seguimiento.", _GOLD)
        await interaction.followup.send(file=discord.File(fp=buf, filename="add_warn.png"))

@bot.tree.command(name="remove", description="Deja de vigilar a un jugador del servidor")
async def remove(interaction: discord.Interaction, nombre: str, tag: str):
    await interaction.response.defer()
    server_id = str(interaction.guild_id)
    deleted = await bot.db.execute("DELETE FROM jugadores WHERE server_id = $1 AND nombre ILIKE $2 AND tag ILIKE $3", server_id, nombre, tag)
    if deleted == "DELETE 1":
        buf = gen_banner_notificacion("🗑️ AGENTE ELIMINADO", f"Se han desactivado las alertas de tracking para: {nombre}#{tag}", _RED_G)
        await interaction.followup.send(file=discord.File(fp=buf, filename="remove_ok.png"))
    else:
        buf = gen_banner_notificacion("⚠️ ERROR DE EXTRACTOR", f"No se encontró ninguna cuenta registrada bajo {nombre}#{tag}", _GOLD)
        await interaction.followup.send(file=discord.File(fp=buf, filename="remove_fail.png"))

@bot.tree.command(name="sync", description="Sincroniza los slash commands en este servidor")
async def sync_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True); synced = await bot.tree.sync(guild=discord.Object(id=interaction.guild_id))
    buf = gen_banner_notificacion("⚙️ ÁRBOL SINCRONIZADO", f"Sincronizados con éxito {len(synced)} comandos de barra localmente.", _BLUE_G)
    await interaction.followup.send(file=discord.File(fp=buf, filename="sync.png"), ephemeral=True)

@bot.tree.command(name="stats", description="Muestra las estadísticas de un jugador de Valorant")
@app_commands.choices(modo=MODOS_DISCORD)
async def stats(interaction: discord.Interaction, nombre: str, tag: str, region: str = "eu", modo: app_commands.Choice[str] = None):
    await interaction.response.defer(thinking=True); modo_busqueda = modo.value if modo else "Competitive"; modo_display = modo.name if modo else "Competitivo"
    if modo_busqueda == "%": modo_display = "Todos los modos"
    s, err = await fetch_stats(nombre, tag, region)
    if err or not s:
        buf = gen_banner_notificacion("❌ ERROR DE COMBATE", f"Fallo al buscar a {nombre}#{tag}: {err}", _RED_G); await interaction.followup.send(file=discord.File(fp=buf, filename="error_search.png")); return
    rows = await bot.db.fetch("SELECT p.match_id, p.kills, p.deaths, p.assists, p.acs, p.won, p.mapa, p.modo, p.agente, p.adr, p.kast, p.dda, p.rounds_played, p.damage_dealt_total, p.damage_received_total, p.kast_rounds, p.hs, p.fecha FROM partidas p JOIN jugadores j ON p.jugador_nombre = j.nombre AND p.jugador_tag = j.tag WHERE j.server_id = $1 AND p.jugador_nombre ILIKE $2 AND p.jugador_tag ILIKE $3 AND ($4 = '%' OR LOWER(p.modo) = LOWER($4)) ORDER BY p.fecha DESC LIMIT 120", str(interaction.guild_id), nombre, tag, modo_busqueda)
    if not rows:
        buf = gen_banner_notificacion("❌ HISTORIAL SIN REGISTROS", f"No hay partidas guardadas para {nombre}#{tag} en {modo_display}", _GOLD); await interaction.followup.send(file=discord.File(fp=buf, filename="error_empty.png")); return
    tk, td, ta = sum((r["kills"] or 0) for r in rows), sum((r["deaths"] or 0) for r in rows), sum((r["assists"] or 0) for r in rows)
    db_stats = {"tk": tk, "td": td, "ta": ta, "kda": round((tk + ta) / max(td, 1), 2), "acs_medio": round(sum(float(r["acs"] or 0) for r in rows) / len(rows), 1), "adr_medio": round(sum(float(r["adr"] or 0) for r in rows) / len(rows), 1), "dda_medio": round(sum(float(r["dda"] or 0) for r in rows) / len(rows), 1), "hs_medio": round(sum(float(r["hs"] or 0) for r in rows) / len(rows), 1), "winrate": round(sum(1 for r in rows if r["won"]) * 100.0 / len(rows), 1), "total_matches": len(rows)}
    k_v = [float(r["kast"]) for r in rows if r["kast"] is not None]; db_stats["kast_medio"] = round(sum(k_v) / len(k_v), 1) if k_v else None
    agent_counts = {}; _ = [agent_counts.update({r["agente"]: agent_counts.get(r["agente"], 0) + 1}) for r in rows]
    top_agents_db = [a for a, _ in sorted(agent_counts.items(), key=lambda x: x[1], reverse=True)]; db_stats["main_agent"] = top_agents_db[0] if top_agents_db else "Desconocido"
    latest = rows[0]; s.update({"mapa": latest["mapa"] or s.get("mapa"), "modo": latest["modo"] or s.get("modo"), "kda": db_stats["kda"], "adr": db_stats["adr_medio"], "acs": db_stats["acs_medio"], "hs": db_stats["hs_medio"], "winrate": db_stats["winrate"], "dda": db_stats["dda_medio"], "kast": db_stats.get("kast_medio"), "last_match": {"id": latest["match_id"], "kills": latest["kills"] or 0, "deaths": latest["deaths"] or 0, "assists": latest["assists"] or 0, "acs": float(latest["acs"] or 0), "adr": float(latest["adr"] or 0), "dda": float(latest["dda"] or 0), "kast": float(latest["kast"]) if latest["kast"] is not None else None, "hs": float(latest["hs"] or 0), "won": bool(latest["won"]), "agente": latest["agente"] or "Desconocido", "rounds_played": latest["rounds_played"], "damage_dealt_total": latest["damage_dealt_total"], "damage_received_total": latest["damage_received_total"], "kast_rounds": latest["kast_rounds"]}})
    try:
        buf = await asyncio.wait_for(asyncio.to_thread(generar_tarjeta, s, modo_display, True, db_stats, top_agents_db, rows), timeout=20)
        # MODIFICACIÓN INTERACTIVA: IMAGEN LIMPIA SIN EMBED + BOTONERA DE COMANDOS COMPACTA
        view_interactiva = StatsInteractiveHub(rows, s.get('nombre', nombre), s.get('tag', tag))
        await interaction.followup.send(file=discord.File(fp=buf, filename="stats.png"), view=view_interactiva)
    except Exception as e:
        logging.exception("Error generando tarjeta /stats"); buf = gen_banner_notificacion("❌ CRASH INTERNO", f"Error pintando tarjeta de stats: {e}", _RED_G); await interaction.followup.send(file=discord.File(fp=buf, filename="err_canvas.png"))

@bot.tree.command(name="graficas", description="Muestra gráficas de evolución, precisión y mapas de un jugador")
@app_commands.choices(modo=MODOS_DISCORD)
async def graficas(interaction: discord.Interaction, nombre: str, tag: str, modo: app_commands.Choice[str] = None):
    await interaction.response.defer(); server_id, modo_busqueda = str(interaction.guild_id), "Competitive"
    rows = await bot.db.fetch("SELECT p.fecha, p.acs, p.dda, p.won, p.mapa, p.agente, p.hs FROM partidas p JOIN jugadores j ON p.jugador_nombre = j.nombre AND p.jugador_tag = j.tag WHERE j.server_id = $1 AND p.jugador_nombre ILIKE $2 AND p.jugador_tag ILIKE $3 AND ($4 = '%' OR LOWER(p.modo) = LOWER($4)) ORDER BY p.fecha ASC LIMIT 40", server_id, nombre, tag, modo_busqueda)
    if not rows:
        buf = gen_banner_notificacion("❌ SIN REGISTROS", f"No hay partidas guardadas para {nombre}#{tag} en ese modo.", _GOLD); await interaction.followup.send(file=discord.File(fp=buf, filename="err_graficas.png")); return
    archivos = []
    archivos.append(discord.File(fp=await asyncio.to_thread(gen_evolucion, rows, f"{nombre}#{tag}"), filename="evolucion.png"))
    buf_hm = await asyncio.to_thread(gen_heatmap_mapas, rows)
    if buf_hm: archivos.append(discord.File(fp=buf_hm, filename="mapas.png"))
    agent_rows = await bot.db.fetch("SELECT p.agente, COUNT(*) as count FROM partidas p JOIN jugadores j ON p.jugador_nombre = j.nombre AND p.jugador_tag = j.tag WHERE j.server_id = $1 AND p.jugador_nombre ILIKE $2 AND p.jugador_tag ILIKE $3 AND ($4 = '%' OR LOWER(p.modo) = LOWER($4)) GROUP BY p.agente ORDER BY count DESC", server_id, nombre, tag, modo_busqueda)
    buf_pie = await asyncio.to_thread(gen_pie_agentes, agent_rows, f"Agentes — {nombre}#{tag}")
    if buf_pie: archivos.append(discord.File(fp=buf_pie, filename="agentes.png"))
    if modo_busqueda == "Competitive":
        buf_prec = await asyncio.to_thread(gen_precision, rows, f"{nombre}#{tag}")
        if buf_prec: archivos.append(discord.File(fp=buf_prec, filename="precision.png"))
    await interaction.followup.send(files=archivos)

@bot.tree.command(name="comparar", description="Compara las stats competitivas de dos jugadores del servidor")
async def comparar(interaction: discord.Interaction, nombre1: str, tag1: str, nombre2: str, tag2: str):
    await interaction.response.defer(); server_id, modo_busqueda = str(interaction.guild_id), "Competitive"
    async def _get_stats(nom, tg): return await bot.db.fetchrow("SELECT AVG(p.acs) as acs_medio, SUM(p.kills) as tk, SUM(p.deaths) as td, SUM(p.assists) as ta, AVG(CASE WHEN p.rounds_played > 0 AND p.damage_dealt_total IS NOT NULL THEN p.damage_dealt_total::numeric / p.rounds_played ELSE p.adr END) as adr_medio, AVG(CASE WHEN p.rounds_played > 0 AND p.kast_rounds IS NOT NULL THEN (p.kast_rounds::numeric * 100.0) / p.rounds_played ELSE p.kast END) as kast_medio, AVG(CASE WHEN p.rounds_played > 0 AND p.damage_dealt_total IS NOT NULL AND p.damage_received_total IS NOT NULL THEN (p.damage_dealt_total::numeric - p.damage_received_total::numeric) / p.rounds_played ELSE p.dda END) as dda_medio, AVG(p.hs) as hs_medio, COUNT(CASE WHEN p.won THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0) as winrate, COUNT(*) as total_matches FROM partidas p JOIN jugadores j ON p.jugador_nombre = j.nombre AND p.jugador_tag = j.tag WHERE j.server_id = $1 AND p.jugador_nombre ILIKE $2 AND p.jugador_tag ILIKE $3 AND ($4 = '%' OR LOWER(p.modo) = LOWER($4))", server_id, nom, tg, modo_busqueda)
    s1, s2 = await asyncio.gather(_get_stats(nombre1, tag1), _get_stats(nombre2, tag2))
    if not s1 or not s1["total_matches"]:
        buf = gen_banner_notificacion("❌ REGISTROS INSUFICIENTES", f"No hay datos guardados para {nombre1}#{tag1}", _GOLD); await interaction.followup.send(file=discord.File(fp=buf, filename="err_comp1.png")); return
    if not s2 or not s2["total_matches"]:
        buf = gen_banner_notificacion("❌ REGISTROS INSUFICIENTES", f"No hay datos guardados para {nombre2}#{tag2}", _GOLD); await interaction.followup.send(file=discord.File(fp=buf, filename="err_comp2.png")); return
    buf = await asyncio.to_thread(gen_barra_comparativa, dict(s1), f"{nombre1}#{tag1}", dict(s2), f"{nombre2}#{tag2}")
    await interaction.followup.send(file=discord.File(fp=buf, filename="comparar.png"))

@bot.tree.command(name="leaderboard", description="Ranking de los colegas del servidor")
@app_commands.choices(modo=MODOS_DISCORD)
async def leaderboard(interaction: discord.Interaction, modo: app_commands.Choice[str] = None):
    server_id = str(interaction.guild_id); modo_busqueda = modo.value if modo else "Competitive"; modo_display = modo.name if modo else "Competitivo"
    if modo_busqueda == "%": modo_display = "Todos los modos"
    amigos = await bot.db.fetch("SELECT nombre, tag FROM jugadores WHERE server_id = $1", server_id)
    if not amigos: amigos = await bot.db.fetch("SELECT nombre, tag FROM jugadores WHERE server_id = $1", server_id); return
    await interaction.response.defer()
    scores = await bot.db.fetch("SELECT p.jugador_nombre as nombre, p.jugador_tag as tag, AVG(p.acs) as acs_medio, SUM(p.kills) as tk, SUM(p.deaths) as td, SUM(p.assists) as ta, COUNT(*) as total_matches, COUNT(CASE WHEN p.won THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0) as winrate, (SELECT agente FROM partidas p2 WHERE p2.jugador_nombre = p.jugador_nombre AND p2.jugador_tag = p.jugador_tag AND ($2 = '%' OR LOWER(p2.modo) = LOWER($2)) GROUP BY agente ORDER BY COUNT(*) DESC LIMIT 1) as main_agent FROM partidas p JOIN jugadores j ON p.jugador_nombre = j.nombre AND p.jugador_tag = j.tag WHERE j.server_id = $1 AND ($2 = '%' OR LOWER(p.modo) = LOWER($2)) GROUP BY p.jugador_nombre, p.jugador_tag ORDER BY acs_medio DESC", server_id, modo_busqueda)
    if not scores:
        buf = gen_banner_notificacion("❌ SIN COMBATES REGISTRADOS", f"Todavía no hay partidas de {modo_display} en este servidor.", _GOLD); await interaction.followup.send(file=discord.File(fp=buf, filename="err_leader.png")); return
    
    filas_tabla = []
    for i, p in enumerate(scores):
        kda_val = round((p["tk"] + p["ta"]) / max(p["td"], 1), 2)
        medalla = "🥇 " if i == 0 else "🥈 " if i == 1 else "🥉 " if i == 2 else ""
        filas_tabla.append([f"{medalla}{i+1}º", f"{p['nombre']}#{p['tag']}", f"{p['main_agent'] or '?'}", f"{round(p['acs_medio'],0):.0f}", f"{kda_val:.2f}", f"{round(p['winrate'],1):.1f}%", f"{p['total_matches']}"])
    
    headers_t = ["RANK", "JUGADOR", "MAIN AGENT", "ACS", "KDA", "WINRATE", "PARTIDAS"]
    cw_t = [70, 240, 140, 90, 90, 110, 100]
    buf = await asyncio.to_thread(gen_canvas_tabla, f"🏆 LEADERBOARD ({modo_display.upper()})", f"Clasificación de {len(scores)} agentes activos", headers_t, filas_tabla, cw_t)
    await interaction.followup.send(file=discord.File(fp=buf, filename="leaderboard.png"))

@bot.tree.command(name="temporada", description="Resumen competitivo de la temporada del servidor")
async def temporada(interaction: discord.Interaction, modo: app_commands.Choice[str] = None):
    await interaction.response.defer(); server_id = str(interaction.guild_id); modo_busqueda = "Competitive"; modo_display = modo.name if modo else "Competitivo"
    rows = await bot.db.fetch("SELECT p.jugador_nombre as nombre, p.jugador_tag as tag, AVG(p.acs) as acs_medio, COUNT(*) as partidas, COUNT(CASE WHEN p.won THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0) as winrate, AVG(CASE WHEN p.rounds_played > 0 AND p.damage_dealt_total IS NOT NULL AND p.damage_received_total IS NOT NULL THEN (p.damage_dealt_total::numeric - p.damage_received_total::numeric) / p.rounds_played ELSE p.dda END) as dda_medio FROM partidas p JOIN jugadores j ON p.jugador_nombre = j.nombre AND p.jugador_tag = j.tag WHERE j.server_id = $1 AND ($2 = '%' OR LOWER(p.modo) = LOWER($2)) GROUP BY p.jugador_nombre, p.jugador_tag ORDER BY acs_medio DESC", server_id, modo_busqueda)
    if not rows:
        buf = gen_banner_notificacion("❌ COLA VACÍA", f"Todavía no hay datos de {modo_display} en este servidor.", _GOLD); await interaction.followup.send(file=discord.File(fp=buf, filename="err_temp.png")); return
    
    agent_rows_all = await bot.db.fetch("SELECT p.agente, COUNT(*) as count FROM partidas p JOIN jugadores j ON p.jugador_nombre = j.nombre AND p.jugador_tag = j.tag WHERE j.server_id = $1 AND ($2 = '%' OR LOWER(p.modo) = LOWER($2)) AND p.agente != 'Desconocido' GROUP BY p.agente ORDER BY count DESC LIMIT 8", server_id, modo_busqueda)
    buf_pie = await asyncio.to_thread(gen_pie_agentes, agent_rows_all, f"Agentes más jugados — {modo_display}")
    
    mvp = rows[0]; mvp_txt = f"{mvp['nombre']}#{mvp['tag']}  (ACS Medio: {round(mvp['acs_medio'],1)} | WR: {round(mvp['winrate'],1)}%)"
    most_games = max(rows, key=lambda r: r["partidas"]); best_wr = max((r for r in rows if r["partidas"] >= 3), key=lambda r: float(r["winrate"] or 0), default=rows[0]); best_dda = max((r for r in rows if r["dda_medio"] is not None), key=lambda r: float(r["dda_medio"]), default=rows[0])
    boxes = [("MÁS PARTIDAS", f"{most_games['nombre']} ({most_games['partidas']})"), ("MEJOR WINRATE", f"{best_wr['nombre']} ({round(float(best_wr['winrate']),1)}%)"), ("MEJOR DDA", f"{best_dda['nombre']} ({round(float(best_dda['dda_medio']),1)})")]
    
    ranking_filas = []
    for i, r in enumerate(rows):
        med = "🥇 " if i == 0 else "🥈 " if i == 1 else "🥉 " if i == 2 else ""
        ranking_filas.append([f"{med}{i+1}º", f"{r['nombre']}#{r['tag']}", f"{round(r['acs_medio'],1)}", f"{round(float(r['winrate'] or 0),1)}%", f"{r['partidas']}"])
    
    buf_temp = await asyncio.to_thread(gen_canvas_temporada, f"🏆 RESUMEN COMPACTO: TEMPORADA ({modo_display.upper()})", mvp_txt, boxes, ranking_filas, [60, 320, 150, 150, 120])
    archivos = [discord.File(fp=buf_temp, filename="temporada.png")]
    if buf_pie: archivos.append(discord.File(fp=buf_pie, filename="agentes_temporada.png"))
    await interaction.followup.send(files=archivos)

async def agente_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    coincidencias = [app_commands.Choice(name=agente, value=agente) for agente in AGENTES_VALORANT if current.lower() in agente.lower()]
    return coincidencias[:25]

@bot.tree.command(name="lineups", description="Muestra lineups de un agente")
@app_commands.describe(agente="Nombre del agente")
@app_commands.autocomplete(agente=agente_autocomplete)
async def lineups(interaction: discord.Interaction, agente: str):
    await interaction.response.defer()
    url = f"{LINEUPS_BASE}{urllib.parse.quote(agente)}"
    buf = gen_banner_notificacion(f"📚 LINEUPS DE {agente.upper()}", f"Click para abrir el libro de tácticas de {agente}: {url}", _TEAL)
    await interaction.followup.send(file=discord.File(fp=buf, filename="lineups.png"))

@bot.tree.command(name="coach", description="La IA de Gemini analiza sarcásticamente la última partida")
async def coach(interaction: discord.Interaction, nombre: str, tag: str):
    await interaction.response.defer()
    if not GEMINI_API_KEY:
        buf = gen_banner_notificacion("❌ ERROR DE LLAVE", "La API Key de Gemini está ausente en el entorno.", _RED_G); await interaction.followup.send(file=discord.File(fp=buf, filename="err_key.png")); return
    server_id = str(interaction.guild_id); ultima_partida = await bot.db.fetchrow("SELECT p.kills, p.deaths, p.assists, p.acs, p.won, p.mapa, p.agente, p.hs, p.dda FROM partidas p JOIN jugadores j ON p.jugador_nombre = j.nombre AND p.jugador_tag = j.tag WHERE j.server_id = $1 AND p.jugador_nombre ILIKE $2 AND p.jugador_tag ILIKE $3 ORDER BY p.fecha DESC LIMIT 1", server_id, nombre, tag)
    if not ultima_partida:
        buf = gen_banner_notificacion("❌ AGENTE SIN REGISTRO", f"No constan partidas registradas de {nombre}#{tag} en la base de datos.", _GOLD); await interaction.followup.send(file=discord.File(fp=buf, filename="err_coach.png")); return
    k, d, a = ultima_partida["kills"], ultima_partida["deaths"], ultima_partida["assists"]
    prompt = f"Actúa como un entrenador de eSports de Valorant muy sarcástico, crítico y con humor negro (pero sin insultos graves). Analiza la última partida de este jugador llamado {nombre}. Tus comentarios deben ser breves (máximo 2 líneas de texto corto), directos al grano y usar jerga de Valorant. Estadísticas: Agente: {ultima_partida['agente']}, Resultado: {'Victoria' if ultima_partida['won'] else 'Derrota'}, KDA: {k}/{d}/{a}, ACS: {ultima_partida['acs']}, DDA: {float(ultima_partida['dda'] or 0)}, HS: {float(ultima_partida['hs'] or 0)}%. Haz un comentario lapidario corto."
    def ask_gemini_modern():
        return genai.Client(api_key=GEMINI_API_KEY.strip()).models.generate_content(model='gemini-2.5-flash', contents=prompt).text
    try:
        respuesta_texto = await asyncio.to_thread(ask_gemini_modern)
        buf_coach = gen_banner_notificacion(f"🤖 ANALISIS DE IA: {nombre.upper()}", respuesta_texto.strip(), _PURPLE)
        await interaction.followup.send(file=discord.File(fp=buf_coach, filename="coach_roast.png"))
    except Exception as e:
        buf = gen_banner_notificacion("❌ CORTE DE ENLACE IA", f"El coach se ha liado con los cables: {str(e)[:50]}", _RED_G); await interaction.followup.send(file=discord.File(fp=buf, filename="err_gemini.png"))

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    logging.exception("Slash command error", exc_info=error)
    buf = gen_banner_notificacion("💥 ERROR DE ÁRBOL", f"Fallo de ejecución: {str(error)[:60]}", _RED_G)
    try:
        if interaction.response.is_done(): await interaction.followup.send(file=discord.File(fp=buf, filename="fatal_error.png"), ephemeral=True)
        else: await interaction.response.send_message(file=discord.File(fp=buf, filename="fatal_error.png"), ephemeral=True)
    except Exception: pass

@vigilante_partidas.error
async def vigilante_partidas_error(error): print(f"💥 CRASH EN EL BUCLE DE VIGILANCIA: {error}")
@resumen_semanal.error
async def resumen_semanal_error(error): print(f"💥 CRASH EN EL BUCLE DE RESUMEN SEMANAL: {error}")

# ==============================================================================
# BUCLE AUTOMÁTICO VIGILANTE DE PARTIDAS EN SEGUNDO PLANO
# ==============================================================================
@tasks.loop(minutes=5)
async def vigilante_partidas():
    await bot.wait_until_ready()
    try: canal = await bot.fetch_channel(CANAL_ALERTAS_ID)
    except Exception: return
    jugadores = await bot.db.fetch("SELECT DISTINCT nombre, tag FROM jugadores")
    if not jugadores: return
    
    for j in jugadores:
        try:
            nombre, tag = j["nombre"], j["tag"]
            s, err = await fetch_stats(nombre, tag)
            await asyncio.sleep(4)
            if err or not s or not s.get("last_match"):
                continue
            lm = s["last_match"]; match_id = lm.get("id"); existe = await bot.db.fetchval("SELECT 1 FROM partidas WHERE match_id = $1 AND jugador_nombre ILIKE $2 AND jugador_tag ILIKE $3", match_id, nombre, tag)
            if match_id and not existe:
                k, d, a, acs, won, agente, mapa = lm.get("kills", 0), lm.get("deaths", 1), lm.get("assists", 0), lm.get("acs", 0), lm.get("won", False), lm.get("agente", "Desconocido"), s.get("mapa", "Desconocido")
                modo_raw = (s.get("modo") or "Unrated").strip(); m_f = "Competitive" if modo_raw.lower() == "competitive" else modo_raw
                if await bot.db.fetchval("SELECT COUNT(*) FROM partidas WHERE jugador_nombre ILIKE $1 AND jugador_tag ILIKE $2", nombre, tag) == 0: continue
                t_m = _calc_tracker_metrics_from_stats(s); hs_val = s.get("last_match", {}).get("hs") if s.get("last_match", {}).get("hs") is not None else (t_m.get("hs") if t_m.get("hs") is not None else s.get("hs"))
                await bot.db.execute("INSERT INTO partidas (match_id, jugador_nombre, jugador_tag, kills, deaths, assists, acs, won, mapa, modo, agente, adr, kast, dda, rounds_played, damage_dealt_total, damage_received_total, kast_rounds, hs) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19)", match_id, nombre, tag, k, d, a, acs, won, mapa, m_f, agente, t_m["adr"], t_m["kast"], t_m["dda"], t_m["rounds_played"], t_m["damage_dealt_total"], t_m["damage_received_total"], t_m["kast_rounds"], hs_val)
                await _check_racha(nombre, tag, canal); await _check_rango(nombre, tag, s.get("rank"), canal)
                
                tit = f"🎮 NUEVA PARTIDA DE {nombre.upper()}#{tag.upper()}"
                msg_body = f"{'VICTORIA' if won else 'DERROTA'} en {mapa} ({m_f}) con {agente}. KDA: {k}/{d}/{a} | ACS: {acs}"
                buf_a = gen_gif_notificacion(tit, msg_body, _GREEN_G if won else _RED_G)
                await canal.send(file=discord.File(fp=buf_a, filename="match_alert.gif"))
        except Exception: pass

if __name__ == "__main__":
    bot.run(TOKEN)