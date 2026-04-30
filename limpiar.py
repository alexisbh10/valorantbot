import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def limpiar():
    conn = await asyncpg.connect(os.getenv("DATABASE_URL"))
    # Vaciamos la tabla de partidas de un plumazo
    await conn.execute("TRUNCATE TABLE partidas;")
    print("✅ Base de datos limpia y lista para la nueva temporada!")
    await conn.close()

asyncio.run(limpiar())