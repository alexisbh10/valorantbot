import discord
from discord.ext import commands
import requests
import os
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
TRACKER_URL = os.getenv("TRACKER_URL", "http://localhost:8000")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"✅ Bot conectado: {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"✅ {len(synced)} comando(s) sincronizado(s)")
    except Exception as e:
        print(f"❌ Error: {e}")


@bot.tree.command(name="stats", description="Obtener stats de un jugador de Valorant")
async def stats(interaction: discord.Interaction, nombre: str, region: str = "NA1"):
    """Obtiene stats: /stats Nombre NA1"""
    await interaction.response.defer()
    
    try:
        response = requests.post(
            f"{TRACKER_URL}/tracker",
            json={"username": nombre, "tag": region, "discord_user_id": str(interaction.user.id)},
            timeout=10
        )
        
        if response.status_code == 200 and response.json().get("success"):
            embed = discord.Embed(
                title="✅ Stats Obtenidas",
                description="Datos enviados al canal",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send(f"❌ Error: {response.json().get('error', 'Error desconocido')}")
    
    except requests.exceptions.Timeout:
        await interaction.followup.send("❌ Timeout - intenta de nuevo")
    except requests.exceptions.ConnectionError:
        await interaction.followup.send(f"❌ No conexión a {TRACKER_URL}")
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {str(e)}")


@bot.tree.command(name="regiones", description="Ver regiones disponibles")
async def regiones(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🌍 Regiones de Valorant",
        description="• NA1 - Norteamérica\n• EUW1 - Europa Occ.\n• LATAM - Lat.americana\n• BRA1 - Brasil\n• AP1 - APAC\n• KR - Corea",
        color=discord.Color.blue()
    )
    await interaction.response.send_message(embed=embed)


if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("❌ DISCORD_TOKEN no configurada en .env")
    else:
        bot.run(DISCORD_TOKEN)
