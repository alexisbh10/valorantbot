# ⚡ START - Comienza aquí

## 📋 Estructura

```
.env                 ← Tu configuración (rellena con tus tokens)
discord_bot.py       ← Bot que ejecutas en tu PC
webhook.py           ← Backend que va en Render.com
requirements.txt     ← Dependencias
Procfile, runtime.txt ← Para Render
README.md            ← Documentación
```

---

## 🔧 Paso 1: Configurar .env

Abre `.env` y reemplaza:

```
DISCORD_TOKEN=TU_BOT_TOKEN
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/TU_ID/TU_TOKEN
TRACKER_URL=http://localhost:8000
```

**¿Dónde obtenerlos?**
- **DISCORD_TOKEN:** https://discord.com/developers/applications → Tu App → Bot → Copy Token
- **DISCORD_WEBHOOK_URL:** Discord Server → Settings → Integrations → Webhooks → Create Webhook → Copy URL
- **TRACKER_URL:** Cuando depliegues en Render (ej: `https://valorant-tracker.onrender.com`)

---

## 🚀 Paso 2: Deploy del Backend

### 📤 Ver guía completa de Deploy

**[DEPLOY_GITHUB_RENDER.md](DEPLOY_GITHUB_RENDER.md)** - Guía paso-a-paso de:
- ✅ Instalar Git
- ✅ Subir código a GitHub  
- ✅ Deploy automático en Render.com
- ✅ Configurar variables de entorno
- ✅ Obtener tu URL pública
- ✅ Actualizar `.env` con TRACKER_URL

**Después de completar esa guía, continúa con el Paso 3 abajo.**

---

## 🤖 Paso 3: Ejecutar el Bot

```bash
# Instalar dependencias
pip install -r requirements.txt

# Ejecutar bot
python discord_bot.py
```

---

## 💬 Usar en Discord

Escribe en cualquier canal:
```
/stats PlayerName NA1
/regiones
```

El bot responde con las stats 🎉

---

## ✅ Checklist

- [ ] `.env` configurado con tus tokens
- [ ] Git instalado
- [ ] Código subido a GitHub
- [ ] Backend deployado en Render
- [ ] `TRACKER_URL` actualizado en `.env` con tu URL de Render
- [ ] Bot ejecutándose (`python discord_bot.py`)
- [ ] Comando `/stats` funciona en Discord

¡Listo!
