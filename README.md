# 🎮 Valorant Tracker Bot 24/7

Bot de Discord para obtener estadísticas de jugadores de Valorant, corriendo siempre en la nube.

## 🚀 Comienza Aquí

### 📖 Guías Principales

1. **[START.md](START.md)** - Guía rápida para empezar
2. **[DEPLOY_RENDER_FULL.md](DEPLOY_RENDER_FULL.md)** - Deploy completo (Bot + Backend en Render)

## 🎯 Con este tracker obtienes:

- ✅ Bot Discord corriendo 24/7
- ✅ Backend corriendo 24/7
- ✅ Sin necesidad de tu PC encendida
- ✅ HTTPS automático
- ✅ Actualizaciones automáticas desde GitHub

## 💬 Comandos Discord

```
/stats PlayerName NA1       ← Obtener stats de un jugador
/regiones                   ← Ver regiones disponibles
```

## 🌍 Regiones Soportadas

| Código | Región |
|--------|--------|
| NA1 | Norteamérica |
| EUW1 | Europa Occidental |
| LATAM | América Latina |
| BRA1 | Brasil |
| AP1 | APAC |
| KR | Corea |

## 📊 Datos que devuelve

El bot muestra:
- 👤 Nombre del jugador
- 🏷️ Tag (región)
- 🎮 Nivel de cuenta
- 🔄 Última actualización

## 📁 Estructura del Proyecto

```
webhook.py           ← Backend FastAPI
discord_bot.py       ← Bot de Discord
requirements.txt     ← Dependencias
Procfile             ← Config Render (Web Service + Worker)
.env                 ← Variables de entorno
```

## 🔗 API Backend

**Endpoint:** `POST /tracker`

```json
{
  "username": "jugador",
  "tag": "NA1",
  "discord_user_id": "opcional"
}
```

**Respuesta:**
```json
{
  "success": true,
  "stats": {
    "nombre": "jugador",
    "tag": "NA1",
    "nivel": 185,
    "ultima_actualizacion": "2024-01-15T10:30:00Z"
  }
}
```

## 🆘 Necesitas Ayuda?

Revisa [DEPLOY_RENDER_FULL.md](DEPLOY_RENDER_FULL.md) sección **Troubleshooting**
