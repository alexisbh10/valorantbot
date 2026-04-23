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

# ---------------- STATS ----------------
@bot.tree.command(name="stats")
async def stats(interaction, nombre: str, tag: str, region: str = "eu"):
    await interaction.response.defer()

    r = requests.post(
        f"{TRACKER_URL.rstrip('/')}/tracker",
        json={
            "username": nombre,
            "tag": tag,
            "region": region
        }
    )

    data = r.json()

    if not data["success"]:
        await interaction.followup.send("❌ Error")
        return

    s = data["stats"]

    embed = discord.Embed(
        title=f"{s['nombre']}#{s['tag']}",
        color=0xFF4655
    )

    embed.add_field(name="🎮 Nivel", value=s["nivel"])
    embed.add_field(name="🏆 Rank", value=s["rank"])
    embed.add_field(name="📈 RR", value=s["rr"])
    embed.add_field(name="🗺️ Mapa", value=s["mapa"])
    embed.add_field(name="🎯 Modo", value=s["modo"])

    await interaction.followup.send(embed=embed)

# ---------------- FRIENDS ----------------
friends = {}

@bot.tree.command(name="add")
async def add(interaction, nombre: str, tag: str):
    uid = interaction.user.id

    if uid not in friends:
        friends[uid] = []

    friends[uid].append((nombre, tag))

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
    r1 = requests.post(f"{TRACKER_URL}/tracker", json={"username": p1, "tag": t1}).json()
    r2 = requests.post(f"{TRACKER_URL}/tracker", json={"username": p2, "tag": t2}).json()

    a = r1["stats"]
    b = r2["stats"]

    embed = discord.Embed(title="⚔️ Compare")

    embed.add_field(name=a["nombre"], value=f"{a['rank']} | {a['rr']} RR")
    embed.add_field(name=b["nombre"], value=f"{b['rank']} | {b['rr']} RR")

    await interaction.response.send_message(embed=embed)

# ---------------- LEADERBOARD ----------------
@bot.tree.command(name="leaderboard")
async def leaderboard(interaction):
    uid = interaction.user.id

    if uid not in friends:
        await interaction.response.send_message("Sin amigos")
        return

    scores = []

    for n, t in friends[uid]:
        r = requests.post(f"{TRACKER_URL}/tracker", json={"username": n, "tag": t}).json()
        s = r["stats"]
        scores.append((n, s["rr"], s["rank"]))

    scores.sort(key=lambda x: x[1], reverse=True)

    text = "\n".join([f"🏆 {n} - {rr} RR ({rk})" for n, rr, rk in scores])

    await interaction.response.send_message(text)

# ---------------- RUN ----------------
bot.run(TOKEN)