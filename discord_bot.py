import discord
from discord.ext import commands
from discord.ext import tasks
import requests
import os
import logging
import asyncio
import urllib.parse
import asyncpg
from dotenv import load_dotenv

from discord import app_commands

MODOS_DISCORD = [
    app_commands.Choice(name="Competitivo (Por defecto)", value="Competitive"),
    app_commands.Choice(name="Todos los modos", value="%"),
    app_commands.Choice(name="No Competitivo (Unrated)", value="Unrated"),
    app_commands.Choice(name="Swiftplay", value="Swiftplay")
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

            if k >= 25 or acs >= 300:
                title = f"🚨 ¡ALERTA DE CARREADA! 🚨"
                desc = f"**{nombre_real}#{tag_real}** acaba de destrozar el lobby jugando {modo_formateado} en {mapa} con {agente}."
            elif d > (k + 8) or acs < 130:
                title = f"🗑️ ¡Tenemos un infiltrado! 🗑️"
                desc = f"El monitor de **{nombre_real}#{tag_real}** estaba apagado jugando {modo_formateado} en {mapa} con {agente}."

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
            data = r.json()
            if not data.get("success"):
                return None, data.get("error", "Error de la API")
            return data.get("stats", {}), None
        except Exception as e:
            return None, str(e)
    
    return await asyncio.to_thread(_request)

@bot.tree.command(name="stats", description="Muestra las estadísticas de un jugador de Valorant")
@app_commands.choices(modo=MODOS_DISCORD)
async def stats(interaction: discord.Interaction, nombre: str, tag: str, region: str = "eu", modo: app_commands.Choice[str] = None):
    await interaction.response.defer()

    # Filtro de modo: por defecto Competitivo
    modo_busqueda = modo.value if modo else "Competitive"
    modo_display = modo.name if modo else "Competitivo"
    if modo_busqueda == "%":
        modo_display = "Todos los modos"

    s, err = await fetch_stats(nombre, tag, region)

    if err or not s:
        await interaction.followup.send(f"❌ Fallo al buscar a {nombre}#{tag}: {err}")
        return

    nombre_perfil = s.get('nombre') or nombre
    tag_perfil = s.get('tag') or tag

    # Consultamos a la Base de Datos
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
    
    top_agents_db = [r['agente'] for r in agent_rows]
    tiene_datos_db = db_stats and db_stats['total_matches'] > 0

    color = 0xFF4655 if not s.get("smurf") else 0x9333EA
    
    # Si tiene datos mostramos "Temporada", si no, el clásico "Últimas 10"
    descripcion = f"Nivel {s.get('nivel')} | **Temporada ({modo_display})**" if tiene_datos_db else f"Nivel {s.get('nivel')} | **Últimas 10 partidas** ({modo_display} sin datos BD)"

    embed = discord.Embed(
        title=f"📊 Estadísticas de {nombre_perfil}#{tag_perfil}",
        description=descripcion,
        color=color
    )

    if s.get("card"):
        embed.set_thumbnail(url=s.get("card"))

    # Rango SIEMPRE visible, como antes
    embed.add_field(name="🏆 Rango", value=f"**{s.get('rank')}** ({s.get('rr')} RR)", inline=True)

    if tiene_datos_db:
        # Modo Nueva Temporada (BD)
        kda_txt = f"{round((db_stats['tk'] + db_stats['ta']) / max(db_stats['td'], 1), 2)}"
        winrate_txt = f"{round(db_stats['winrate'], 1)}%"
        acs_txt = f"{round(db_stats['acs_medio'], 1)}"
        
        embed.add_field(name="📈 Winrate (Temp.)", value=f"**{winrate_txt}**", inline=True)
        embed.add_field(name="📊 Partidas", value=f"**{db_stats['total_matches']}**", inline=True)
        embed.add_field(name="⚔️ ACS (Combate)", value=acs_txt, inline=True)
        embed.add_field(name="🎯 KDA", value=kda_txt, inline=True)
        embed.add_field(name="💥 Headshot", value=f"{s.get('hs')}% (Reciente)", inline=True) 
        top_agents = top_agents_db
    else:
        # Modo Clásico (API) - ¡Vuelve la Tendencia y lo que tenías antes!
        embed.add_field(name="📈 Winrate", value=f"**{s.get('winrate')}%**", inline=True)
        embed.add_field(name="📊 Tendencia", value=f"**{s.get('trend')}**", inline=True)
        embed.add_field(name="⚔️ ACS (Combate)", value=str(s.get('acs')), inline=True)
        embed.add_field(name="🎯 KDA", value=str(s.get('kda')), inline=True)
        embed.add_field(name="💥 Headshot", value=f"{s.get('hs')}%", inline=True)
        top_agents = s.get("top_agents", [])

    # Agentes y Setups (Protegido contra crash)
    if top_agents:
        lineups_links = []
        for agent in top_agents:
            if agent == "Desconocido": continue
            agente_formateado = urllib.parse.quote(agent)
            url = f"https://lineupsvalorant.com/?agent={agente_formateado}"
            lineups_links.append(f"[{agent}]({url})")
            
        if lineups_links:
            texto_enlaces = " | ".join(lineups_links)
            if len(texto_enlaces) > 1000:
                texto_enlaces = texto_enlaces[:990] + "... (Límite de Discord)"
            embed.add_field(name="📚 Aprende setups", value=texto_enlaces, inline=False)

    # ¡RECUPERADO EL FOOTER ORIGINAL!
    estado = "⚠️ ALERTA DE SMURF / CARREADITO" if s.get("smurf") else "✅ Jugador Legal"
    modo_str = s.get('modo', 'Desconocido')
    mapa_str = s.get('mapa', 'Desconocido')
    embed.set_footer(text=f"Última partida: {modo_str} en {mapa_str} • {estado}")

    await interaction.followup.send(embed=embed)

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
    
    modo_busqueda = modo.value if modo else "Competitive"
    modo_display = modo.name if modo else "Competitivo"
    if modo_busqueda == "%":
        modo_display = "Todos los modos"

    amigos = await bot.db.fetch("SELECT nombre, tag FROM jugadores WHERE server_id = $1", server_id)
    
    if not amigos:
        await interaction.response.send_message("❌ No hay nadie en la lista. Usad `/add` primero.")
        return

    await interaction.response.defer()
    
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
        msg = f"❌ Todavía no hay partidas de **{modo_display}** guardadas."
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