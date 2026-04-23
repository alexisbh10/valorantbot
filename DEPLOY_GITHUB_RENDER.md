# 📤 Deploy en Render.com (Guía Completa)

## 🎯 Objetivo
Hacer que tu bot esté corriendo **24/7** en un servidor en la nube, sin necesidad de tu PC.

---

## 📋 PASO 1: Instalar Git

### Descargar e instalar
1. Ve a: https://git-scm.com/download/win
2. Descarga **Git for Windows**
3. Ejecuta el installer
4. Marca todo por defecto
5. Reinicia PowerShell

### Verificar instalación
```powershell
git --version
```

Debería mostrar: `git version 2.x.x.windows.1`

---

## 📋 PASO 2: Crear repositorio en GitHub

1. Ve a: https://github.com/new
2. Completa:
   - **Repository name:** `valorant-tracker`
   - **Description:** "Valorant Tracker Bot"
   - **Public** (importante para Render gratis)
3. Haz clic en **Create repository**
4. NO inicialices con README

---

## 📋 PASO 3: Subir código a GitHub desde PowerShell

Abre PowerShell en `C:\Users\Alexi\Documents\Tracker`:

```powershell
# Navegar a la carpeta
cd C:\Users\Alexi\Documents\Tracker

# Inicializar Git
git init

# Configurar usuario
git config --local user.name "Tu Nombre"
git config --local user.email "tu@email.com"

# Agregar archivos
git add .

# Hacer commit
git commit -m "Initial commit: Valorant Tracker Bot"

# Cambiar rama a main
git branch -M main

# Agregar repositorio remoto (reemplaza TU_USUARIO)
git remote add origin https://github.com/TU_USUARIO/valorant-tracker.git

# Subir a GitHub
git push -u origin main
```

**Si pide contraseña:**
- Usa tu **token de GitHub** en lugar de contraseña
- Obtener token: https://github.com/settings/tokens
  - Generate new token (classic)
  - Selecciona `repo`
  - Copia el token

---

## 📋 PASO 4: Crear cuenta en Render.com

1. Ve a: https://render.com
2. Haz clic en **Sign up**
3. Selecciona **Continue with GitHub**
4. Autoriza a Render

---

## 📋 PASO 5: Crear Web Service en Render

1. En tu dashboard, haz clic en **New +**
2. Selecciona **Web Service**
3. Haz clic en **Connect Account** (conectar GitHub)
4. Busca `valorant-tracker`
5. Selecciona el repositorio

### Configurar:
- **Name:** `valorant-tracker`  
- **Environment:** Python 3
- **Region:** Elige la más cercana
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `uvicorn webhook:app --host 0.0.0.0 --port $PORT`
- **Plan:** Free

7. Haz clic en **Create Web Service**

**Esperará 3-5 minutos para hacer build y deploy**

---

## 📋 PASO 6: Configurar Variables de Entorno

Una vez que el deploy termine:

1. En tu Web Service, ve a **Environment**
2. Haz clic en **Add Environment Variable**
3. Agrega:
   ```
   DISCORD_WEBHOOK_URL = https://discord.com/api/webhooks/TU_ID/TU_TOKEN
   ```
4. Haz clic en **Save**

**(El DISCORD_TOKEN lo necesitas solo si ejecutas el bot en Render también, no es necesario aquí)**

---

## 📋 PASO 7: Obtener tu URL pública

Una vez que termina el deploy:

1. Tu URL aparecerá en el dashboard
2. Algo como: `https://valorant-tracker.onrender.com`
3. **GUÁRDALA BIEN**

---

## 📋 PASO 8: Actualizar .env en tu PC

Edita tu `.env` local:

```
DISCORD_TOKEN=TU_BOT_TOKEN
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/TU_ID/TU_TOKEN
TRACKER_URL=https://valorant-tracker.onrender.com
```

---

## 🤖 PASO 9: Ejecutar el Bot en tu PC

```bash
# Instalar dependencias (primera vez)
pip install -r requirements.txt

# Ejecutar bot
python discord_bot.py
```

El bot correrá en tu PC y usará el backend que está en Render.

---

## 🔄 Cómo hacer actualizaciones

Cada vez que hagas cambios en los archivos:

```powershell
# Desde C:\Users\Alexi\Documents\Tracker
git add .
git commit -m "Tu mensaje descriptivo"
git push origin main
```

**Render automáticamente detectará los cambios y hará redeploy** ✨

---

## ✅ Resumen Arquitectura

```
┌─────────────────────────────────────────┐
│  Discord                                │
│  Tu servidor de Discord                 │
└──────────────┬──────────────────────────┘
               │ /stats comando
               ↓
┌─────────────────────────────────────────┐
│  discord_bot.py (Tu PC)                │
│  - Escucha comandos /stats              │
│  - Hace peticiones HTTP al backend      │
└──────────────┬──────────────────────────┘
               │ POST /tracker
               ↓
┌─────────────────────────────────────────┐
│  webhook.py en Render.com (24/7)       │
│  - Consulta valorant-api.com            │
│  - Envía embeds a Discord webhook       │
│  URL: https://valorant-tracker.onrender.com
└─────────────────────────────────────────┘
```

---

## 🆘 Troubleshooting

| Problema | Solución |
|----------|----------|
| "fatal: not a git repository" | Ejecuta `git init` en la carpeta correcta |
| "src refspec main does not match any" | Ejecuta `git commit` antes de push |
| Build failed en Render | Verifica `requirements.txt` está correcto |
| "Permission denied" en GitHub | Usa token en lugar de contraseña |
| Bot no responde | Verifica que `TRACKER_URL` es la URL correcta de Render |
| Error 502 en Render | El servidor se está iniciando, espera 30 segundos |

---

## 📊 Monitorear tu deploy

En el dashboard de Render:
- ✅ Status debe ser **Green** (Online)
- 📊 Puedes ver ancho de banda usado
- 📋 Logs en vivo de errores
- 🔄 Histórico de deploys

---

## 🎉 ¡Listo!

Tu tracker estará:
- ✅ Online 24/7
- ✅ Accesible desde cualquier parte del mundo
- ✅ Actualizaciones automáticas desde GitHub
- ✅ Tus colegas pueden usar `/stats PlayerName NA1` en Discord
