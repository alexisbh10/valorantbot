import asyncio
import asyncpg
import os
from dotenv import load_dotenv

# Cargamos las variables del .env
load_dotenv()

async def crear_tablas():
    # Nos conectamos a la URL de Railway
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("❌ Error: No se encontró DATABASE_URL en el archivo .env")
        return

    print("🔄 Conectando a PostgreSQL en Railway...")
    conn = await asyncpg.connect(db_url)
    
    print("🛠️ Creando tablas...")
    
    # Ejecutamos el código SQL
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS jugadores (
            id SERIAL PRIMARY KEY,
            server_id VARCHAR(50) NOT NULL,
            nombre VARCHAR(50) NOT NULL,
            tag VARCHAR(10) NOT NULL,
            UNIQUE (server_id, nombre, tag)
        );

        CREATE TABLE IF NOT EXISTS partidas (
            match_id VARCHAR(100) NOT NULL,
            jugador_nombre VARCHAR(50) NOT NULL,
            jugador_tag VARCHAR(10) NOT NULL,
            kills INTEGER,
            deaths INTEGER,
            assists INTEGER,
            acs INTEGER,
            won BOOLEAN,
            mapa VARCHAR(50),
            modo VARCHAR(50),
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (match_id, jugador_nombre, jugador_tag)
        );
    """)
    
    print("✅ ¡Tablas creadas con éxito!")
    await conn.close()

# Ejecutamos la función asíncrona
asyncio.run(crear_tablas())