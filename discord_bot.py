import discord
from discord.ext import commands
from discord.ext import tasks
import requests
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

# PON AQUÍ EL ID DEL CANAL DONDE EL BOT MANDARÁ LAS ALERTAS
# (Click derecho en el canal de texto de tu Discord -> Copiar ID de canal)
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

# ---------------- PERSISTENCIA (GUARDAR AMIGOS) ----------------
def load_friends():
    if os.path.exists(FRIENDS_FILE):
        with open(FRIENDS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_friends(data):
    with open(FRIENDS_FILE, "w") as f:
        json.dump(data, f, indent=4)

friends = load_friends()

# ---------------- READY ----------------
# ---------------- READY & BACKGROUND TASK ----------------
@bot.event
async def on_ready():
    print(f"✅ Bot listo: {bot.user}")
    await bot.tree.sync()
    if not vigilante_partidas.is_running():
        vigilante_partidas.start()

@tasks.loop(minutes=5) # Revisa cada 5 minutos
async def vigilante_partidas():
    if not friends: return
    
    canal = bot.get_channel(CANAL_ALERTAS_ID)
    if not canal: return

    for server_id, friend_list in friends.items():
        for f in friend_list:
            nombre, tag = f["nombre"], f["tag"]
            s, err = fetch_stats(nombre, tag)
            
            if err or not s or not s.get("last_match"):
                continue

            lm = s["last_match"]
            match_id = lm.get("id")
            key = f"{nombre}#{tag}"

            # Si es una partida nueva que no habíamos registrado
            if match_id and last_matches_cache.get(key) != match_id:
                last_matches_cache[key] = match_id
                save_last_matches(last_matches_cache)

                # Ignoramos Deathmatch u otros modos para las alertas si queremos, 
                # o verificamos si la partida es digna de mención.
                if s["modo"].lower() not in ["competitive", "unrated"]:
                    continue

                k = lm["kills"]
                d = lm["deaths"]
                acs = lm["acs"]
                won = lm["won"]
                resultado = "VICTORIA" if won else "DERROTA"

                # ALERTA DE CARREADA (Jugó increíble)
                if k >= 25 or acs >= 300:
                    embed = discord.Embed(
                        title=f"🚨 ¡ALERTA DE CARREADA! 🚨",
                        description=f"**{nombre}#{tag}** acaba de destrozar el lobby en {s['mapa']}.",
                        color=0x00FF00 # Verde
                    )
                    embed.add_field(name="Resultado", value=resultado, inline=True)
                    embed.add_field(name="K/D/A", value=f"{k}/{d}/{lm['assists']}", inline=True)
                    embed.add_field(name="ACS", value=str(acs), inline=True)
                    if s.get("card"): embed.set_thumbnail(url=s.get("card"))
                    await canal.send(embed=embed)

                # ALERTA DE BOT (Jugó fatal)
                elif d > (k + 10) or acs < 120:
                    embed = discord.Embed(
                        title=f"🗑️ ¡Tenemos un infiltrado de Hierro! 🗑️",
                        description=f"El monitor de **{nombre}#{tag}** estaba apagado en {s['mapa']}.",
                        color=0xFF0000 # Rojo
                    )
                    embed.add_field(name="Resultado", value=resultado, inline=True)
                    embed.add_field(name="K/D/A", value=f"{k}/{d}/{lm['assists']}", inline=True)
                    embed.add_field(name="ACS", value=str(acs), inline=True)
                    if s.get("card"): embed.set_thumbnail(url=s.get("card"))
                    await canal.send(embed=embed)

# ---------------- REQUEST WRAPPER ----------------
def fetch_stats(nombre, tag, region="eu"):
    try:
        r = requests.post(
            f"{TRACKER_URL.rstrip('/')}/tracker",
            json={"username": nombre, "tag": tag, "region": region},
            timeout=15
        )
        data = r.json()
        if not data.get("success"):
            return None, data.get("error", "Error desconocido de la API")
        return data.get("stats", {}), None
    except Exception as e:
        return None, str(e)

# ---------------- STATS COMMAND ----------------
@bot.tree.command(name="stats", description="Muestra las estadísticas de un jugador de Valorant")
async def stats(interaction: discord.Interaction, nombre: str, tag: str, region: str = "eu"):
    await interaction.response.defer()

    s, err = fetch_stats(nombre, tag, region)

    if err or not s:
        await interaction.followup.send(f"❌ Error: {err}")
        return

    # Diseño Premium del Embed
    color = 0xFF4655 if not s.get("smurf") else 0x9333EA # Morado si es smurf
    embed = discord.Embed(
        title=f"📊 Estadísticas de {s.get('nombre')}#{s.get('tag')}",
        description=f"Nivel {s.get('nivel')} | **Últimas 10 partidas**",
        color=color
    )

    if s.get("card"):
        embed.set_thumbnail(url=s.get("card"))

    # Fila 1: Rango
    embed.add_field(name="🏆 Rango", value=f"**{s.get('rank')}** ({s.get('rr')} RR)", inline=True)
    embed.add_field(name="📈 Winrate", value=f"**{s.get('winrate')}%**", inline=True)
    embed.add_field(name="📊 Tendencia", value=f"**{s.get('trend')}**", inline=True)

    # Fila 2: Tiroteo
    embed.add_field(name="⚔️ ACS (Combate)", value=str(s.get('acs')), inline=True)
    embed.add_field(name="🎯 KDA", value=str(s.get('kda')), inline=True)
    embed.add_field(name="💥 Headshot", value=f"{s.get('hs')}%", inline=True)

    # Footer
    estado = "⚠️ ALERTA DE SMURF / CARREADITO" if s.get("smurf") else "✅ Jugador Legal"
    embed.set_footer(text=f"Última partida: {s.get('modo')} en {s.get('mapa')} • {estado}")

    await interaction.followup.send(embed=embed)

# ---------------- AÑADIR AMIGO ----------------
@bot.tree.command(name="add", description="Guarda a un colega en la lista del servidor")
async def add(interaction: discord.Interaction, nombre: str, tag: str):
    server_id = str(interaction.guild_id)
    if server_id not in friends:
        friends[server_id] = []
    
    # Evitar duplicados
    if any(f["nombre"].lower() == nombre.lower() and f["tag"].lower() == tag.lower() for f in friends[server_id]):
        await interaction.response.send_message(f"⚠️ {nombre}#{tag} ya está en la lista.")
        return

    friends[server_id].append({"nombre": nombre, "tag": tag})
    save_friends(friends)
    await interaction.response.send_message(f"✅ Añadido a la lista: **{nombre}#{tag}**")

# ---------------- LEADERBOARD ----------------
@bot.tree.command(name="leaderboard", description="Ranking de los colegas del servidor")
async def leaderboard(interaction: discord.Interaction):
    server_id = str(interaction.guild_id)

    if server_id not in friends or not friends[server_id]:
        await interaction.response.send_message("❌ No hay nadie en la lista. Usad `/add` primero.")
        return

    await interaction.response.defer()
    scores = []

    for amigo in friends[server_id]:
        s, err = fetch_stats(amigo["nombre"], amigo["tag"])
        if not err and s:
            scores.append(s)

    if not scores:
        await interaction.followup.send("❌ No se pudieron cargar las stats de nadie.")
        return

    # Ordenar por ACS (Puntuación media de combate) de mayor a menor
    scores.sort(key=lambda x: float(x.get("acs", 0)), reverse=True)

    embed = discord.Embed(title="🏆 Leaderboard de Colegas (Top ACS)", color=0xFFD700)
    
    for i, p in enumerate(scores):
        medalla = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else "🔹"
        stats_txt = f"**ACS:** {p.get('acs')} | **KDA:** {p.get('kda')} | **Rank:** {p.get('rank')}"
        embed.add_field(name=f"{medalla} {p.get('nombre')}#{p.get('tag')}", value=stats_txt, inline=False)

    await interaction.followup.send(embed=embed)

# ---------------- RUN ----------------
bot.run(TOKEN)