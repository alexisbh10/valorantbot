import subprocess
import sys
import os
import time

def run_services():
    print("🚀 Arrancando el Webhook Tracker...")
    # Arranca webhook.py en segundo plano (asumiendo que usa uvicorn o fastapi)
    # Cambia el comando si tu webhook se arranca de otra forma (ej: "python webhook.py")
    webhook_process = subprocess.Popen([sys.executable, "webhook.py"])
    
    # Le damos 3 segundos para que el webhook se asiente en su puerto
    time.sleep(3)
    
    print("🤖 Arrancando el Bot de Discord...")
    # Arranca el bot de Discord en el hilo principal
    bot_process = subprocess.Popen([sys.executable, "discord_bot.py"])
    
    # Mantener el script vivo mientras los subprocesos funcionen
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        webhook_process.terminate()
        bot_process.terminate()

if __name__ == "__main__":
    run_services()