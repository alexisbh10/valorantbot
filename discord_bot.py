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
AGENTES_VALORANT = ["Astra", "Breach", "Brimstone", "Chamber", "Clove", "Cypher", "Deadlock", "Fade", "Gekko", "Harbor", "Iso", "Jett", "KAY/O", "Killjoy", "Neon", "Omen", "Phoenix", "Raze", "Reyna", "Sage", "Skye", "Sova", "Tejo", "Viper", "Vyse", "Yoru"]

MAP_SPLASHES = {
    "Ascent": "https://media.valorant-api.com/maps/7eaecc1b-4337-bbf6-6ab9-04b8f06b3319/splash.png",
    "Bind": "https://media.valorant-api.com/maps/2c9d57ec-4431-9c5e-11ef-ba7ae662c694/splash.png",
    "Haven": "https://media.valorant-api.com/maps/2bee0dc9-4ffe-519b-1cbd-7825631b7aa5/splash.png",
    "Split": "https://media.valorant-api.com/maps/d960549e-485c-e861-8d71-aa9d1aed12a2/splash.png",
    "Fracture": "https://media.valorant-api.com/maps/b529448b-4d60-346e-e89e-00a4c527a405/splash.png",
    "Breeze": "https://media.valorant-api.com/maps/2fb9a4fd-47a7-3e68-9c03-d38d1b7caabd/splash.png",
    "Icebox": "https://media.valorant-api.com/maps/e2ad5c54-4114-a870-9641-8ea21279579a/splash.png",
    "Pearl": "https://media.valorant-api.com/maps/fd267378-4d1d-484f-ff52-77821ed10dc2/splash.png",
    "Lotus": "https://media.valorant-api.com/maps/2fe4ed3a-450a-01be-2339-95a5b1ac8d53/splash.png",
    "Sunset": "https://media.valorant-api.com/maps/92584fbe-486a-b1b2-9faa-39b0f486b498/splash.png",
    "Abyss": "https://media.valorant-api.com/maps/224b0a95-48b9-f703-1bd8-67aca101a61f/splash.png",
}

_BG = (10, 11, 17); _PANEL = (15, 17, 25); _BORDER = (42, 48, 67); _TEXT_G = (245, 247, 251)
_MUTED_G = (150, 163, 179); _TEAL = (79, 209, 197); _RED_G = (252, 129, 129); _GOLD = (246, 224, 94)
_GREEN_G = (104, 211, 145); _PURPLE = (167, 139, 250); _BLUE_G = (118, 228, 247)
CHART_COLORS = [_TEAL, _RED_G, _GOLD, _GREEN_G, _PURPLE, _BLUE_G, (251,211,141), (246,135,179), (154,230,180)]

FONTS_DIR = "assets/fonts"
def _cargar_fuente_proyecto(n, s):
    try: return ImageFont.truetype(f"{FONTS_DIR}/{n}", s)
    except OSError: return ImageFont.load_default()

def _bc_eb(s): return _cargar_fuente_proyecto("BarlowCondensed-ExtraBold.ttf", s)
def _bc_b(s):  return _cargar_fuente_proyecto("BarlowCondensed-Bold.ttf", s)
def _bc_m(s):  return _cargar_fuente_proyecto("BarlowCondensed-Medium.ttf", s)
def _bc_r(s):  return _cargar_fuente_proyecto("BarlowCondensed-Regular.ttf", s)

def mix(c1, c2, t): return tuple(int(c1[i]*(1-t) + c2[i]*t) for i in range(3))
def _gl(a, b, t): return tuple(int(a[i]*(1-t)+b[i]*t) for i in range(3))
def _rr2(d,x1,y1,x2,y2,r=6,fill=None,outline=None,w=1): d.rounded_rectangle([x1,y1,x2,y2],radius=r,fill=fill,outline=outline,width=w)
def _safe_float(v, default=0.0):
    try: return float(v)
    except: return default
def _safe_int(v, default=0):
    try: return int(v)
    except: return default
def fmt_num(v, digits=1, suffix=""):
    if v is None: return "—"
    try: return f"{round(float(v), digits)}{suffix}"
    except: return f"{v}{suffix}"

def _rank_palette(rank):
    r = (rank or "").lower()
    palettes = {"radiant": ((255, 228, 80), (255, 200, 30)), "immortal": ((220, 70, 100), (180, 30, 65)), "ascendant": ((55, 210, 130), (20, 155, 80)), "diamond": ((170, 105, 240), (100, 45, 195)), "platinum": ((75, 185, 235), (30, 115, 185)), "gold": ((240, 190, 55), (190, 135, 20)), "silver": ((195, 195, 205), (130, 130, 145)), "bronze": ((200, 125, 55), (140, 80, 20)), "iron": ((115, 115, 120), (70, 70, 75))}
    for key, pal in palettes.items():
        if key in r: return pal
    return ((255, 70, 85), (200, 20, 40))

def gen_banner_notificacion(titulo, mensaje, color_neon=_TEAL):
    W, H = 750, 160; img = Image.new("RGBA", (W, H)); draw = ImageDraw.Draw(img)
    for y in range(H): draw.line([(0, y), (W, y)], fill=(*_gl(_BG, (18, 22, 32), y/(H-1)), 255))
    _rr2(draw, 14, 14, W - 14, H - 14, r=10, fill=(15, 18, 26, 200), outline=_BORDER, w=1)
    _rr2(draw, 22, 24, 28, H - 24, r=3, fill=color_neon)
    draw.text((44, 28), titulo, font=_bc_eb(26), fill=_TEXT_G)
    if draw.textlength(mensaje, font=_bc_r(18)) > (W - 80):
        l1 = l2 = ""
        for p in mensaje.split(" "):
            if draw.textlength(l1 + " " + p, font=_bc_r(18)) < (W - 90): l1 += " " + p
            else: l2 += " " + p
        draw.text((44, 68), l1.strip(), font=_bc_r(18), fill=_MUTED_G)
        if l2: draw.text((44, 94), l2.strip(), font=_bc_r(18), fill=_MUTED_G)
    else: draw.text((44, 72), mensaje, font=_bc_r(19), fill=_MUTED_G)
    buf = io.BytesIO(); img.convert("RGB").save(buf, format="PNG", optimize=True); buf.seek(0); return buf

