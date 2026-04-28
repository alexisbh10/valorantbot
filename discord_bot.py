import discord
from discord.ext import commands
from discord.ext import tasks
import requests
import os
import logging
import json
import asyncio
import urllib.parse
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
TRACKER_URL = os.getenv("TRACKER_URL", "http://localhost:8000")
FRIENDS_FILE = "amigos_valorant.json"
LAST_MATCHES_FILE = "ultimas_partidas.json"

logging.basicConfig(level=logging.INFO)
bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())

CANAL_ALERTAS_ID = 1496835339828990078 

def load_json(file_path):
    if os.path.exists(file_path):
        with open(file_path, "r") as f:
            return json.load(f)
    return {}

def save_json(file_path, data):
    with open(file_path, "w") as f:
        json.dump(data, f, indent=4)

last_matches_cache = load_json(LAST_MATCHES_FILE)
friends = load_json(FRIENDS_FILE)

@bot.event
async def on_ready():
    print(f"✅ Bot listo: {bot.user}")
    await bot.tree.sync()
    if not vigilante_partidas.is_running():
        vigilante_partidas.start()

@tasks.loop(minutes=5)
async def vigilante_partidas():
    await bot.wait_until_ready() 
    if not friends: return
    
    try:
        canal = await bot.fetch_channel(CANAL_ALERTAS_ID)
    except Exception as e:
        print(f"⚠️ ERROR: No se puede encontrar el canal de alertas.")
        return

    for server_id, friend_list in friends.items():
        for f in friend_list:
            nombre, tag = f["nombre"], f["tag"]
            s, err = await fetch_stats(nombre, tag)
            
            # 4 segundos de pausa en background para no llamar NUNCA la atención de la API
            await asyncio.sleep(4) 
            
            if err or not s or not s.get("last_match"):
                continue

            lm = s["last_match"]
            match_id = lm.get("id")
            key = f"{nombre}#{tag}"

            if match_id and last_matches_cache.get(key) != match_id:
                es_primera_vez = (last_matches_cache.get(key) is None)
                
                last_matches_cache[key] = match_id
                save_json(LAST_MATCHES_FILE, last_matches_cache)

                if es_primera_vez:
                    continue

                k = lm.get("kills", 0)
                d = lm.get("deaths", 1)
                a = lm.get("assists", 0)
                acs = lm.get("acs", 0)
                won = lm.get("won", False)
                
                resultado = "VICTORIA" if won else "DERROTA"
                color_borde = 0x00FF00 if won else 0xFF0000

                nombre_real = s.get('nombre') or nombre
                tag_real = s.get('tag') or tag
                mapa = s.get('mapa', 'Desconocido')
                modo_formateado = s.get('modo', 'Unrated').capitalize()

                title = f"🎮 Nueva partida de {nombre_real}#{tag_real}"
                desc = f"Acaba de jugar **{modo_formateado}** en **{mapa}**."

                if k >= 25 or acs >= 300:
                    title = f"🚨 ¡ALERTA DE CARREADA! 🚨"
                    desc = f"**{nombre_real}#{tag_real}** acaba de destrozar el lobby jugando {modo_formateado} en {mapa}."
                elif d > (k + 8) or acs < 130:
                    title = f"🗑️ ¡Tenemos un infiltrado! 🗑️"
                    desc = f"El monitor de **{nombre_real}#{tag_real}** estaba apagado jugando {modo_formateado} en {mapa}."

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
async def stats(interaction: discord.Interaction, nombre: str, tag: str, region: str = "eu"):
    await interaction.response.defer()

    s, err = await fetch_stats(nombre, tag, region)

    if err or not s:
        # AHORA TE DARÁ EL ERROR REAL Y SABRÁS QUÉ PASA
        await interaction.followup.send(f"❌ Fallo al buscar a {nombre}#{tag}: {err}")
        return

    nombre_perfil = s.get('nombre') or nombre
    tag_perfil = s.get('tag') or tag

    color = 0xFF4655 if not s.get("smurf") else 0x9333EA
    embed = discord.Embed(
        title=f"📊 Estadísticas de {nombre_perfil}#{tag_perfil}",
        description=f"Nivel {s.get('nivel')} | **Últimas 10 partidas**",
        color=color
    )

    if s.get("card"):
        embed.set_thumbnail(url=s.get("card"))

    embed.add_field(name="🏆 Rango", value=f"**{s.get('rank')}** ({s.get('rr')} RR)", inline=True)
    embed.add_field(name="📈 Winrate", value=f"**{s.get('winrate')}%**", inline=True)
    embed.add_field(name="📊 Tendencia", value=f"**{s.get('trend')}**", inline=True)

    embed.add_field(name="⚔️ ACS (Combate)", value=str(s.get('acs')), inline=True)
    embed.add_field(name="🎯 KDA", value=str(s.get('kda')), inline=True)
    embed.add_field(name="💥 Headshot", value=f"{s.get('hs')}%", inline=True)

    top_agents = s.get("top_agents", [])
    if top_agents:
        agentes_str = " | ".join(top_agents)
        #embed.add_field(name="🕵️ Agentes Jugados", value=f"**{agentes_str}**", inline=False)
        
        lineups_links = []
        for agent in top_agents:
            agente_formateado = urllib.parse.quote(agent)
            url = f"https://lineupsvalorant.com/?agent={agente_formateado}"
            lineups_links.append(f"[{agent}]({url})")
            
        embed.add_field(name="📚 Aprende setups", value=" | ".join(lineups_links), inline=False)

    estado = "⚠️ ALERTA DE SMURF / CARREADITO" if s.get("smurf") else "✅ Jugador Legal"
    modo_str = s.get('modo', 'Desconocido')
    mapa_str = s.get('mapa', 'Desconocido')
    embed.set_footer(text=f"Última partida: {modo_str} en {mapa_str} • {estado}")

    await interaction.followup.send(embed=embed)

