import os
import sys
import threading
import time
import uvicorn

def start_webhook():
    print("🚀 [LANZADOR] Iniciando el Webhook Tracker con Uvicorn...")
    # Extraemos el puerto dinámico de Render (por defecto 10000)
    puerto = int(os.getenv("PORT", 10000))
    
    # Importamos la app de FastAPI de forma local para evitar bucles de importación
    from webhook import app
    uvicorn.run(app, host="0.0.0.0", port=puerto, log_level="info")

def start_discord_bot():
    print("🤖 [LANZADOR] Esperando 5 segundos a que el Webhook se asiente...")
    time.sleep(5)
    print("🤖 [LANZADOR] Iniciando el Bot de Discord...")
    
    # Ejecutamos el archivo del bot de Discord directamente
    try:
        with open("discord_bot.py", "r", encoding="utf-8") as f:
            code = f.read()
        exec(code, {"__name__": "__main__"})
    except Exception as e:
        print(f"❌ [ERROR EN BOT DE DISCORD]: {e}")

if __name__ == "__main__":
    print("⚙️ [LANZADOR] Preparando entorno multiproceso híbrido...")
    
    # Creamos el hilo para el Webhook (FastAPI)
    hilo_webhook = threading.Thread(target=start_webhook, daemon=True)
    
    # Creamos el hilo para el Bot de Discord
    hilo_bot = threading.Thread(target=start_discord_bot, daemon=True)
    
    # Arrancamos ambos hilos en paralelo
    hilo_webhook.start()
    hilo_bot.start()
    
    # Mantenemos el hilo principal vivo para que Render no cierre la aplicación
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("🛑 Lanzador detenido por el usuario.")