# ==============================================================================
# NUEVOS MOTORES CANVAS PARA REEMPLAZAR LEADERBOARD Y EMBEDS DE TEMPORADA
# ==============================================================================
def gen_canvas_tabla(titulo, subtitulo, cabeceras, filas, cw, medallas=False):
    PAD = 44; ROW_H = 54; HEAD_H = 110; W = PAD * 2 + sum(cw); H = HEAD_H + len(filas) * ROW_H + PAD
    img = _chart_base(W, H); draw = ImageDraw.Draw(img)
    _cheader(draw, W, PAD, titulo, subtitulo)
    cx = PAD
    for c, width in zip(cabeceras, cw):
        draw.text((cx + width // 2, HEAD_H - 18), str(col).upper() if isinstance(c, str) else str(c), font=_bc_m(15), fill=(*_MUTED_G, 220), anchor="mm"); cx += width
    for ri, f in enumerate(filas):
        ry = HEAD_H + ri * ROW_H
        _rr2(draw, PAD, ry + 3, W - PAD, ry + ROW_H - 3, r=6, fill=(*(_PANEL if ri % 2 == 0 else _BG), 160))
        cx = PAD
        for ci, cell in enumerate(f):
            txt = f"🥇 {cell}" if medallas and ci == 0 and ri == 0 else f"🥈 {cell}" if medallas and ci == 0 and ri == 1 else f"🥉 {cell}" if medallas and ci == 0 and ri == 2 else str(cell)
            draw.text((cx + cw[ci] // 2, ry + ROW_H // 2), txt, font=_bc_b(18) if ci == 0 else _bc_m(18), fill=(*_TEXT_G, 240), anchor="mm")
            cx += cw[ci]
    buf = io.BytesIO(); img.convert("RGB").save(buf, format="PNG", optimize=True); buf.seek(0); return buf

def gen_canvas_temporada(titulo, mvp_txt, boxes, ranking_filas, cw):
    W, H, PAD = 1180, 720, 44; img = _chart_base(W, H); draw = ImageDraw.Draw(img)
    _cheader(draw, W, PAD, titulo, "Estadísticas del Servidor Actualizadas")
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
        draw.text((cx + width // 2, ry), c, font=_bc_m(14), fill=_MUTED_G, anchor="mm"); cx += width
    for ri, f in enumerate(ranking_filas[:7]):
        ry += 48; _rr2(draw, PAD, ry - 16, W - PAD, ry + 24, r=4, fill=(*(_PANEL if ri % 2 == 0 else _BG), 120))
        cx = PAD
        for ci, cell in enumerate(f):
            txt = f"🥇 {cell}" if ci == 0 and ri == 0 else f"🥈 {cell}" if ci == 0 and ri == 1 else f"🥉 {cell}" if ci == 0 and ri == 2 else str(cell)
            draw.text((cx + cw[ci] // 2, ry + 4), txt, font=_bc_b(17) if ci <= 1 else _bc_m(17), fill=(*_TEXT_G, 240), anchor="mm")
            cx += cw[ci]
    buf = io.BytesIO(); img.convert("RGB").save(buf, format="PNG", optimize=True); buf.seek(0); return buf

def _calc_tracker_metrics_from_stats(s):
    lm = s.get("last_match", {}) or {}
    rounds_played = _safe_int(s.get("rounds_played") or s.get("rounds") or lm.get("rounds_played") or lm.get("rounds"))
    damage_dealt_total = _safe_int(s.get("damage_dealt_total") or s.get("damage_dealt") or s.get("damage_done") or lm.get("damage_dealt_total") or lm.get("damage_dealt") or lm.get("damage_done"))
    damage_received_total = _safe_int(s.get("damage_received_total") or s.get("damage_received") or lm.get("damage_received_total") or lm.get("damage_received"))
    kast_rounds = _safe_int(s.get("kast_rounds") or lm.get("kast_rounds"))
    _adr_raw = s.get("adr") or lm.get("adr")
    adr = round(damage_dealt_total / rounds_played, 2) if rounds_played > 0 and damage_dealt_total > 0 else round(_safe_float(_adr_raw), 2) if _adr_raw is not None and _safe_float(_adr_raw) > 0 else None
    _dda_raw = s.get("damage_delta") or s.get("dda") or lm.get("damage_delta") or lm.get("dda")
    dda = round((damage_dealt_total - damage_received_total) / rounds_played, 2) if rounds_played > 0 and (damage_dealt_total or damage_received_total) else round(_safe_float(_dda_raw), 2) if _dda_raw is not None else None
    _kast_raw = s.get("kast") or lm.get("kast")
    kast = round((kast_rounds / rounds_played) * 100, 2) if rounds_played > 0 and kast_rounds > 0 else round(_safe_float(_kast_raw), 2) if _kast_raw is not None and _safe_float(_kast_raw) > 0 else None
    hs_raw = lm.get("hs") if lm.get("hs") is not None else s.get("hs"); hs_value = round(_safe_float(hs_raw), 2) if hs_raw is not None else None
    return {"rounds_played": rounds_played or None, "damage_dealt_total": damage_dealt_total or None, "damage_received_total": damage_received_total or None, "kast_rounds": kast_rounds or None, "adr": adr, "dda": dda, "kast": kast, "hs": hs_value}

async def _check_racha(nombre, tag, canal):
    ultimas = await bot.db.fetch("SELECT won FROM partidas WHERE jugador_nombre ILIKE $1 AND jugador_tag ILIKE $2 ORDER BY fecha DESC LIMIT 5", nombre, tag)
    if len(ultimas) < 3: return
    resultados = [r["won"] for r in ultimas]
    if all(resultados[:3]):
        buf = gen_banner_notificacion("🔥 JUGADOR EN RACHA", f"¡{nombre}#{tag} lleva 3 victorias seguidas! Tiembla VCT.", _GREEN_G)
        await canal.send(file=discord.File(fp=buf, filename="racha.png"))
    elif not any(resultados[:3]):
        buf = gen_banner_notificacion("💀 RACHA DE DERROTAS", f"{nombre}#{tag} lleva 3 derrotas seguidas. Alguien que le escondas el ratón.", _RED_G)
        await canal.send(file=discord.File(fp=buf, filename="derrotas.png"))

async def _check_rango(nombre, tag, nuevo_rango, canal):
    row = await bot.db.fetch("SELECT ultimo_rango FROM jugadores WHERE nombre ILIKE $1 AND tag ILIKE $2", nombre, tag)
    if not row: return
    viejo = row[0]["ultimo_rango"]
    if viejo and viejo != nuevo_rango and nuevo_rango:
        ranks_order = ["Iron 1","Iron 2","Iron 3", "Bronze 1","Bronze 2","Bronze 3", "Silver 1","Silver 2","Silver 3", "Gold 1","Gold 2","Gold 3", "Platinum 1","Platinum 2","Platinum 3", "Diamond 1","Diamond 2","Diamond 3", "Ascendant 1","Ascendant 2","Ascendant 3", "Immortal 1","Immortal 2","Immortal 3", "Radiant"]
        vi, ni = ranks_order.index(viejo) if viejo in ranks_order else -1, ranks_order.index(nuevo_rango) if nuevo_rango in ranks_order else -1
        if vi >= 0 and ni >= 0:
            if ni > vi:
                buf = gen_banner_notificacion("📈 ¡UPGRADE DE RANGO!", f"{nombre}#{tag} ha ascendido: {viejo} ➔ {nuevo_rango} 🎉", _GREEN_G)
                await canal.send(file=discord.File(fp=buf, filename="rank_up.png"))
            else:
                buf = gen_banner_notificacion("📉 ¡DOWNGRADE DE RANGO!", f"{nombre}#{tag} ha caido de rango: {viejo} ➔ {nuevo_rango} 😬", _RED_G)
                await canal.send(file=discord.File(fp=buf, filename="rank_down.png"))
    await bot.db.execute("UPDATE jugadores SET ultimo_rango = $1 WHERE nombre ILIKE $2 AND tag ILIKE $3", nuevo_rango, nombre, tag)

def _chart_base(W, H):
    img = Image.new("RGBA",(W,H)); d = ImageDraw.Draw(img)
    for y in range(H): d.line([(0,y),(W,y)], fill=(*_gl(_BG, tuple(max(0,v-6) for v in _BG), y/max(H-1,1)),255))
    for cx,cy,rx,ry,col,al in [(-40,-30,260,200,_TEAL,14),(W+40,H+30,220,180,_RED_G,10)]:
        g = Image.new("RGBA",(W,H),(0,0,0,0)); gd= ImageDraw.Draw(g)
        for i in range(6,0,-1): gd.ellipse([cx-rx*(i/6),cy-ry*(i/6),cx+rx*(i/6),cy+ry*(i/6)],fill=(*col,int(al*(i/6)*0.4)))
        img = Image.alpha_composite(img,g)
    return img

def _cheader(draw, W, PAD, title, sub=""):
    draw.text((PAD,14), title, font=_bc_eb(32), fill=(*_TEXT_G,240))
    if sub: draw.text((PAD,52), sub, font=_bc_r(18), fill=(*_MUTED_G,200))

def generar_tarjeta(s, modo_display, tiene_datos_db, db_stats, top_agents_db, matches=None):
    acc1, acc2 = _rank_palette(s.get("rank", "")); W, H, PAD = 1180, 680, 44; TEXT = (244, 247, 252, 255); MUTED = (160, 168, 185, 255); FAINT = (255, 255, 255, 22); POS = (92, 224, 152, 255); NEG = (239, 106, 106, 255); WARN = (255, 185, 70, 255)
    def soft_badge(x1, y1, x2, y2, fill, outline=None): draw.rounded_rectangle([x1,y1,x2,y2], radius=16, fill=fill, outline=outline, width=1)
    rank_str = s.get("rank", ""); subdivision = 1
    for part in rank_str.split():
        if part in ("1", "2", "3"): subdivision = int(part); break
    img = Image.new("RGBA", (W, H)); draw = ImageDraw.Draw(img)
    overlay = Image.new("RGBA", (W, H)); od = ImageDraw.Draw(overlay)
    top_bg = mix(acc1, (8, 10, 16), {1: 0.82, 2: 0.74, 3: 0.66}.get(subdivision, 0.74)); bottom_bg = mix(acc2, (3, 4, 8), {1: 0.82, 2: 0.74, 3: 0.66}.get(subdivision, 0.74) + 0.06)
    for y in range(H): od.line([(0,y),(W,y)], fill=(*mix(top_bg, bottom_bg, y/max(H-1,1)), 210), width=1)
    img = Image.alpha_composite(img, overlay); glow = Image.new("RGBA", (W, H), (0,0,0,0)); gd = ImageDraw.Draw(glow); gd.ellipse((-200,-140,360,340), fill=(*acc1,25)); gd.ellipse((W-360,H-300,W+100,H+100), fill=(*acc2,20)); img = Image.alpha_composite(img, glow); draw = ImageDraw.Draw(img)
    draw.text((PAD, 16), s.get('nombre','?'), font=_bc_eb(54), fill=TEXT); name_w = draw.textlength(s.get('nombre','?'), font=_bc_eb(54)); draw.text((PAD + name_w + 8, 28), f"#{s.get('tag','?')}", font=_bc_m(34), fill=MUTED)
    draw.text((PAD, 80), f"{s.get('rank','Unranked')}  ·  {s.get('rr',0)} RR  ·  Nivel {s.get('nivel','?')}", font=_bc_m(22), fill=MUTED); draw.text((PAD, 106), modo_display, font=_bc_r(18), fill=(*acc1,210)); draw.line([(PAD,132),(W-PAD,132)], fill=(255,255,255,28), width=1)
    wr_val = float(db_stats.get("winrate") or s.get("winrate") or 0); metrics = [("KDA", fmt_num(db_stats.get("kda") if tiene_datos_db else s.get("kda"), 2), None, True), ("ACS", fmt_num(db_stats.get("acs_medio") if tiene_datos_db else s.get("acs"), 1), None, False), ("HS", fmt_num(db_stats.get("hs_medio") if tiene_datos_db else s.get("hs"), 1, "%"), None, False), ("WR", fmt_num(wr_val, 1, "%"), POS if wr_val >= 50 else WARN if wr_val >= 45 else NEG, False), ("ADR", fmt_num(db_stats.get("adr_medio") if tiene_datos_db else s.get("adr"), 1), None, False)]; col_w = (W - PAD*2) // 5
    for i, (label, value, accent, is_hero) in enumerate(metrics):
        x = PAD + i * col_w; draw.text((x, 144), label, font=_bc_m(14), fill=MUTED); draw.text((x, 162), value, font=_bc_eb(38 if is_hero else 30), fill=accent or TEXT)
        if i < 4: draw.line([(x+col_w-2, 148),(x+col_w-2, 206)], fill=(255,255,255,16), width=1)
    draw.line([(PAD,218),(W-PAD,218)], fill=(255,255,255,22), width=1); BY = 238; MID = 548; RX = MID + 38
    draw.text((PAD, BY), "Resumen", font=_bc_eb(28), fill=TEXT); draw.text((PAD, BY+34), f"{db_stats.get('total_matches', 0) if tiene_datos_db else 0} partidas analizadas", font=_bc_r(16), fill=MUTED)
    dda_val = db_stats.get("dda_medio") if tiene_datos_db else None; resumen = [("KAST", fmt_num(db_stats.get("kast_medio"),1,"%") if tiene_datos_db else "—", TEXT), ("DDA", fmt_num(dda_val,1) if tiene_datos_db else "—", POS if dda_val and float(dda_val) > 0 else NEG if dda_val and float(dda_val) < 0 else TEXT), ("Agente principal", (db_stats.get("main_agent") or s.get("agent") or "?") if tiene_datos_db else "—", TEXT)]
    racha = 0; racha_tipo = None
    for m in (matches or [])[:10]:
        resultado = m.get("won")
        if resultado is None: continue
        tipo = "W" if resultado else "L"
        if racha_tipo is None: racha_tipo = tipo
        if tipo == racha_tipo: racha += 1
        else: break
    if racha_tipo and racha > 0: resumen.append(("RACHA ACTUAL", f"▲ {racha} VICTORIA{'S' if racha > 1 else ''}" if racha_tipo == "W" else f"▼ {racha} DERROTA{'S' if racha > 1 else ''}", POS if racha_tipo == "W" else NEG))
    for idx, (lab, val, col) in enumerate(resumen):
        ry = BY + 80 + idx * 58; draw.text((PAD, ry), lab, font=_bc_r(14), fill=MUTED); draw.text((PAD, ry+18), val, font=_bc_b(22), fill=col)
        if idx < len(resumen)-1: draw.line([(PAD, ry+52),(MID-18, ry+52)], fill=FAINT, width=1)
    draw.line([(MID,BY),(MID,H-PAD)], fill=(255,255,255,18), width=1); lm = s.get("last_match",{}) or {}; draw.text((RX, BY), "Última partida", font=_bc_eb(28), fill=TEXT); draw.text((W-PAD, BY+8), "Victoria" if lm.get("won") else "Derrota", font=_bc_eb(24), fill=POS if lm.get("won") else NEG, anchor="ra")
    kda_str = f"{lm.get('kills',0)}/{lm.get('deaths',0)}/{lm.get('assists',0)}"; draw.text((RX, BY+34), kda_str, font=_bc_eb(52), fill=TEXT)
    ag_last = lm.get("agente","")
    if ag_last:
        aw = max(90, 24 + int(draw.textlength(ag_last, font=_bc_m(15)))); ax = RX + int(draw.textlength(kda_str, font=_bc_eb(52))) + 14; ay = BY + 48
        soft_badge(ax, ay, ax+aw, ay+30, (*mix(acc1,(20,20,20),0.6),100), (*acc1,80)); draw.text((ax+aw//2, ay+5), ag_last, font=_bc_m(15), fill=TEXT, anchor="ma")
    lm_y = BY + 102; lm_metrics = [("ACS", fmt_num(lm.get("acs"),1), TEXT), ("HS", fmt_num(lm.get("hs"),1,"%"), TEXT), ("ADR", fmt_num(lm.get("adr"),1), TEXT), ("KAST", fmt_num(lm.get("kast"),1,"%"), TEXT), ("DDA", fmt_num(lm.get("dda"),1), POS if lm.get("dda") and float(lm.get("dda")) > 0 else NEG if lm.get("dda") and float(lm.get("dda")) < 0 else TEXT)]; lm_col_w = (W - PAD - RX) // 5
    for i,(lab,val,col) in enumerate(lm_metrics):
        lx = RX + i * lm_col_w; draw.text((lx, lm_y), lab, font=_bc_r(13), fill=MUTED); draw.text((lx, lm_y+16), val, font=_bc_b(20), fill=col)
    draw.line([(RX, lm_y+44),(W-PAD, lm_y+44)], fill=FAINT, width=1); draw.text((RX, lm_y+54), "MAPA", font=_bc_r(13), fill=MUTED); draw.text((RX, lm_y+70), s.get("mapa","?"), font=_bc_b(20), fill=TEXT); draw.line([(RX, lm_y+98),(W-PAD, lm_y+98)], fill=FAINT, width=1); draw.text((RX, lm_y+110), "Agentes más usados", font=_bc_eb(22), fill=TEXT); bx, by_ = RX, lm_y + 142
    for ag in (top_agents_db[:5] if top_agents_db else (s.get("top_agents") or [])[:5]):
        aw2 = max(90, 24 + int(draw.textlength(ag, font=_bc_m(15))))
        if bx + aw2 > W - PAD - 10: bx = RX; by_ += 46
        soft_badge(bx, by_, bx+aw2, by_+36, (*mix(acc1,(20,20,20),0.6),100), (*acc1,60)); draw.text((bx+aw2//2, by_+6), ag, font=_bc_m(15), fill=TEXT, anchor="ma"); bx += aw2 + 8
    buf = io.BytesIO(); img.convert("RGB").save(buf, format="PNG", optimize=True); buf.seek(0); return buf

def gen_evolucion(rows, nombre_jugador):
    if not rows: return None
    W,H,PAD = 1180,660,44; img = _chart_base(W,H); draw = ImageDraw.Draw(img); fechas = [r["fecha"].strftime("%d/%m") if hasattr(r.get("fecha",""),"strftime") else "" for r in rows]; acs_v = [float(r["acs"]) if r["acs"] is not None else None for r in rows]; dda_v = [float(r["dda"]) if r["dda"] is not None else None for r in rows]; hs_v = [float(r["hs"]) if r.get("hs") is not None else None for r in rows]; n = len(rows)
    _cheader(draw, W, PAD, f"Evolución · {nombre_jugador}", f"{n} partidas  ·  ACS / DDA / HS%")
    panels = [("ACS",acs_v,_TEAL,None),("DDA",dda_v,_RED_G,0.0),("HS%",hs_v,_GOLD,None)]; TOP0 = 80; p_h = (H-TOP0-PAD)//3; GAP = 8
    for pi,(label,vals,color,zero) in enumerate(panels):
        pt = TOP0+pi*p_h+(GAP if pi>0 else 0); pb = pt+p_h-GAP; lx = PAD+54; rx = W-PAD-12
        _rr2(draw,PAD,pt-4,W-PAD,pb+4,fill=(*_PANEL,180),outline=(*_BORDER,60))
        clean = [(i,v) for i,v in enumerate(vals) if v is not None]
        if not clean: draw.text((lx+8,(pt+pb)//2),"Sin datos",font=_bc_r(16),fill=(*_MUTED_G,150),anchor="lm"); continue
        xs,ys = zip(*clean); vmn,vmx,vmed = min(ys),max(ys),sum(ys)/len(ys); rng = max(vmx-vmn,1)
        def tp(i,v): return lx+(i/max(n-1,1))*(rx-lx), pb-((v-vmn)/rng)*(pb-pt-8)-4
        if zero is not None and vmn<=zero<=vmx: draw.line([(lx,pb-((zero-vmn)/rng)*(pb-pt-8)-4),(rx,pb-((zero-vmn)/rng)*(pb-pt-8)-4)],fill=(*_MUTED_G,60),width=1)
        draw.line([(lx,pb-((vmed-vmn)/rng)*(pb-pt-8)-4),(rx,pb-((vmed-vmn)/rng)*(pb-pt-8)-4)],fill=(*color,50),width=1); draw.text((rx+6,pb-((vmed-vmn)/rng)*(pb-pt-8)-4),fmt_num(vmed,1),font=_bc_r(13),fill=(*_MUTED_G,180),anchor="lm")
        fl = Image.new("RGBA",(W,H),(0,0,0,0)); fld = ImageDraw.Draw(fl); fld.polygon([(lx,pb)]+[tp(i,v) for i,v in clean]+[(tp(xs[-1],ys[-1])[0],pb)],fill=(*color,18)); img = Image.alpha_composite(img,fl); draw = ImageDraw.Draw(img)
        for i in range(len(xs)-1): draw.line([tp(xs[i],ys[i]),tp(xs[i+1],ys[i+1])],fill=(*_gl(color,_GREEN_G,0.35) if ys[i+1]>=ys[i] else _gl(color,_RED_G,0.35),220),width=3)
        for i,v in clean:
            px_,py_=tp(i,v); draw.ellipse([px_-5,py_-5,px_+5,py_+5],fill=(*(_GREEN_G if v>=vmed else _RED_G),200)); draw.ellipse([px_-3,py_-3,px_+3,py_+3],fill=(*_TEXT_G,230))
        draw.text((PAD+8,(pt+pb)//2),label,font=_bc_eb(22),fill=(*color,230),anchor="lm")
        if pi==2:
            for i in range(0,n,max(1,n//12)): draw.text((tp(i,vmn)[0],pb+8),fechas[i] if i<len(fechas) else "",font=_bc_r(13),fill=(*_MUTED_G,160),anchor="mt")
    buf = io.BytesIO(); img.convert("RGB").save(buf,format="PNG",optimize=True); buf.seek(0); return buf

def gen_heatmap_mapas(rows):
    ms = {}
    for r in rows:
        m = r["mapa"] or "?"
        if m not in ms: ms[m] = {"acs":[], "won":[], "dda":[], "n":0}
        ms[m]["n"] += 1
        if r["acs"] is not None: ms[m]["acs"].append(float(r["acs"]))
        ms[m]["won"].append(1 if r["won"] else 0)
        if r["dda"] is not None: ms[m]["dda"].append(float(r["dda"]))
    mapas = sorted(ms.keys()); if not mapas: return None
    cols = ["MAPA","PARTIDAS","ACS","WR %","DDA"]; col_w = [180,110,110,100,110]; W = 44*2+sum(col_w)+20; H = 72+52*len(mapas)+44+20; img = _chart_base(W,H); draw = ImageDraw.Draw(img); _cheader(draw,W,44,"Rendimiento por mapa")
    cx = 44
    for col,cw in zip(cols,col_w): draw.text((cx+cw//2,58),col,font=_bc_m(16),fill=(*_MUTED_G,200),anchor="mm"); cx+=cw
    all_acs = [sum(ms[m]["acs"])/len(ms[m]["acs"]) for m in mapas if ms[m]["acs"]]; all_wr = [sum(ms[m]["won"])/len(ms[m]["won"])*100 for m in mapas]; all_dda = [sum(ms[m]["dda"])/len(ms[m]["dda"]) if ms[m]["dda"] else None for m in mapas]
    def ncol(val,vals):
        cl = [v for v in vals if v is not None]
        if not cl or max(cl)==min(cl): return _MUTED_G
        t = (val-min(cl))/(max(cl)-min(cl))
        return _GREEN_G if t>0.66 else _GOLD if t>0.33 else _RED_G
    for ri,m in enumerate(mapas):
        st = ms[m]; ry = 72+ri*52; _rr2(draw,44,ry+3,W-44,ry+49,r=6,fill=(*(_PANEL if ri%2==0 else _BG),160)); av = sum(st["acs"])/len(st["acs"]) if st["acs"] else None; wv = sum(st["won"])/len(st["won"])*100; dv = sum(st["dda"])/len(st["dda"]) if st["dda"] else None; row = [(m,None),(str(st["n"]),_MUTED_G),(fmt_num(av,0),ncol(av,all_acs) if av else _MUTED_G),(fmt_num(wv,1,"%"),ncol(wv,all_wr)),(fmt_num(dv,1) if dv is not None else "—",ncol(dv,[v for v in all_dda if v is not None]) if dv is not None else _MUTED_G)]; cx = 44
        for ci,((txt,col),cw) in enumerate(zip(row,col_w)): draw.text((cx+cw//2,ry+26),txt,font=_bc_b(20) if ci==0 else _bc_m(20),fill=(*(col or _TEXT_G),230),anchor="mm"); cx+=cw
    buf = io.BytesIO(); img.convert("RGB").save(buf,format="PNG",optimize=True); buf.seek(0); return buf

def gen_pie_agentes(agent_rows, titulo="Agentes jugados"):
    ags = [r["agente"] for r in agent_rows if r["agente"] not in (None,"Desconocido")]; cts = [r["count"] for r in agent_rows if r["agente"] not in (None,"Desconocido")]; if not ags: return None
    W,H,PAD,CX,CY,RO,RI = 900,480,40,260,240,170,90; img = _chart_base(W,H); draw = ImageDraw.Draw(img); _cheader(draw,W,PAD,titulo,f"{sum(cts)} partidas · {len(ags)} agentes"); total = sum(cts); start = -90.0
    for i,(ag,cnt) in enumerate(zip(ags,cts)):
        col = CHART_COLORS[i%len(CHART_COLORS)]; ang = cnt/total*360; s = Image.new("RGBA",(W,H),(0,0,0,0)); ds = ImageDraw.Draw(s); ds.pieslice([CX-RO,CY-RO,CX+RO,CY+RO],start,start+ang,fill=(*col,210)); ds.ellipse([CX-RI,CY-RI,CX+RI,CY+RI],fill=(0,0,0,0)); img = Image.alpha_composite(img,s); draw = ImageDraw.Draw(img)
        if cnt/total>0.05: draw.text((CX+(RI+(RO-RI)*0.55)*_math.cos(_math.radians(start+ang/2)),CY+(RI+(RO-RI)*0.55)*_math.sin(_math.radians(start+ang/2))),f"{cnt/total*100:.0f}%",font=_bc_b(16),fill=(*_TEXT_G,230),anchor="mm")
        start+=ang
    draw.ellipse([CX-RI,CY-RI,CX+RI,CY+RI],fill=(*_PANEL,255)); draw.text((CX,CY-12),str(total),font=_bc_eb(34),fill=(*_TEXT_G,240),anchor="mm"); draw.text((CX,CY+18),"partidas",font=_bc_r(16),fill=(*_MUTED_G,200),anchor="mm"); LX = CX+RO+40
    for i,(ag,cnt) in enumerate(zip(ags,cts)):
        col = CHART_COLORS[i%len(CHART_COLORS)]; ly = 95+i*48; if ly+24>H-PAD: break
        _rr2(draw,LX,ly+2,LX+16,ly+18,r=4,fill=(*col,220)); draw.text((LX+24,ly+10),ag,font=_bc_b(18),fill=(*_TEXT_G,230),anchor="lm"); draw.rounded_rectangle([LX+130, ly+6, LX+130+210, ly+14], radius=4, fill=(*col,40)); draw.rounded_rectangle([LX+130, ly+6, LX+130+max(int(210*(cnt/total)), 8), ly+14], radius=4, fill=(*col,200)); draw.text((W-PAD, ly+10),f"{(cnt/total)*100:.0f}%",font=_bc_m(17),fill=(*_MUTED_G,200),anchor="rm")
    buf = io.BytesIO(); img.convert("RGB").save(buf,format="PNG",optimize=True); buf.seek(0); return buf

def gen_barra_comparativa(stats_a, nombre_a, stats_b, nombre_b):
    mets = ["ACS","KDA","ADR","KAST %","DDA","WR %","HS %"]; va = [float(stats_a.get("acs_medio") or 0),round((float(stats_a.get("tk") or 0)+float(stats_a.get("ta") or 0))/max(float(stats_a.get("td") or 1),1),2),float(stats_a.get("adr_medio") or 0),float(stats_a.get("kast_medio") or 0),float(stats_a.get("dda_medio") or 0),float(stats_a.get("winrate") or 0),float(stats_a.get("hs_medio") or 0)]; vb = [float(stats_b.get("acs_medio") or 0),round((float(stats_b.get("tk") or 0)+float(stats_b.get("ta") or 0))/max(float(stats_b.get("td") or 1),1),2),float(stats_b.get("adr_medio") or 0),float(stats_b.get("kast_medio") or 0),float(stats_b.get("dda_medio") or 0),float(stats_b.get("winrate") or 0),float(stats_b.get("hs_medio") or 0)]; W, H = 1000, 125+7*70+44; img = _chart_base(W,H); draw = ImageDraw.Draw(img); _cheader(draw,W,44,f"{nombre_a}  vs  {nombre_b}","Comparativa de métricas competitivas"); MID = W//2; BAR_MAX = MID-44-65
    _rr2(draw,MID-140,82,MID-10,106,r=4,fill=(*_TEAL,180)); draw.text((MID-75,94),nombre_a[:16],font=_bc_m(16),fill=(*_TEXT_G,230),anchor="mm"); _rr2(draw,MID+10,82,MID+140,106,r=4,fill=(*_RED_G,180)); draw.text((MID+75,94),nombre_b[:16],font=_bc_m(16),fill=(*_TEXT_G,230),anchor="mm")
    for i,(met,a,b) in enumerate(zip(mets,va,vb)):
        ry = 125+i*70; if i%2==0: _rr2(draw,44,ry+4,W-44,ry+66,r=6,fill=(*_PANEL,140))
        draw.text((MID,ry+35),met,font=_bc_eb(22),fill=(*_MUTED_G,200),anchor="mm"); vmx = max(abs(a),abs(b),0.01); _rr2(draw,MID-65-max(int(BAR_MAX*abs(a)/vmx), 8),ry+18,MID-65,ry+52,r=4,fill=(*_TEAL,200)); draw.text((MID-75,ry+35),fmt_num(a,1),font=_bc_b(20),fill=(255,255,255,255),anchor="rm"); _rr2(draw,MID+65,ry+18,MID+65+max(int(BAR_MAX*abs(b)/vmx), 8),ry+52,r=4,fill=(*_RED_G,200)); draw.text((MID+75,ry+35),fmt_num(b,1),font=_bc_b(20),fill=(255,255,255,255),anchor="lm")
    buf = io.BytesIO(); img.convert("RGB").save(buf,format="PNG",optimize=True); buf.seek(0); return buf

def gen_precision(rows, nombre_jugador):
    hd = [(r["fecha"].strftime("%d/%m") if hasattr(r.get("fecha",""),"strftime") else "",float(r["hs"])) for r in rows if r.get("hs") is not None]; if not hd: return None
    fechas,vals = zip(*hd); n = len(vals); media = sum(vals)/n; W,H,PAD = 1180,380,44; img = _chart_base(W,H); draw = ImageDraw.Draw(img); _cheader(draw,W,PAD,f"Precisión HS% · {nombre_jugador}",f"Media {media:.1f}%   Mejor {max(vals):.1f}%   Peor {min(vals):.1f}%   {n} partidas"); LEFT, RIGHT, TOP, BOT = PAD+54, W-PAD-16, 80, H-46; vmn, vmx = max(0,min(vals)-6), max(vals)+6; rng = max(vmx-vmn,1)
    def tp(i,v): return LEFT+(i/max(n-1,1))*(RIGHT-LEFT), BOT-((v-vmn)/rng)*(BOT-TOP)
    for ti in range(5):
        ty = BOT-((vmn+(rng/4)*ti-vmn)/rng)*(BOT-TOP); draw.line([(LEFT,ty),(RIGHT,ty)],fill=(*_BORDER,40),width=1); draw.text((LEFT-8,ty),f"{vmn+(rng/4)*ti:.0f}%",font=_bc_r(13),fill=(*_MUTED_G,160),anchor="rm")
    draw.line([(LEFT,BOT-((media-vmn)/rng)*(BOT-TOP)),(RIGHT,BOT-((media-vmn)/rng)*(BOT-TOP))],fill=(*_MUTED_G,50),width=1); draw.text((RIGHT+6,BOT-((media-vmn)/rng)*(BOT-TOP)),f"{media:.1f}%",font=_bc_m(14),fill=(*_MUTED_G,200),anchor="lm")
    fl = Image.new("RGBA",(W,H),(0,0,0,0)); fld = ImageDraw.Draw(fl); fld.polygon([(LEFT,BOT)]+[tp(i,v) for i,v in enumerate(vals)]+[(RIGHT,BOT)],fill=(*_GOLD,22)); img = Image.alpha_composite(img,fl); draw = ImageDraw.Draw(img)
    for i in range(n-1): draw.line([tp(i,vals[i]),tp(i+1,vals[i+1])],fill=(*_gl(_GOLD,_GREEN_G,0.4) if vals[i+1]>vals[i] else _gl(_GOLD,_RED_G,0.4),220),width=3)
    for i,v in enumerate(vals): px_,py_=tp(i,v); draw.ellipse([px_-5,py_-5,px_+5,py_+5],fill=(*(_GREEN_G if v>=media else _RED_G),200)); draw.ellipse([px_-3,py_-3,px_+3,py_+3],fill=(*_TEXT_G,230))
    for i in range(0,n,max(1,n//12)): draw.text((tp(i,vmn)[0],BOT+6),fechas[i] if i<len(fechas) else "",font=_bc_r(13),fill=(*_MUTED_G,160),anchor="mt")
    _rr2(draw,W-PAD-220,10,W-PAD,74,r=8,fill=(*_PANEL,220)); draw.line([(W-PAD-220,28),(W-PAD-192,28)],fill=(*_GOLD,210),width=3); draw.text((W-PAD-184,22),"HS% real",font=_bc_m(16),fill=(*_TEXT_G,230))
    buf = io.BytesIO(); img.convert("RGB").save(buf,format="PNG",optimize=True); buf.seek(0); return buf

# ==============================================================================
# ENGINES GRÁFICOS COMPLEMENTARIOS (PIL CANVAS v1.0.4)
# ==============================================================================
def gen_banner_notificacion(titulo, mensaje, color_neon=_TEAL):
    W, H = 750, 160
    img = Image.new("RGBA", (W, H))
    draw = ImageDraw.Draw(img)
    for y in range(H): 
        draw.line([(0, y), (W, y)], fill=(*_gl(_BG, (18, 22, 32), y/(H-1)), 255))
    _rr2(draw, 14, 14, W - 14, H - 14, r=10, fill=(15, 18, 26, 200), outline=_BORDER, w=1)
    _rr2(draw, 22, 24, 28, H - 24, r=3, fill=color_neon)
    draw.text((44, 28), titulo, font=_bc_eb(26), fill=_TEXT_G)
    if draw.textlength(mensaje, font=_bc_r(18)) > (W - 80):
        l1 = l2 = ""
        for p in mensaje.split(" "):
            if draw.textlength(l1 + " " + p, font=_bc_r(18)) < (W - 90): l1 += " " + p
            else: l2 += " " + p
        draw.text((44, 68), l1.strip(), font=_bc_r(18), fill=_MUTED_G)
        if l2: draw.text((44, 94), l2.strip(), font=_bc_r(18), fill=_MUTED_G)
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
            txt = f"🥇 {cell}" if ci == 0 and ri == 0 else f"🥈 {cell}" if ci == 0 and ri == 1 else f"🥉 {cell}" if ci == 0 and ri == 2 else str(cell)
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
            txt = f"🥇 {cell}" if ci == 0 and ri == 0 else f"🥈 {cell}" if ci == 0 and ri == 1 else f"🥉 {cell}" if ci == 0 and ri == 2 else str(cell)
            draw.text((cx + cw[ci] // 2, ry + 4), txt, font=_bc_b(17) if ci <= 1 else _bc_m(17), fill=(*_TEXT_G, 240), anchor="mm")
            cx += cw[ci]
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf

# ==============================================================================
# COMANDOS DE DISCORD REFACTORIZADOS COMPLETO A BANNER/TABLAS
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
    await interaction.response.defer(); server_id = str(interaction.guild_id)
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
        await interaction.followup.send(file=discord.File(fp=buf, filename="stats.png"))
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
    if not amigos: await interaction.response.send_message("❌ No hay nadie en la lista. Usad `/add` primero."); return
    await interaction.response.defer()
    scores = await bot.db.fetch("SELECT p.jugador_nombre as nombre, p.jugador_tag as tag, AVG(p.acs) as acs_medio, SUM(p.kills) as tk, SUM(p.deaths) as td, SUM(p.assists) as ta, COUNT(*) as total_matches, COUNT(CASE WHEN p.won THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0) as winrate, (SELECT agente FROM partidas p2 WHERE p2.jugador_nombre = p.jugador_nombre AND p2.jugador_tag = p.jugador_tag AND ($2 = '%' OR LOWER(p2.modo) = LOWER($2)) GROUP BY agente ORDER BY COUNT(*) DESC LIMIT 1) as main_agent FROM partidas p JOIN jugadores j ON p.jugador_nombre = j.nombre AND p.jugador_tag = j.tag WHERE j.server_id = $1 AND ($2 = '%' OR LOWER(p.modo) = LOWER($2)) GROUP BY p.jugador_nombre, p.jugador_tag ORDER BY acs_medio DESC", server_id, modo_busqueda)
    if not scores:
        buf = gen_banner_notificacion("❌ SIN COMBATES REGISTRADOS", f"Todavía no hay partidas de {modo_display} en este servidor.", _GOLD); await interaction.followup.send(file=discord.File(fp=buf, filename="err_leader.png")); return
    
    # TRANSFORMACIÓN: LEADERBOARD AHORA SE DIBUJA COMO UNA TABLA COMPLETA EN IMAGEN PIL
    filas_tabla = []
    for i, p in enumerate(scores):
        kda_val = round((p["tk"] + p["ta"]) / max(p["td"], 1), 2)
        filas_tabla.append([f"{i+1}º", f"{p['nombre']}#{p['tag']}", f"{p['main_agent'] or '?'}", f"{round(p['acs_medio'],0):.0f}", f"{kda_val:.2f}", f"{round(p['winrate'],1):.1f}%", f"{p['total_matches']}"])
    
    headers_t = ["RANK", "JUGADOR", "MAiN", "ACS", "KDA", "WINRATE", "PARTIDAS"]
    cw_t = [60, 240, 140, 90, 90, 110, 100]
    buf = await asyncio.to_thread(gen_canvas_tabla, f"🏆 LEADERBOARD ({modo_display.upper()})", f"Clasificación competitiva de {len(scores)} agentes activos", headers_t, filas_tabla, cw_t, True)
    await interaction.followup.send(file=discord.File(fp=buf, filename="leaderboard.png"))

@bot.tree.command(name="temporada", description="Resumen competitivo de la temporada del servidor")
async def temporada(interaction: discord.Interaction, modo: app_commands.Choice[str] = None):
    await interaction.response.defer(); server_id = str(interaction.guild_id); modo_busqueda = "Competitive"; modo_display = modo.name if modo else "Competitivo"
    rows = await bot.db.fetch("SELECT p.jugador_nombre as nombre, p.jugador_tag as tag, AVG(p.acs) as acs_medio, COUNT(*) as partidas, COUNT(CASE WHEN p.won THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0) as winrate, AVG(CASE WHEN p.rounds_played > 0 AND p.damage_dealt_total IS NOT NULL AND p.damage_received_total IS NOT NULL THEN (p.damage_dealt_total::numeric - p.damage_received_total::numeric) / p.rounds_played ELSE p.dda END) as dda_medio FROM partidas p JOIN jugadores j ON p.jugador_nombre = j.nombre AND p.jugador_tag = j.tag WHERE j.server_id = $1 AND ($2 = '%' OR LOWER(p.modo) = LOWER($2)) GROUP BY p.jugador_nombre, p.jugador_tag ORDER BY acs_medio DESC", server_id, modo_busqueda)
    if not rows:
        buf = gen_banner_notificacion("❌ COLA VACÍA", f"Todavía no hay datos de {modo_display} en este servidor.", _GOLD); await interaction.followup.send(file=discord.File(fp=buf, filename="err_temp.png")); return
    
    # TRANSFORMACIÓN: LA FICHA COMPLETA DE RESUMEN DE LA TEMPORADA SE GENERA COMO CANVAS
    mvp = rows[0]; mvp_txt = f"{mvp['nombre']}#{mvp['tag']}  (ACS: {round(mvp['acs_medio'],1)} | WR: {round(mvp['winrate'],1)}%)"
    most_games = max(rows, key=lambda r: r["partidas"]); best_wr = max((r for r in rows if r["partidas"] >= 3), key=lambda r: float(r["winrate"] or 0), default=rows[0]); best_dda = max((r for r in rows if r["dda_medio"] is not None), key=lambda r: float(r["dda_medio"]), default=rows[0])
    
    boxes = [("MÁS PARTIDAS", f"{most_games['nombre']} ({most_games['partidas']})"), ("MEJOR WINRATE", f"{best_wr['nombre']} ({round(float(best_wr['winrate']),1)}%)"), ("MEJOR DDA", f"{best_dda['nombre']} ({round(float(best_dda['dda_medio']),1)})")]
    ranking_filas = [[f"{i+1}º", f"{r['nombre']}#{r['tag']}", f"{round(r['acs_medio'],1)}", f"{round(float(r['winrate'] or 0),1)}%", f"{r['partidas']}"] for i, r in enumerate(rows)]
    
    buf_temp = await asyncio.to_thread(gen_canvas_temporada, f"🏆 RESUMEN COMPACTO: TEMPORADA ({modo_display.upper()})", mvp_txt, boxes, ranking_filas, [60, 320, 150, 150, 120])
    await interaction.followup.send(file=discord.File(fp=buf_temp, filename="temporada.png"))

@bot.tree.command(name="lineups", description="Muestra lineups de un agente")
@app_commands.describe(agente="Nombre del agente")
@app_commands.autocomplete(agente=agente_autocomplete)
async def lineups(interaction: discord.Interaction, agente: str):
    await interaction.response.defer(); url = f"{LINEUPS_BASE}{urllib.parse.quote(agente)}"
    buf = gen_banner_notificacion(f"📚 LINEUPS DE {agente.upper()}", f"Click para abrir el mapa estratégico táctico de {agente}: {url}", _TEAL)
    await interaction.followup.send(file=discord.File(fp=buf, filename="lineups.png"))

@bot.tree.command(name="coach", description="La IA de Gemini analiza sarcásticamente la última partida")
async def coach(interaction: discord.Interaction, nombre: str, tag: str):
    await interaction.response.defer()
    if not GEMINI_API_KEY:
        buf = gen_banner_notificacion("❌ ERROR DE LLAVE", "La API Key de Gemini está ausente en el entorno.", _RED_G); await interaction.followup.send(file=discord.File(fp=buf, filename="err_key.png")); return
    server_id = str(interaction.guild_id); ultima_partida = await bot.db.fetchrow("SELECT p.kills, p.deaths, p.assists, p.acs, p.won, p.mapa, p.agente, p.hs, p.dda FROM partidas p JOIN jugadores j ON p.jugador_nombre = j.nombre AND p.jugador_tag = j.tag WHERE j.server_id = $1 AND p.jugador_nombre ILIKE $2 AND p.jugador_tag ILIKE $3 ORDER BY p.fecha DESC LIMIT 1", server_id, nombre, tag)
    if not ultima_partida:
        buf = gen_banner_notificacion("❌ AGENTE SIN REGISTRO", f"No constan partidas de {nombre}#{tag} en la base de datos.", _GOLD); await interaction.followup.send(file=discord.File(fp=buf, filename="err_coach.png")); return
    k, d, a = ultima_partida["kills"], ultima_partida["deaths"], ultima_partida["assists"]
    prompt = f"Actúa como un entrenador de eSports de Valorant muy sarcástico, crítico y con humor negro (pero sin insultos). Analiza la última partida de {nombre}: Agente: {ultima_partida['agente']}, Resultado: {'Victoria' if ultima_partida['won'] else 'Derrota'}, KDA: {k}/{d}/{a}, ACS: {ultima_partida['acs']}, DDA: {float(ultima_partida['dda'] or 0)}, HS: {float(ultima_partida['hs'] or 0)}%. Haz un comentario lapidario hiper-breve de máximo una línea."
    def ask_gemini_modern():
        return genai.Client(api_key=GEMINI_API_KEY.strip()).models.generate_content(model='gemini-2.5-flash', contents=prompt).text
    try:
        respuesta_texto = await asyncio.to_thread(ask_gemini_modern)
        buf_coach = gen_banner_notificacion(f"🤖 ENTRENADOR IA: {nombre.upper()}", respuesta_texto.strip(), _PURPLE)
        await interaction.followup.send(file=discord.File(fp=buf_coach, filename="coach_roast.png"))
    except Exception as e:
        buf = gen_banner_notificacion("❌ CORTE DE ENLACE IA", f"El coach se ha liado con los cables: {str(e)[:50]}", _RED_G); await interaction.followup.send(file=discord.File(fp=buf, filename="err_gemini.png"))

# ==============================================================================
# MANEJADORES DE ERRORES GLOBALES Y ALERTAS DE BUCLE AUTOMÁTICO DE PARTIDAS
# ==============================================================================
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    logging.exception("Slash command error", exc_info=error); buf = gen_banner_notificacion("💥 ERROR DE ÁRBOL", f"Fallo de ejecución: {str(error)[:60]}", _RED_G)
    try: await interaction.followup.send(file=discord.File(fp=buf, filename="fatal_error.png"), ephemeral=True)
    except: pass

@tasks.loop(minutes=5)
async def vigilante_partidas():
    await bot.wait_until_ready(); canal = await bot.fetch_channel(CANAL_ALERTAS_ID); jugadores = await bot.db.fetch("SELECT DISTINCT nombre, tag FROM jugadores"); if not jugadores: return
    for j in jugadores:
        try:
            nombre, tag = j["nombre"], j["tag"]; s, err = await fetch_stats(nombre, tag); await asyncio.sleep(4); if err or not s or not s.get("last_match"): continue
            lm = s["last_match"]; match_id = lm.get("id"); existe = await bot.db.fetchval("SELECT 1 FROM partidas WHERE match_id = $1 AND jugador_nombre ILIKE $2 AND jugador_tag ILIKE $3", match_id, nombre, tag)
            if match_id and not existe:
                k, d, a, acs, won, agente, mapa = lm.get("kills", 0), lm.get("deaths", 1), lm.get("assists", 0), lm.get("acs", 0), lm.get("won", False), lm.get("agente", "Desconocido"), s.get("mapa", "Desconocido")
                modo_raw = (s.get("modo") or "Unrated").strip(); m_f = "Competitive" if modo_raw.lower() == "competitive" else modo_raw
                if await bot.db.fetchval("SELECT COUNT(*) FROM partidas WHERE jugador_nombre ILIKE $1 AND jugador_tag ILIKE $2", nombre, tag) == 0: continue
                t_m = _calc_tracker_metrics_from_stats(s); hs_val = s.get("last_match", {}).get("hs") if s.get("last_match", {}).get("hs") is not None else (t_m.get("hs") if t_m.get("hs") is not None else s.get("hs"))
                await bot.db.execute("INSERT INTO partidas (match_id, jugador_nombre, jugador_tag, kills, deaths, assists, acs, won, mapa, modo, agente, adr, kast, dda, rounds_played, damage_dealt_total, damage_received_total, kast_rounds, hs) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19)", match_id, nombre, tag, k, d, a, acs, won, mapa, m_f, agente, t_m["adr"], t_m["kast"], t_m["dda"], t_m["rounds_played"], t_m["damage_dealt_total"], t_m["damage_received_total"], t_m["kast_rounds"], hs_val)
                await _check_racha(nombre, tag, canal); await _check_rango(nombre, tag, s.get("rank"), canal)
                
                # TRANSFORMACIÓN: LAS ALERTAS COMPORTAMENTALES DE NUEVAS PARTIDAS TAMBIÉN SON IMÁGENES
                buf_a = gen_banner_notificacion(f"🎮 PARTiDA DE {nombre.upper()}#{tag.upper()}", f"{'VICTORIA' if won else 'DERROTA'} en {mapa} ({m_f}) con {agente}. KDA: {k}/{d}/{a} | ACS: {acs}", _GREEN_G if won else _RED_G)
                await canal.send(file=discord.File(fp=buf_a, filename="match_alert.png"))
        except Exception as e: print(f"❌ Error vigilante: {e}")

if __name__ == "__main__":
    bot.run(TOKEN)