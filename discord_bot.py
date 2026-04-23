import discord
from discord.ext import commands
import requests
import os
import logging
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
TRACKER_URL = os.getenv("TRACKER_URL", "http://localhost:8000")

logging.basicConfig(level=logging.INFO)
bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())

# ---------------- READY ----------------
@bot.event
async def on_ready():
    print(f"✅ Bot listo: {bot.user}")
    await bot.tree.sync()

# ---------------- SAFE ----------------
def safe(v, default="N/A"):
    return default if v is None else v

# ---------------- REQUEST WRAPPER ----------------
def fetch_stats(nombre, tag, region="eu"):
    try:
        r = requests.post(
            f"{TRACKER_URL.rstrip('/')}/tracker",
            json={
                "username": nombre,
                "tag": tag,
                "region": region
            },
            timeout=10
        )

        data = r.json()

        if not data.get("success"):
            return None, data.get("error", "unknown error")

        return data.get("stats", {}), None

    except Exception as e:
        return None, str(e)

# ---------------- STATS (FULL TRACKER) ----------------
@bot.tree.command(name="stats")
async def stats(interaction, nombre: str, tag: str, region: str = "eu"):
    await interaction.response.defer()

    s, err = fetch_stats(nombre, tag, region)

    if err or not s:
        await interaction.followup.send(f"❌ Error: {err}")
        return

    smurf_text = "⚠️ SMURF DETECTED" if s.get("smurf") else "OK"

    embed = discord.Embed(
        title=f"{safe(s.get('nombre'))}#{safe(s.get('tag'))}",
        color=0xFF4655
    )

    # BASIC
    embed.add_field(name="🎮 Nivel", value=safe(s.get("nivel")), inline=True)
    embed.add_field(name="🏆 Rank", value=safe(s.get("rank", "Unranked")), inline=True)
    embed.add_field(name="📈 RR", value=safe(s.get("rr", 0)), inline=True)

    # LEVEL 1
    embed.add_field(name="📊 KDA", value=safe(s.get("kda", 0)), inline=True)
    embed.add_field(name="📈 Winrate", value=f"{s.get('winrate', 0)}%", inline=True)

    # LEVEL 2
    embed.add_field(name="🧠 ELO", value=safe(s.get("elo", 0)), inline=True)
    embed.add_field(name="📉 Consistencia", value=safe(s.get("consistency", 0)), inline=True)
    embed.add_field(name="📈 Tendencia", value=safe(s.get("trend", "UNKNOWN")), inline=True)

    # LEVEL 3
    embed.add_field(name="🧪 Estado", value=smurf_text, inline=False)

    # LAST MATCH
    embed.add_field(name="🗺️ Último mapa", value=safe(s.get("mapa")), inline=True)
    embed.add_field(name="🎯 Modo", value=safe(s.get("modo")), inline=True)

    await interaction.followup.send(embed=embed)

# ---------------- FRIENDS ----------------
friends = {}

@bot.tree.command(name="add")
async def add(interaction, nombre: str, tag: str):
    uid = interaction.user.id
    friends.setdefault(uid, []).append((nombre, tag))
    await interaction.response.send_message("✔ Añadido")

# ---------------- FRIENDS LIST ----------------
@bot.tree.command(name="friends")
async def friends_cmd(interaction):
    uid = interaction.user.id

    if uid not in friends or not friends[uid]:
        await interaction.response.send_message("No tienes amigos")
        return

    text = "\n".join([f"{n}#{t}" for n, t in friends[uid]])
    await interaction.response.send_message(f"👥 Amigos:\n{text}")

# ---------------- COMPARE (UPGRADED) ----------------
@bot.tree.command(name="compare")
async def compare(interaction, p1: str, t1: str, p2: str, t2: str):
    await interaction.response.defer()

    s1, e1 = fetch_stats(p1, t1)
    s2, e2 = fetch_stats(p2, t2)

    if e1 or e2 or not s1 or not s2:
        await interaction.followup.send(f"❌ Error: {e1 or e2}")
        return

    embed = discord.Embed(title="⚔️ Compare (Pro)", color=0xFF4655)

    embed.add_field(
        name=safe(s1.get("nombre")),
        value=(
            f"🏆 {s1.get('rank')} | {s1.get('rr', 0)} RR\n"
            f"📊 KDA {s1.get('kda')} | WR {s1.get('winrate')}%\n"
            f"🧠 ELO {s1.get('elo')}"
        ),
        inline=True
    )

    embed.add_field(
        name=safe(s2.get("nombre")),
        value=(
            f"🏆 {s2.get('rank')} | {s2.get('rr', 0)} RR\n"
            f"📊 KDA {s2.get('kda')} | WR {s2.get('winrate')}%\n"
            f"🧠 ELO {s2.get('elo')}"
        ),
        inline=True
    )

    await interaction.followup.send(embed=embed)

# ---------------- LEADERBOARD (PRO) ----------------
@bot.tree.command(name="leaderboard")
async def leaderboard(interaction):
    uid = interaction.user.id

    if uid not in friends or not friends[uid]:
        await interaction.response.send_message("Sin amigos")
        return

    await interaction.response.defer()

    scores = []

    for n, t in friends[uid]:
        s, err = fetch_stats(n, t)

        if err or not s:
            continue

        scores.append((
            n,
            s.get("elo", 0),
            s.get("winrate", 0),
            s.get("rank", "Unranked")
        ))

    scores.sort(key=lambda x: x[1], reverse=True)

    text = "\n".join([
        f"🏆 {n} | ELO {elo} | WR {wr}% | {rk}"
        for n, elo, wr, rk in scores
    ]) or "Sin datos"

    await interaction.followup.send(text)

# ---------------- RUN ----------------
bot.run(TOKEN)