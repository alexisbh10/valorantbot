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

# ---------------- SAFE GET ----------------
def safe(v, default="N/A"):
    return v if v is not None else default

# ---------------- STATS ----------------
@bot.tree.command(name="stats")
async def stats(interaction, nombre: str, tag: str, region: str = "eu"):
    await interaction.response.defer()

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
            await interaction.followup.send(f"❌ Error: {data.get('error', 'desconocido')}")
            return

        s = data["stats"]

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

    except Exception as e:
        await interaction.followup.send(f"❌ Error: {str(e)}")

# ---------------- FRIENDS ----------------
friends = {}

@bot.tree.command(name="add")
async def add(interaction, nombre: str, tag: str):
    uid = interaction.user.id

    friends.setdefault(uid, [])
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
    try:
        r1 = requests.post(f"{TRACKER_URL}/tracker", json={"username": p1, "tag": t1}).json()
        r2 = requests.post(f"{TRACKER_URL}/tracker", json={"username": p2, "tag": t2}).json()

        a = r1.get("stats", {})
        b = r2.get("stats", {})

        embed = discord.Embed(title="⚔️ Compare")

        embed.add_field(
            name=safe(a.get("nombre")),
            value=f"{safe(a.get('rank'))} | {safe(a.get('rr', 0))} RR"
        )

        embed.add_field(
            name=safe(b.get("nombre")),
            value=f"{safe(b.get('rank'))} | {safe(b.get('rr', 0))} RR"
        )

        await interaction.response.send_message(embed=embed)

    except Exception as e:
        await interaction.response.send_message(f"❌ Error: {str(e)}")

# ---------------- LEADERBOARD ----------------
@bot.tree.command(name="leaderboard")
async def leaderboard(interaction):
    uid = interaction.user.id

    if uid not in friends or not friends[uid]:
        await interaction.response.send_message("Sin amigos")
        return

    scores = []

    for n, t in friends[uid]:
        try:
            r = requests.post(
                f"{TRACKER_URL}/tracker",
                json={"username": n, "tag": t}
            ).json()

            s = r.get("stats", {})
            scores.append((
                n,
                s.get("rr", 0),
                s.get("rank", "Unranked")
            ))

        except:
            continue

    scores.sort(key=lambda x: x[1], reverse=True)

    text = "\n".join([
        f"🏆 {n} - {rr} RR ({rk})"
        for n, rr, rk in scores
    ])

    await interaction.response.send_message(text)

# ---------------- RUN ----------------
bot.run(TOKEN)