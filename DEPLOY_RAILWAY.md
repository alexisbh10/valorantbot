# 🚀 Deploy en Railway.app - TODO Gratis y 24/7

## 🎯 Por qué Railway?

- ✅ $5 USD mensuales GRATIS (suficiente para 2 servicios)
- ✅ Almacenamiento no consumido en créditos
- ✅ Uptime 24/7 garantizado
- ✅ Soporte para múltiples servicios
- ✅ Deploy automático desde GitHub
- ✅ Simple y rápido

---

## 📊 Arquitectura Final

```
            Discord
                ↓
        Discord Bot (Cron Worker)
                ↓
    Petición HTTP a Backend
                ↓
    FastAPI Backend (Web Service)
                ↓
        valorant-api.com
                ↓
    Envía embed a Discord Webhook
```

---

## 📋 PASO 1: Preparar GitHub

### 1.1 Crear repositorio
1. Ve a: https://github.com/new
2. **Repository name:** `valorant-tracker`
3. **Public** ← importante para Railway gratis
4. **Create repository**

### 1.2 Subir código a GitHub

En PowerShell en `C:\Users\Alexi\Documents\Tracker`:

```powershell
git init
git config --local user.name "Tu Nombre"
git config --local user.email "tu@email.com"
git add .
git commit -m "Valorant Tracker Bot"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/valorant-tracker.git
git push -u origin main
```

---

## 📋 PASO 2: Crear cuenta en Railway

1. Ve a: https://railway.app
2. **Sign up** → **GitHub**
3. Autoriza Railway

---

## 📋 PASO 3: Crear Web Service (Backend)

### 3.1 Crear servicio desde GitHub
1. Dashboard de Railway → **New Project**
2. **Deploy from GitHub repo**
3. Selecciona `valorant-tracker`
4. Autoriza si es necesario
5. Railway auto-detecta Python
6. Espera a que termine build (3-5 min)

### 3.2 Configurar Start Command
1. Haz clic en el servicio
2. Ve a **Settings** → **Start Command**
3. Reemplaza con:
   ```
   uvicorn webhook:app --host 0.0.0.0 --port $PORT
   ```

### 3.3 Copiar URL
1. En el servicio, busca **Railway Provided Domain**
2. Algo como: `https://valorant-tracker-backend-prod.up.railway.app`
3. **GUÁRDALA**

---

## 📋 PASO 4: Crear Cron Worker (Bot Discord)

### 4.1 Agregar nuevo servicio
1. Dashboard → Tu proyecto → **+ Add Service**
2. **GitHub Repo** → Selecciona de nuevo `valorant-tracker`
3. Marca **Is Cron Job**
4. **Add Service**

### 4.2 Configurar Cron Job
1. Haz clic en el servicio
2. Ve a **Settings**
3. **Service Name:** `discord-bot`
4. **Cron Schedule:** `* * * * *` (cada minuto)
5. **Commit SHA:** Usa `main` branch

### 4.3 Configurar Start Command
1. Ve a **Settings** → **Start Command**
2. Ingresa:
   ```
   python discord_bot.py
   ```

---

## 📋 PASO 5: Configurar Variables de Entorno

### 5.1 En el Web Service (Backend)
1. Haz clic en el servicio Backend
2. Ve a **Variables**
3. Agrega:
   ```
   DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/TU_ID/TU_TOKEN
   ```

### 5.2 En el Cron Worker (Bot)
1. Haz clic en el servicio Bot
2. Ve a **Variables**
3. Agrega:
   ```
   DISCORD_TOKEN=TU_BOT_TOKEN
   TRACKER_URL=https://valorant-tracker-backend-prod.up.railway.app
   PORT=8000
   ```

---

## 📋 PASO 6: Actualizar `.env` Local

En `C:\Users\Alexi\Documents\Tracker\.env`:

```
DISCORD_TOKEN=TU_BOT_TOKEN
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/TU_ID/TU_TOKEN
TRACKER_URL=https://valorant-tracker-backend-prod.up.railway.app
```

Luego sube:
```powershell
git add .env
git commit -m "Update TRACKER_URL"
git push origin main
```

Railway automáticamente hace redeploy.

---

## ✅ Verificar Deploy

### Backend
```
https://valorant-tracker-backend-prod.up.railway.app/health
```
Debería responder: `{"status":"ok"}`

### Bot
- Ve a Railway Dashboard → Bot service → **Logs**
- Debería mostrar: `✅ Bot conectado: TuBotName`

---

## 💬 Usar en Discord

Una vez todo esté corriendo:

```
/stats PlayerName NA1      ← ✅ Funciona
/regiones                  ← ✅ Funciona
```

---

## 🔄 Actualizaciones

Cualquier cambio en los archivos:

```powershell
git add .
git commit -m "Tu cambio"
git push origin main
```

Railway automáticamente detecta y redeploy ✨

---

## 📊 Monitorear en Railway

**Dashboard:**
- ✅ Status de servicios (Green = Online)
- 📊 Uso de créditos (aprox $0.50-1.00 por mes)
- 📋 Logs en vivo
- ⚙️ Historia de deploys

---

## 🆘 Troubleshooting

| Problema | Solución |
|----------|----------|
| Bot no responde | Verifica logs en Railway |
| `TRACKER_URL` error | Usar URL completa de Railway con `/health` |
| "Build failed" | Revisa `requirements.txt` |
| Créditos se agotan | Reducer frecuencia de cron o upgrade plan |

---

## 💰 Costos

- Backend: ~$0.30-0.50/mes
- Bot (Cron): ~$0.10-0.20/mes
- **Total: < $1/mes dentro de $5 gratis**

---

## 🎉 ¡Todo Funcionando!

Tu tracker:
- ✅ Backend corriendo 24/7
- ✅ Bot coriendo cada minuto (responde al instante)
- ✅ Completamente gratis
- ✅ Automático desde GitHub
- ✅ Tus colegas pueden usar `/stats PlayerName NA1` siempre
