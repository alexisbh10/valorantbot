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

# ---------------- STATS ----------------
@bot.tree.command(name="stats")
async def stats(interaction, nombre: str, tag: str, region: str = "eu"):
    await interaction.response.defer()

    s, err = fetch_stats(nombre, tag, region)

    if err:
        await interaction.followup.send(f"❌ Error: {err}")
        return

    embed = discord.Embed(
        title=f"{safe(s.get('nombre'))}#{safe(s.get('tag'))}",
        color=0xFF4655
    )

    embed.add_field(name="🎮 Nivel", value=safe(s.get("nivel")), inline=True)
    embed.add_field(name="🏆 Rank", value=safe(s.get("rank", "Unranked")), inline=True)
    embed.add_field(name="📈 RR", value=safe(s.get("rr", 0)), inline=True)
    embed.add_field(name="🗺️ Mapa", value=safe(s.get("mapa")), inline=True)
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

# ---------------- COMPARE ----------------
@bot.tree.command(name="compare")
async def compare(interaction, p1: str, t1: str, p2: str, t2: str):
    await interaction.response.defer()

    s1, e1 = fetch_stats(p1, t1)
    s2, e2 = fetch_stats(p2, t2)

    if e1 or e2:
        await interaction.followup.send(f"❌ Error: {e1 or e2}")
        return

    embed = discord.Embed(title="⚔️ Compare", color=0xFF4655)

    embed.add_field(
        name=safe(s1.get("nombre")),
        value=f"{safe(s1.get('rank'))} | {safe(s1.get('rr', 0))} RR",
        inline=True
    )

    embed.add_field(
        name=safe(s2.get("nombre")),
        value=f"{safe(s2.get('rank'))} | {safe(s2.get('rr', 0))} RR",
        inline=True
    )

    await interaction.followup.send(embed=embed)

# ---------------- LEADERBOARD ----------------
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
            s.get("rr", 0),
            s.get("rank", "Unranked")
        ))

    scores.sort(key=lambda x: x[1], reverse=True)

    text = "\n".join([
        f"🏆 {n} - {rr} RR ({rk})"
        for n, rr, rk in scores
    ]) or "Sin datos"

    await interaction.followup.send(text)

# ---------------- RUN ----------------
bot.run(TOKEN)