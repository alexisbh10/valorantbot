import discord
from discord.ext import commands
from discord.ext import tasks
import aiohttp
import os
import logging
import json
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
TRACKER_URL = os.getenv("TRACKER_URL", "http://localhost:8000")
FRIENDS_FILE = "amigos_valorant.json"

logging.basicConfig(level=logging.INFO)
bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())

CANAL_ALERTAS_ID = 1496835339828990078 
LAST_MATCHES_FILE = "ultimas_partidas.json"

def load_last_matches():
    if os.path.exists(LAST_MATCHES_FILE):
        with open(LAST_MATCHES_FILE, "r") as f:
            return json.load(f)
    return {}

def save_last_matches(data):
    with open(LAST_MATCHES_FILE, "w") as f:
        json.dump(data, f, indent=4)

last_matches_cache = load_last_matches()

def load_friends():
    if os.path.exists(FRIENDS_FILE):
        with open(FRIENDS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_friends(data):
    with open(FRIENDS_FILE, "w") as f:
        json.dump(data, f, indent=4)

friends = load_friends()

@bot.event
async def on_ready():
    print(f"✅ Bot listo: {bot.user}")
    await bot.tree.sync()
    if not vigilante_partidas.is_running():
        vigilante_partidas.start()

@tasks.loop(minutes=5)
async def vigilante_partidas():
    if not friends: return
    
    canal = bot.get_channel(CANAL_ALERTAS_ID)
    if not canal: return

    for server_id, friend_list in friends.items():
        for f in friend_list:
            nombre, tag = f["nombre"], f["tag"]
            s, err = await fetch_stats(nombre, tag)
            
            if err or not s or not s.get("last_match"):
                continue

            lm = s["last_match"]
            match_id = lm.get("id")
            key = f"{nombre}#{tag}"

            if match_id and last_matches_cache.get(key) != match_id:
                last_matches_cache[key] = match_id
                save_last_matches(last_matches_cache)

                if s["modo"].lower() not in ["competitive", "unrated"]:
                    continue

                k = lm["kills"]
                d = lm["deaths"]
                acs = lm["acs"]
                won = lm["won"]
                resultado = "VICTORIA" if won else "DERROTA"

                if k >= 25 or acs >= 300:
                    embed = discord.Embed(
                        title=f"🚨 ¡ALERTA DE CARREADA! 🚨",
                        description=f"**{nombre}#{tag}** acaba de destrozar el lobby en {s['mapa']}.",
                        color=0x00FF00
                    )
                    embed.add_field(name="Resultado", value=resultado, inline=True)
                    embed.add_field(name="K/D/A", value=f"{k}/{d}/{lm['assists']}", inline=True)
                    embed.add_field(name="ACS", value=str(acs), inline=True)
                    if s.get("card"): embed.set_thumbnail(url=s.get("card"))
                    await canal.send(embed=embed)

                elif d > (k + 10) or acs < 120:
                    embed = discord.Embed(
                        title=f"🗑️ ¡Tenemos un infiltrado de Hierro! 🗑️",
                        description=f"El monitor de **{nombre}#{tag}** estaba apagado en {s['mapa']}.",
                        color=0xFF0000
                    )
                    embed.add_field(name="Resultado", value=resultado, inline=True)
                    embed.add_field(name="K/D/A", value=f"{k}/{d}/{lm['assists']}", inline=True)
                    embed.add_field(name="ACS", value=str(acs), inline=True)
                    if s.get("card"): embed.set_thumbnail(url=s.get("card"))
                    await canal.send(embed=embed)

async def fetch_stats(nombre, tag, region="eu"):
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
            async with session.post(
                f"{TRACKER_URL.rstrip('/')}/tracker",
                json={"username": nombre, "tag": tag, "region": region}
            ) as r:
                data = await r.json()
                if not data.get("success"):
                    return None, data.get("error", "Error desconocido de la API")
                return data.get("stats", {}), None
    except Exception as e:
        return None, str(e)

@bot.tree.command(name="stats", description="Muestra las estadísticas de un jugador de Valorant")
async def stats(interaction: discord.Interaction, nombre: str, tag: str, region: str = "eu"):
    await interaction.response.defer()

    s, err = await fetch_stats(nombre, tag, region)

    if err or not s:
        await interaction.followup.send(f"❌ Error: {err}")
        return

    color = 0xFF4655 if not s.get("smurf") else 0x9333EA
    embed = discord.Embed(
        title=f"📊 Estadísticas de {s.get('nombre')}#{s.get('tag')}",
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
        lineups_links = []
        for agent in top_agents:
            agente_formateado = agent.lower().replace("/", "") 
            url = f"https://lineupsvalorant.com/agent/{agente_formateado}"
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
    save_friends(friends)
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
        if not err and s:
            scores.append(s)
        else:
            # AHORA EL BOT INCLUYE EL ERROR REAL QUE RECIBE DEL WEBHOOK
            jugadores_fantasma.append(f"{amigo['nombre']}#{amigo['tag']} ({err})")

    if not scores:
        msg = "❌ Nadie tiene datos recientes."
        if jugadores_fantasma:
            msg += f" \nErrores detectados:\n" + "\n".join(jugadores_fantasma)
        await interaction.followup.send(msg)
        return

    scores.sort(key=lambda x: x.get("acs") if x.get("acs") is not None else 0, reverse=True)
    embed = discord.Embed(title="🏆 Leaderboard de Colegas (Top ACS)", color=0xFFD700)
    
    for i, p in enumerate(scores):
        medalla = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else "🔹"
        main_agent = p.get('agent', 'Desconocido')
        stats_txt = f"**ACS:** {p.get('acs')} | **KDA:** {p.get('kda')} | **Rank:** {p.get('rank')}"
        embed.add_field(name=f"{medalla} {p.get('nombre')}#{p.get('tag')} ({main_agent})", value=stats_txt, inline=False)

    if jugadores_fantasma:
        nombres_rotos = " | ".join(jugadores_fantasma)
        embed.set_footer(text=f"⚠️ Errores: {nombres_rotos}")

    await interaction.followup.send(embed=embed)

bot.run(TOKEN)