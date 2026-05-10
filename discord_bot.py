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
import random
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

@bot.event
async def on_ready():
    # Creamos el pool de conexiones a la base de datos
    bot.db = await asyncpg.create_pool(DATABASE_URL)
    print(f"✅ Bot conectado a PostgreSQL")
    
    # --- LA SOLUCIÓN: EL BOT CREA LAS TABLAS SI NO EXISTEN ---
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
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (match_id, jugador_nombre, jugador_tag)
        );
    """)
    print("✅ Base de datos lista y estructurada.")
    # ---------------------------------------------------------

    print(f"✅ Bot listo en Discord: {bot.user}")
    
    await bot.tree.sync()
    if not vigilante_partidas.is_running():
        vigilante_partidas.start()

@tasks.loop(minutes=5)
async def vigilante_partidas():
    await bot.wait_until_ready() 
    
    try:
        canal = await bot.fetch_channel(CANAL_ALERTAS_ID)
    except Exception as e:
        print(f"⚠️ ERROR: No se puede encontrar el canal de alertas.")
        return

    # Obtenemos una lista única de jugadores para no comprobar al mismo 2 veces si está en varios servidores
    jugadores = await bot.db.fetch("SELECT DISTINCT nombre, tag FROM jugadores")
    if not jugadores: return

    for j in jugadores:
        nombre, tag = j["nombre"], j["tag"]
        s, err = await fetch_stats(nombre, tag)
        
        # 4 segundos de pausa en background para no llamar NUNCA la atención de la API
        await asyncio.sleep(4) 
        
        if err or not s or not s.get("last_match"):
            continue

        lm = s["last_match"]
        match_id = lm.get("id")

        # Comprobamos si este match_id exacto ya está en la base de datos
        existe = await bot.db.fetchval(
            "SELECT 1 FROM partidas WHERE match_id = $1 AND jugador_nombre = $2 AND jugador_tag = $3",
            match_id, nombre, tag
        )

        if match_id and not existe:
            k = lm.get("kills", 0)
            d = lm.get("deaths", 1)
            a = lm.get("assists", 0)
            acs = lm.get("acs", 0)
            won = lm.get("won", False)
            agente = lm.get("agente", "Desconocido")
            
            mapa = s.get('mapa', 'Desconocido')
            modo_formateado = s.get('modo', 'Unrated').capitalize()

            # Evitamos spam de la primera vez que se lee al jugador comprobando cuántas partidas tiene
            total_partidas = await bot.db.fetchval(
                "SELECT COUNT(*) FROM partidas WHERE jugador_nombre = $1 AND jugador_tag = $2",
                nombre, tag
            )
            es_primera_vez = (total_partidas == 0)

            # Insertamos la nueva partida
            await bot.db.execute("""
                INSERT INTO partidas (match_id, jugador_nombre, jugador_tag, kills, deaths, assists, acs, won, mapa, modo, agente)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            """, match_id, nombre, tag, k, d, a, acs, won, mapa, modo_formateado, agente)

            # Si es la primera partida que le registramos, cortamos aquí y no avisamos por Discord
            if es_primera_vez:
                continue

            resultado = "VICTORIA" if won else "DERROTA"
            color_borde = 0x00FF00 if won else 0xFF0000

            nombre_real = s.get('nombre') or nombre
            tag_real = s.get('tag') or tag

            title = f"🎮 Nueva partida de {nombre_real}#{tag_real}"
            desc = f"Acaba de jugar **{modo_formateado}** en **{mapa}** con **{agente}**."

            if modo_formateado == "Competitive" or modo_formateado == "Unrated":
                if k >= 25 or acs >= 300:
                    title = f"🚨 ¡ALERTA DE CARREADA! 🚨"
                    desc = f"**{nombre_real}#{tag_real}** acaba de destrozar el lobby jugando {modo_formateado} en {mapa} con {agente}."
                elif d > (k + 8) or acs < 130:
                    title = f"🗑️ ¡Tenemos un infiltrado! 🗑️"
                    desc = f"El monitor de **{nombre_real}#{tag_real}** estaba apagado jugando {modo_formateado} en {mapa} con {agente}."
                else:
                    title = f"🎮 Nueva partida de {nombre_real}#{tag_real}"
                    desc = f"Acaba de jugar **{modo_formateado}** en **{mapa}** con **{agente}**."
                
            elif modo_formateado == "Skirmish 1v1" or modo_formateado == "Skirmish 2v2":
                if k >= 10 and acs >= 150:
                    title = f"¡ALERTA DE DESTROZO EN {modo_formateado.upper()}! 🚨"
                    desc = f"**{nombre_real}#{tag_real}** acaba de arrasar en {modo_formateado} en {mapa} con {agente}."
                elif d > (k + 5) or acs < 100:
                    title = f"🗑️ Sospecha de bot en {modo_formateado.upper()} 🗑️"
                    desc = f"El monitor de **{nombre_real}#{tag_real}** estaba apagado jugando {modo_formateado} en {mapa} con {agente}."
                else:
                    title = f"🎮 Nueva partida de {nombre_real}#{tag_real}"
                    desc = f"Acaba de jugar **{modo_formateado}** en **{mapa}** con **{agente}**."

            elif modo_formateado == "Swiftplay":
                if k >= 10 and acs >= 250:
                    title = f"¡ALERTA DE DESTROZO EN {modo_formateado.upper()}! 🚨"
                    desc = f"**{nombre_real}#{tag_real}** acaba de arrasar en {modo_formateado} en {mapa} con {agente}."
                elif d > (k + 5) or acs < 120:
                    title = f"🗑️ Sospecha de bot en {modo_formateado.upper()} 🗑️"
                    desc = f"El monitor de **{nombre_real}#{tag_real}** estaba apagado jugando {modo_formateado} en {mapa} con {agente}."
                else:
                    title = f"🎮 Nueva partida de {nombre_real}#{tag_real}"
                    desc = f"Acaba de jugar **{modo_formateado}** en **{mapa}** con **{agente}**."

            elif modo_formateado == "Deathmatch" or modo_formateado == "Team deathmatch":
                if k >= 30:
                    title = f"¡ALERTA DE DESTROZO EN {modo_formateado.upper()}! 🚨"
                    desc = f"**{nombre_real}#{tag_real}** acaba de arrasar en {modo_formateado} en {mapa} con {agente}."
                elif d > (k + 10):
                    title = f"🗑️ Sospecha de bot en {modo_formateado.upper()} 🗑️"
                    desc = f"El monitor de **{nombre_real}#{tag_real}** estaba apagado jugando {modo_formateado} en {mapa} con {agente}."
                else:
                    title = f"🎮 Nueva partida de {nombre_real}#{tag_real}"
                    desc = f"Acaba de jugar **{modo_formateado}** en **{mapa}** con **{agente}**."

            embed = discord.Embed(title=title, description=desc, color=color_borde)
            embed.add_field(name="Resultado", value=f"**{resultado}**", inline=True)
            embed.add_field(name="K/D/A", value=f"{k}/{d}/{a}", inline=True)
            embed.add_field(name="ACS", value=str(acs), inline=True)
        
            if s.get("card"): 
                embed.set_thumbnail(url=s.get("card"))
                
            await canal.send(embed=embed)

async def fetch_stats(nombre, tag, region="eu"):
    def _request():
        try:
            r = requests.post(
                f"{TRACKER_URL.rstrip('/')}/tracker",
                json={"username": nombre, "tag": tag, "region": region},
                timeout=30
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


def _load_fonts():
    try:
        r1  = requests.get("https://github.com/googlefonts/roboto/raw/main/src/hinted/Roboto-Regular.ttf", timeout=10)
        r2f = requests.get("https://github.com/googlefonts/roboto/raw/main/src/hinted/Roboto-Bold.ttf",    timeout=10)
        return (
            lambda s: ImageFont.truetype(io.BytesIO(r2f.content), s),
            lambda s: ImageFont.truetype(io.BytesIO(r1.content),  s),
        )
    except:
        f = ImageFont.load_default()
        return lambda s: f, lambda s: f

_FB, _FR = _load_fonts()

def _rank_palette(rank):
    r = (rank or '').lower()
    d = {
        'radiant':   ((255, 228,  80), (255, 200,  30)),
        'immortal':  ((220,  70, 100), (180,  30,  65)),
        'ascendant': ((55,  210, 130), (20,  155,  80)),
        'diamond':   ((170, 105, 240), (100,  45, 195)),
        'platinum':  ((75,  185, 235), (30,  115, 185)),
        'gold':      ((240, 190,  55), (190, 135,  20)),
        'silver':    ((195, 195, 205), (130, 130, 145)),
        'bronze':    ((200, 125,  55), (140,  80,  20)),
        'iron':      ((115, 115, 120), (70,   70,  75)),
    }
    for key, pal in d.items():
        if key in r: return pal
    return ((255, 70, 85), (200, 20, 40))

def generar_tarjeta(s, modo_display, tiene_datos_db, db_stats, top_agents_db):
    acc1, acc2 = _rank_palette(s.get('rank', ''))
    W, H, PAD = 1000, 560, 36
    WHITE = (255, 255, 255); GRAY = (145, 142, 158); FAINT = (72, 70, 86)
    POS = (72, 224, 130);    NEG  = (224, 78, 78)

    def strip_emojis(text):
        # Replace known trend emojis with ASCII, then remove any remaining non-BMP chars
        text = text.replace('📈', '(+)').replace('📉', '(-)').replace('➖', '(=)')
        text = text.replace('⬆', '^').replace('⬇', 'v').replace('➡', '->')
        # Remove any remaining emoji / non-BMP Unicode (codepoints > U+FFFF)
        return ''.join(c for c in text if ord(c) <= 0xFFFF)


    img = Image.new('RGB', (W, H), (12, 10, 16))
    draw = ImageDraw.Draw(img)

    # Noise
    rng = random.Random(42)
    for _ in range(7000):
        x, y = rng.randint(0, W-1), rng.randint(0, H-1)
        v = rng.randint(18, 28)
        draw.point((x, y), fill=(v, v, v+4))

    # Glow top-left
    for r in range(320, 0, -4):
        alpha = int(28 * (1 - r/320))
        c = tuple(min(255, int(acc1[j]*alpha/255 + 12)) for j in range(3))
        draw.ellipse((-r//3, -r//3, r, r), fill=c)

    # Glow bottom-right
    for r in range(200, 0, -4):
        alpha = int(18 * (1 - r/200))
        c = tuple(min(255, int(acc2[j]*alpha/255 + 10)) for j in range(3))
        draw.ellipse((W-r, H-r, W+r//3, H+r//3), fill=c)

    # Left stripe
    for i in range(7):
        a = 1 - i*0.14
        draw.rectangle([i, 0, i+1, H], fill=tuple(int(acc1[j]*a) for j in range(3)))

    def ctext(cx, y, text, font, fill):
        bb = draw.textbbox((0,0), text, font=font)
        draw.text((cx-(bb[2]-bb[0])//2, y), text, font=font, fill=fill)

    # Rank icon
    ix2 = PAD
    try:
        ri_data = requests.get(s.get('rank_icon', ''), timeout=6)
        ri = Image.open(io.BytesIO(ri_data.content)).convert('RGBA').resize((82, 82))
        img.paste(ri, (PAD, PAD), ri)
        ix2 = PAD + 82 + 18
    except: pass

    # Player card faded right
    try:
        card_raw = Image.open(io.BytesIO(requests.get(s.get('card', ''), timeout=6).content)).convert('RGBA')
        cw, ch = 130, 190
        card_img = card_raw.resize((cw, ch))
        mask = Image.new('L', (cw, ch))
        for x in range(cw):
            v = int((x/cw)**1.5 * 210)
            for y in range(ch):
                edge = min(y, ch-y) / 30
                mask.putpixel((x, y), int(min(v, 200) * min(edge, 1)))
        card_img.putalpha(mask)
        img.paste(card_img, (W-cw-6, 10), card_img)
    except: pass

    # Header
    draw.text((ix2, PAD),    f"{s.get('nombre', '?')}#{s.get('tag', '?')}",            font=_FB(50), fill=WHITE)
    draw.text((ix2, PAD+58), f"{s.get('rank', 'Unranked')}  ·  {s.get('rr', 0)} RR  ·  Nv. {s.get('nivel', '?')}  ·  {modo_display}", font=_FR(19), fill=GRAY)

    # Sep 1
    S1 = 130
    draw.rectangle([PAD, S1, W-PAD, S1+1], fill=acc1)

    # 5 stats
    stats5 = [("KDA", str(s.get('kda',0))), ("ACS", str(s.get('acs',0))), ("ADR", str(s.get('adr',0))), ("HS%", f"{s.get('hs',0)}%"), ("KAST", f"{s.get('kast',0)}%")]
    tile_w = (W-PAD*2)//5
    for i, (lbl, val) in enumerate(stats5):
        cx = PAD + i*tile_w + tile_w//2
        ctext(cx, S1+22, val, _FB(48), WHITE)
        ctext(cx, S1+80, lbl, _FR(14), GRAY)
    for i in range(1, 5):
        xd = PAD + i*tile_w
        draw.rectangle([xd-1, S1+10, xd, S1+96], fill=FAINT)

    # Sep 2
    S2 = S1 + 106
    draw.rectangle([PAD, S2, W-PAD, S2+1], fill=FAINT)

    # Row 2
    delta   = s.get('damage_delta', 0)
    delta_s = ('+ ' if delta>=0 else '- ') + str(abs(delta))
    delta_c = POS if delta>=0 else NEG
    row2 = [("DELTA DÑO/RND", delta_s, delta_c), ("TENDENCIA", s.get('trend',''), WHITE), ("WINRATE BD", f"{round(db_stats['winrate'],1)}%" if tiene_datos_db else "—", WHITE), ("PARTIDAS BD", str(db_stats['total_matches']) if tiene_datos_db else "—", WHITE)]
    tile_w2 = (W-PAD*2)//4
    for i, (lbl, val, clr) in enumerate(row2):
        cx = PAD + i*tile_w2 + tile_w2//2
        ctext(cx, S2+14, lbl, _FR(13), GRAY)
        ctext(cx, S2+32, strip_emojis(val), _FB(26), clr)

    # Sep 3
    S3 = S2 + 72
    draw.rectangle([PAD, S3, W-PAD, S3+1], fill=FAINT)

    # Last match
    lm = s.get('last_match', {})
    Y3 = S3 + 16
    if lm:
        res_c = POS if lm.get('won') else NEG
        res_t = "✓ VICTORIA" if lm.get('won') else "✗ DERROTA"
        draw.text((PAD+12, Y3),    "ÚLTIMA PARTIDA",  font=_FR(13), fill=GRAY)
        draw.text((PAD+12, Y3+18), res_t, font=_FB(22), fill=res_c)
        lm_rest = strip_emojis(f"{lm.get('agente','?')}  ·  {lm.get('kills',0)}/{lm.get('deaths',0)}/{lm.get('assists',0)}  ·  ACS {lm.get('acs',0)}")
        draw.text((PAD+165, Y3+18), lm_rest, font=_FB(22), fill=WHITE)

    # Agents
    if top_agents_db:
        agents_txt = "  ·  ".join(a for a in top_agents_db if a != "Desconocido")
        if agents_txt:
            draw.text((PAD+12, Y3+50), strip_emojis(f"AGENTES   {agents_txt}"), font=_FR(14), fill=GRAY)

    # Footer
    draw.text((PAD+12, H-26), f"{s.get('mapa','?')}  ·  HenrikDev API", font=_FR(13), fill=FAINT)
    draw.ellipse((W-PAD-6, H-20, W-PAD+6, H-8), fill=acc1)

    # Rounded corners
    mask_img = Image.new('L', (W, H), 0)
    ImageDraw.Draw(mask_img).rounded_rectangle([0,0,W,H], radius=20, fill=255)
    img.putalpha(mask_img)

    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return buf

@bot.tree.command(name="stats", description="Muestra las estadísticas de un jugador de Valorant")
@app_commands.choices(modo=MODOS_DISCORD)
async def stats(interaction: discord.Interaction, nombre: str, tag: str, region: str = "eu", modo: app_commands.Choice[str] = None):
    await interaction.response.defer()

    # Por defecto busca Competitivo puro, a menos que elijas otro en el menú
    modo_busqueda = modo.value if modo else "Competitive"
    modo_display = modo.name if modo else "Competitivo"
    if modo_busqueda == "%":
        modo_display = "Todos los modos"

    s, err = await fetch_stats(nombre, tag, region)

    if err or not s:
        await interaction.followup.send(f"❌ Fallo al buscar a {nombre}#{tag}: {err}")
        return

    # Buscamos en la BD con filtro estricto de modo
    db_stats = await bot.db.fetchrow("""
        SELECT 
            SUM(kills) as tk, SUM(deaths) as td, SUM(assists) as ta,
            AVG(acs) as acs_medio,
            COUNT(CASE WHEN won THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0) as winrate,
            COUNT(*) as total_matches
        FROM partidas 
        WHERE jugador_nombre = $1 AND jugador_tag = $2 AND modo ILIKE $3
    """, nombre, tag, modo_busqueda)

    agent_rows = await bot.db.fetch("""
        SELECT agente, COUNT(*) as count 
        FROM partidas 
        WHERE jugador_nombre = $1 AND jugador_tag = $2 AND modo ILIKE $3
        GROUP BY agente 
        ORDER BY count DESC
    """, nombre, tag, modo_busqueda)

    top_agents_db  = [r['agente'] for r in agent_rows]
    tiene_datos_db = db_stats and db_stats['total_matches'] > 0

    buf = await asyncio.to_thread(generar_tarjeta, s, modo_display, tiene_datos_db, db_stats or {}, top_agents_db)
    archivo = discord.File(fp=buf, filename="stats.png")

    # Embed mínimo para el color de rango + links de setups
    rank_str = s.get('rank', 'Unranked')
    def rank_color(r):
        r = (r or '').lower()
        if 'radiant'   in r: return 0xFEFFB3
        if 'immortal'  in r: return 0xBD4863
        if 'ascendant' in r: return 0x4CB87A
        if 'diamond'   in r: return 0x9B72CF
        if 'platinum'  in r: return 0x5EAAD7
        if 'gold'      in r: return 0xE8B84B
        if 'silver'    in r: return 0xA8A8A8
        if 'bronze'    in r: return 0xC07B35
        if 'iron'      in r: return 0x6E6E6E
        return 0xFF4655
    embed = discord.Embed(color=0x9333EA if s.get('smurf') else rank_color(rank_str))
    embed.set_image(url="attachment://stats.png")

    if tiene_datos_db and top_agents_db:
        links = []
        for agent in top_agents_db:
            if agent == 'Desconocido': continue
            links.append(f"[{agent}](https://lineupsvalorant.com/?agent={urllib.parse.quote(agent)})")
        if links:
            embed.add_field(name="📚 Setups", value="  ·  ".join(links), inline=False)

    await interaction.followup.send(file=archivo, embed=embed)


@bot.tree.command(name="add", description="Guarda a un colega en la base de datos del servidor")
async def add(interaction: discord.Interaction, nombre: str, tag: str):
    server_id = str(interaction.guild_id)
    try:
        await bot.db.execute(
            "INSERT INTO jugadores (server_id, nombre, tag) VALUES ($1, $2, $3)",
            server_id, nombre, tag
        )
        await interaction.response.send_message(f"✅ Añadido a la lista de la temporada: **{nombre}#{tag}**")
    except asyncpg.exceptions.UniqueViolationError:
        await interaction.response.send_message(f"⚠️ {nombre}#{tag} ya está en la lista.")

@bot.tree.command(name="leaderboard", description="Ranking de los colegas del servidor")
@app_commands.choices(modo=MODOS_DISCORD)
async def leaderboard(interaction: discord.Interaction, modo: app_commands.Choice[str] = None):
    server_id = str(interaction.guild_id)
    
    # Por defecto busca Competitivo, a menos que elijas otro en el menú
    modo_busqueda = modo.value if modo else "Competitive"
    modo_display = modo.name if modo else "Competitivo"
    if modo_busqueda == "%":
        modo_display = "Todos los modos"

    amigos = await bot.db.fetch("SELECT nombre, tag FROM jugadores WHERE server_id = $1", server_id)
    
    if not amigos:
        await interaction.response.send_message("❌ No hay nadie en la lista. Usad `/add` primero.")
        return

    await interaction.response.defer()
    
    # Consultamos la BD usando el filtro de modo ($2)
    scores = await bot.db.fetch("""
        SELECT p.jugador_nombre as nombre, p.jugador_tag as tag, 
               AVG(p.acs) as acs_medio, 
               SUM(p.kills) as tk, SUM(p.deaths) as td, SUM(p.assists) as ta,
               COUNT(*) as total_matches,
               (
                   SELECT agente 
                   FROM partidas p2 
                   WHERE p2.jugador_nombre = p.jugador_nombre AND p2.jugador_tag = p.jugador_tag AND p2.modo ILIKE $2
                   GROUP BY agente ORDER BY COUNT(*) DESC LIMIT 1
               ) as main_agent
        FROM partidas p
        JOIN jugadores j ON p.jugador_nombre = j.nombre AND p.jugador_tag = j.tag
        WHERE j.server_id = $1 AND p.modo ILIKE $2
        GROUP BY p.jugador_nombre, p.jugador_tag
        ORDER BY acs_medio DESC
    """, server_id, modo_busqueda)

    if not scores:
        msg = f"❌ Todavía no hay partidas guardadas de **{modo_display}** en este servidor para generar el ranking."
        await interaction.followup.send(msg)
        return

    embed = discord.Embed(title=f"🏆 Leaderboard ({modo_display})", color=0xFFD700)
    
    for i, p in enumerate(scores):
        medalla = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else "🔹"
        
        nombre_lb = p['nombre']
        tag_lb = p['tag']
        main_agent = p['main_agent'] or "Desconocido"
        acs_val = round(p['acs_medio'], 1)
        kda_val = round((p['tk'] + p['ta']) / max(p['td'], 1), 2)
        partidas_jugadas = p['total_matches']

        stats_txt = f"**ACS:** {acs_val} | **KDA:** {kda_val} | **Partidas:** {partidas_jugadas}"
        embed.add_field(name=f"{medalla} {nombre_lb}#{tag_lb} ({main_agent})", value=stats_txt, inline=False)

    await interaction.followup.send(embed=embed)

bot.run(TOKEN)