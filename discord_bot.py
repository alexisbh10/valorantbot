import discord
from discord.ext import commands
import requests
import os
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
TRACKER_URL = os.getenv("TRACKER_URL", "http://localhost:8000")

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("discord_bot")

intents = discord.Intents.default()
# En producción no necesitamos message content intent para slash commands
intents.message_content = False
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    logger.info(f"✅ Bot conectado: {bot.user}")
    # Si se proporciona GUILD_ID en env, sincronizamos los comandos en ese guild
    guild_id = os.getenv("GUILD_ID")
    try:
        if guild_id:
            guild = discord.Object(id=int(guild_id))
            synced = await bot.tree.sync(guild=guild)
            logger.info(f"✅ {len(synced)} comando(s) sincronizado(s) en guild {guild_id}")
        else:
            synced = await bot.tree.sync()
            logger.info(f"✅ {len(synced)} comando(s) sincronizado(s) globalmente")
    except Exception as e:
        logger.exception(f"❌ Error sincronizando comandos: {e}")


@bot.tree.command(name="stats", description="Obtener stats de un jugador de Valorant")
async def stats(interaction: discord.Interaction, nombre: str, region: str = "EUW1"):
    """Obtiene stats: /stats Nombre NA1"""
    await interaction.response.defer()
    
    try:
        response = requests.post(
            url = f"{TRACKER_URL.rstrip('/')}/tracker",
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
        logger.error("DISCORD_TOKEN no configurada en environment")
        print("❌ DISCORD_TOKEN no configurada en environment")
    else:
        try:
            logger.info("Iniciando bot de Discord...")
            bot.run(DISCORD_TOKEN)
        except Exception as e:
            logger.exception(f"Error al ejecutar el bot: {e}")
            # asegúrate de que Railway capture el error en logs
            print(f"Error al ejecutar el bot: {e}")
