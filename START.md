# ⚡ START - Guía Principal

## 🎯 Objetivo

Tu Valorant Tracker Bot corriendo **24/7 en Render.com**, sin tu PC.

---

## 📦 Qué incluye

```
webhook.py           ← Backend FastAPI (Web Service en Render)
discord_bot.py       ← Bot Discord (Background Worker en Render)
requirements.txt     ← Dependencias Python
Procfile             ← Configuración Render (2 servicios)
.env                 ← Tu configuración
README.md            ← Documentación
```

---

## 🚀 Deploy en Render (TODO en la nube)

### 📖 Sigue esta guía paso-a-paso:

**[DEPLOY_RENDER_FULL.md](DEPLOY_RENDER_FULL.md)**

Incluye:
- ✅ Instalar Git
- ✅ Crear repositorio en GitHub
- ✅ Subir código
- ✅ Crear Web Service (Backend)
- ✅ Crear Background Worker (Bot)
- ✅ Configurar variables de entorno
- ✅ Verificar que todo funciona

---

## 🔑 Obtener tus Tokens

Antes de empezar, consigue:

### 1. DISCORD_TOKEN
- Ve a: https://discord.com/developers/applications
- Crea una app o selecciona la existente
- Tab **Bot** → **Copy Token**

### 2. DISCORD_WEBHOOK_URL
- Tu servidor Discord → Configuración
- **Integraciones** → **Webhooks**
- **Crear Webhook** → **Copiar URL**

---

## 💬 Usar el Bot (Una vez deployado)

En Discord:
```
/stats PlayerName NA1
/stats otro_jugador EUW1
/regiones
```

El bot responde **instantáneamente** desde cualquier parte del mundo 🌍

---

## ✅ Checklist Final

- [ ] Tokens obtenidos (DISCORD_TOKEN, DISCORD_WEBHOOK_URL)
- [ ] Git instalado
- [ ] Código en GitHub
- [ ] Web Service en Render (Backend)
- [ ] Background Worker en Render (Bot)
- [ ] Variables de entorno configuradas
- [ ] `/stats` funciona en Discord

¡Listo! Todo corriendo 24/7 ✨
