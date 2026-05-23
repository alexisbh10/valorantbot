import os
import sys
import time
from multiprocessing import Process

def run_webhook():
    print("🚀 [SISTEMA] Iniciando Webhook en proceso independiente...")
    import uvicorn
    from webhook import app
    puerto = int(os.getenv("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=puerto, log_level="info")

def run_bot():
    print("🤖 [SISTEMA] Iniciando Bot de Discord en proceso independiente...")
    # Forzamos la ejecución limpia del script original del bot
    try:
        with open("discord_bot.py", "r", encoding="utf-8") as f:
            code = f.read()
        exec(code, {"__name__": "__main__"})
    except Exception as e:
        print(f"❌ [ERROR CRÍTICO BOT]: {e}")

if __name__ == "__main__":
    print("⚙️ [SISTEMA] Cargando arquitectura multiproceso aislada...")

    # Creamos dos procesos totalmente separados a nivel de sistema operativo
    proceso_webhook = Process(target=run_webhook)
    proceso_bot = Process(target=run_bot)

    # Arrancamos ambos servicios en paralelo
    proceso_webhook.start()
    
    # Le damos 2 segundos al webhook para que abra el puerto y Render valide el deploy
    time.sleep(2)
    
    proceso_bot.start()

    # Mantenemos vivo el hilo principal para controlar que no se caigan
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("🛑 Deteniendo todos los servicios...")
        proceso_webhook.terminate()
        proceso_bot.terminate()