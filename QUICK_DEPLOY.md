# ⚡ QUICK DEPLOY - 3 pasos rápidos

## 1️⃣ Preparar GitHub (en PowerShell)

```powershell
cd C:\Users\Alexi\Documents\Tracker

git init
git config --local user.name "Tu Nombre"
git config --local user.email "tu@email.com"
git add .
git commit -m "Valorant Tracker Bot"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/valorant-tracker.git
git push -u origin main
```

## 2️⃣ Deploy en Render

### 2a. Web Service (Backend)
- https://render.com → New Web Service
- Conecta repo `valorant-tracker`
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `uvicorn webhook:app --host 0.0.0.0 --port $PORT`
- **Plan:** Free
- → Create
- Copia tu URL: `https://valorant-tracker-backend.onrender.com` (ej)

### 2b. Background Worker (Bot)
- https://render.com → New Background Worker
- Mismo repo `valorant-tracker`
- **Start Command:** `python discord_bot.py`
- **Plan:** Free
- → Create

## 3️⃣ Configurar Variables

### En Web Service Environment:
```
DISCORD_WEBHOOK_URL = https://discord.com/api/webhooks/TU_ID/TU_TOKEN
```

### En Worker Environment:
```
DISCORD_TOKEN = TU_BOT_TOKEN
TRACKER_URL = https://valorant-tracker-backend.onrender.com
```

---

## ✅ ¡Listo!

Ahora:
- `/stats PlayerName NA1` funciona en Discord
- Bot responde 24/7
- Sin tu PC encendida

Para actualizaciones:
```powershell
git add .
git commit -m "Tu cambio"
git push origin main
```

Render redeploy automático ✨
