# 🚀 Deploy en Render.com - TODO en la nube (Bot + Backend 24/7)

## 🎯 Objetivo
Tu tracker corre **siempre online** en Render.com sin necesidad de una PC propia.

---

## 📊 Arquitectura

```
            Discord Server
                  ↓
                  │
        Discord Bot (Worker en Render)
                  │
                  ↓
    Recibe /stats → Hace petición HTTP
                  │
                  ↓
    Backend FastAPI (Web Service en Render)
                  │
                  ↓
        valorant-api.com
                  │
                  ↓
    Envía embed a Discord Webhook
```

---

## 📋 PASO 1: Instalar Git

### Descargar e instalar
1. Ve a: https://git-scm.com/download/win
2. Ejecuta el installer
3. Marca todo por defecto
4. Reinicia PowerShell

### Verificar
```powershell
git --version
```

---

## 📋 PASO 2: Crear repositorio en GitHub

1. Ve a: https://github.com/new
2. Completa:
   - **Repository name:** `valorant-tracker`
   - **Description:** "Valorant Tracker Bot 24/7"
   - **Public** ← IMPORTANTE para Render gratis
3. **NO** inicialices con README
4. Clic en **Create repository**

---

## 📋 PASO 3: Subir código a GitHub

En PowerShell, navega a `C:\Users\Alexi\Documents\Tracker`:

```powershell
cd C:\Users\Alexi\Documents\Tracker

# Inicializar Git
git init

# Configurar usuario
git config --local user.name "Tu Nombre"
git config --local user.email "tu@email.com"

# Agregar todos los archivos
git add .

# Hacer commit
git commit -m "Valorant Tracker - Bot 24/7"

# Cambiar rama a main
git branch -M main

# REEMPLAZA TU_USUARIO por tu usuario de GitHub
git remote add origin https://github.com/TU_USUARIO/valorant-tracker.git

# Subir a GitHub
git push -u origin main
```

**Si pide contraseña:** Usa tu token de GitHub
- Ve a: https://github.com/settings/tokens → Generate new token (classic) → Selecciona `repo` → Copia token

---

## 📋 PASO 4: Configurar `.env` para Render

Edita tu `.env`:

```
DISCORD_TOKEN=TU_BOT_TOKEN_AQUI
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/TU_ID/TU_TOKEN
TRACKER_URL=http://localhost:8000
```

**Esto es temporal.** Una vez que desplegues, actualiza TRACKER_URL con la URL de tu Web Service.

---

## 📋 PASO 5: Crear cuenta en Render.com

1. Ve a: https://render.com
2. Clic en **Sign up**
3. **Continue with GitHub**
4. Autoriza a Render

---

## 📋 PASO 6: Crear Web Service (Backend)

1. Dashboard de Render → **New +** → **Web Service**
2. Clic en **Connect Account** (conectar GitHub)
3. Busca `valorant-tracker` y selecciona
4. Completa:
   - **Name:** `valorant-tracker-backend`
   - **Environment:** Python 3
   - **Region:** Tu región más cercana
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn webhook:app --host 0.0.0.0 --port $PORT`
   - **Plan:** Free

5. Clic en **Create Web Service**

**Espera 3-5 minutos a que termine el build**

---

## 📋 PASO 7: Copiar URL del Web Service

Una vez que termina:
1. Tu URL aparecerá en el dashboard
2. Algo como: `https://valorant-tracker-backend.onrender.com`
3. **CÓPIALA**

---

## 📋 PASO 8: Crear Background Worker (Discord Bot)

En el dashboard de Render:
1. **New +** → **Background Worker**
2. Conecta el **mismo repositorio** `valorant-tracker`
3. Completa:
   - **Name:** `valorant-tracker-bot`
   - **Environment:** Python 3
   - **Start Command:** `python discord_bot.py`
   - **Plan:** Free

4. Clic en **Create Background Worker**

---

## 📋 PASO 9: Configurar Variables de Entorno

**En el Web Service (`valorant-tracker-backend`):**
1. Ve a **Environment**
2. Agrega:
   ```
   DISCORD_WEBHOOK_URL = https://discord.com/api/webhooks/TU_ID/TU_TOKEN
   ```

**En el Background Worker (`valorant-tracker-bot`):**
1. Ve a **Environment**
2. Agrega:
   ```
   DISCORD_TOKEN = TU_BOT_TOKEN
   TRACKER_URL = https://valorant-tracker-backend.onrender.com
   ```

---

## 📋 PASO 10: Actualizar `.env` local (tu PC)

En `C:\Users\Alexi\Documents\Tracker\.env`:

```
DISCORD_TOKEN=TU_BOT_TOKEN
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/TU_ID/TU_TOKEN
TRACKER_URL=https://valorant-tracker-backend.onrender.com
```

Luego sube a GitHub:
```powershell
git add .env
git commit -m "Update TRACKER_URL for Render"
git push origin main
```

Render automáticamente hará redeploy con las nuevas variables.

---

## ✅ Verificar Deploy

### Web Service
- URL: `https://valorant-tracker-backend.onrender.com/health`
- Debería responder: `{"status":"ok"}`

### Background Worker
- Ve a logs en Render
- Debería mostrar: `✅ Bot conectado: NombreDelBot`

---

## 🎉 ¡Todo Corriendo!

Ahora:
- ✅ Backend online 24/7 en `https://valorant-tracker-backend.onrender.com`
- ✅ Bot Discord corriendo 24/7 en Background Worker
- ✅ Tus colegas pueden usar `/stats PlayerName NA1` en cualquier momento
- ✅ No necesitas tu PC encendida

---

## 🔄 Cómo hacer actualizaciones

Cualquier cambio en los archivos:

```powershell
git add .
git commit -m "Tu mensaje"
git push origin main
```

Render automáticamente detecta los cambios y hace redeploy de ambos servicios ✨

---

## 🆘 Troubleshooting

| Problema | Solución |
|----------|----------|
| Bot no responde a comandos | Verifica logs del Worker en Render |
| Error 502 en Web Service | Espera 30 segundos, el servidor se está iniciando |
| "Build failed" | Revisa que `requirements.txt` está correcto |
| Bot se reinicia constantemente | Verifica TRACKER_URL y DISCORD_TOKEN en Environment |
| `/stats` no funciona | Asegúrate que TRACKER_URL apunta a la URL del Web Service |

---

## 💡 Monitorea tu deploy

En el dashboard de Render:

**Web Service:**
- ✅ Status debe ser **Green** (Online)
- 📊 Ancho de banda usado
- 📋 Logs en vivo

**Background Worker:**
- 📋 Logs en vivo (ver si bot está conectado)
- 🔄 Histórico de restarts

---

## 📝 Resumen URLs

- **Web Service:** `https://valorant-tracker-backend.onrender.com`
- **Bot:** Corriendo 24/7 en el Worker (sin URL pública)
- **Health Check:** `https://valorant-tracker-backend.onrender.com/health`

---

## 🎊 ¡Listo!

Tu Valorant Tracker está **completamente en la nube**, sin necesidad de ejecutar nada en tu PC. Tus colegas pueden usar el bot en cualquier momento del día, y el servidor responderá desde Render.com.

Para tus colegas:
```
/stats aceu NA1
/stats SomePlayer EUW1
/regiones
```

¡Y funciona 24/7! 🚀