@bot.tree.command(name="add", description="Guarda a un colega en la lista del servidor")
async def add(interaction: discord.Interaction, nombre: str, tag: str):
    server_id = str(interaction.guild_id)
    if server_id not in friends:
        friends[server_id] = []
    
    if any(f["nombre"].lower() == nombre.lower() and f["tag"].lower() == tag.lower() for f in friends[server_id]):
        await interaction.response.send_message(f"⚠️ {nombre}#{tag} ya está en la lista.")
        return

    friends[server_id].append({"nombre": nombre, "tag": tag})
    save_json(FRIENDS_FILE, friends)
    await interaction.response.send_message(f"✅ Añadido a la lista: **{nombre}#{tag}**")

@bot.tree.command(name="leaderboard", description="Ranking de los colegas del servidor")
async def leaderboard(interaction: discord.Interaction):
    server_id = str(interaction.guild_id)

    if server_id not in friends or not friends[server_id]:
        await interaction.response.send_message("❌ No hay nadie en la lista. Usad `/add` primero.")
        return

    await interaction.response.defer()
    
    scores = []
    jugadores_fantasma = []

    for amigo in friends[server_id]:
        s, err = await fetch_stats(amigo["nombre"], amigo["tag"])
        
        # EL SECRETO ESTÁ AQUÍ. Si pide muy rápido, Riot corta a partir del 3º.
        await asyncio.sleep(3) 
        
        if not err and s:
            scores.append(s)
        else:
            # Si a pesar de todo la API falla, ahora sabrás el motivo exacto entre paréntesis
            jugadores_fantasma.append(f"{amigo['nombre']}#{amigo['tag']} ({err})")

    if not scores:
        msg = "❌ No se pudieron cargar las stats de nadie."
        await interaction.followup.send(msg)
        return

    scores.sort(key=lambda x: x.get("acs") if x.get("acs") is not None else 0, reverse=True)
    embed = discord.Embed(title="🏆 Leaderboard de Colegas (Top ACS)", color=0xFFD700)
    
    for i, p in enumerate(scores):
        medalla = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else "🔹"
        
        nombre_lb = p.get('nombre') or "Jugador"
        tag_lb = p.get('tag') or ""
        main_agent = p.get('agent', 'Desconocido')
        stats_txt = f"**ACS:** {p.get('acs')} | **KDA:** {p.get('kda')} | **Rank:** {p.get('rank')}"
        embed.add_field(name=f"{medalla} {nombre_lb}#{tag_lb} ({main_agent})", value=stats_txt, inline=False)

    if jugadores_fantasma:
        nombres_rotos = "\n".join(jugadores_fantasma)
        embed.add_field(name="⚠️ Sin datos o Errores de API:", value=f"```\n{nombres_rotos}\n```", inline=False)

    await interaction.followup.send(embed=embed)

bot.run(TOKEN)