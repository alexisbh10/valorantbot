import requests
import os
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from typing import Optional
from datetime import datetime

DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK_URL", "")
HENRIK_API_KEY = os.getenv("HENRIK_API_KEY")

app = FastAPI()


def obtener_stats(username: str, tag: str) -> dict:
    """Obtiene stats del jugador desde valorant-api.com"""
    try:
        headers = {
            "Authorization": HENRIK_API_KEY
        }

        response = requests.get(
            f"https://api.henrikdev.xyz/valorant/v1/account/{username}/{tag}",
            headers=headers,
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        
        if not data.get("data"):
            raise ValueError(f"Jugador no encontrado: {username}#{tag}")
        
        player = data["data"]
        return {
            "nombre": player.get("name", "N/A"),
            "tag": player.get("tag", "N/A"),
            "nivel": player.get("account_level", "N/A"),
            "ultima_actualizacion": player.get("last_update", "N/A")
        }
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Error API Valorant: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


def crear_embed(stats: dict) -> dict:
    """Crea un embed de Discord con las stats"""
    return {
        "title": f"📊 Estadísticas de {stats['nombre']}",
        "description": f"Tag: `{stats['tag']}`",
        "color": 16711680,
        "fields": [
            {
                "name": "🎮 Nivel de Cuenta",
                "value": str(stats['nivel']),
                "inline": True
            },
            {
                "name": "🔄 Última Actualización",
                "value": stats['ultima_actualizacion'] or "N/A",
                "inline": True
            }
        ],
        "timestamp": datetime.utcnow().isoformat(),
        "footer": {"text": "Valorant Tracker"}
    }


def enviar_discord(embed: dict, user_id: Optional[str] = None) -> bool:
    """Envía el embed a Discord"""
    if not DISCORD_WEBHOOK:
        return False
    
    try:
        payload = {
            "embeds": [embed],
            "username": "Valorant Tracker"
        }
        if user_id:
            payload["content"] = f"<@{user_id}>"
        
        response = requests.post(DISCORD_WEBHOOK, json=payload, timeout=10)
        response.raise_for_status()
        return True
    except Exception:
        return False


@app.post("tracker")
async def tracker(request: Request):
    """Obtiene stats de Valorant y las envía a Discord
    
    JSON esperado:
    {
        "username": "nombre",
        "tag": "NA1",
        "discord_user_id": "123..." (opcional)
    }
    """
    try:
        body = await request.json()
        username = body.get("username")
        tag = body.get("tag")
        user_id = body.get("discord_user_id")
        
        if not username or not tag:
            raise HTTPException(status_code=400, detail="username y tag requeridos")
        
        stats = obtener_stats(username, tag)
        embed = crear_embed(stats)
        enviado = enviar_discord(embed, user_id)
        
        return {
            "success": True,
            "stats": stats,
            "discord_enviado": enviado
        }
    except HTTPException as e:
        return JSONResponse(
            status_code=e.status_code,
            content={"success": False, "error": e.detail}
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

