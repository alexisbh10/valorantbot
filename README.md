# 🎮 Valorant Tracker Bot

Bot de Discord para obtener estadísticas de jugadores de Valorant.

## 🚀 Instalación Rápida

Ver: **[START.md](START.md)** - Guía para empezar
Ver: **[DEPLOY_GITHUB_RENDER.md](DEPLOY_GITHUB_RENDER.md)** - Guía completa de deploy

## 📥 Instalación Manual

1. **Instalar dependencias:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configurar `.env`:**
   ```
   DISCORD_TOKEN=tu_token_aqui
   TRACKER_URL=https://valorant-tracker.onrender.com  # o http://localhost:8000
   DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/ID/TOKEN
   ```

3. **Obtener tokens:**
   - **Discord Token:** https://discord.com/developers/applications → Bot → Copy Token
   - **Webhook URL:** Discord Server → Settings → Integrations → Webhooks → New Webhook → Copy Link

## 🎯 Uso

**Backend (Render.com):**
```bash
# Se despliega automáticamente en Render
```

**Bot local:**
```bash
python discord_bot.py
```

## 💬 Comandos Discord

- `/stats nombre region` - Obtener stats de un jugador
- `/regiones` - Ver regiones disponibles

**Ejemplo:**
```
/stats aceu NA1
```

## 📊 Respuesta

El bot devuelve un embed con:
- 👤 Nombre del jugador
- 🏷️ Tag
- 🎮 Nivel de cuenta
- 🔄 Última actualización

## 🌍 Regiones

| Código | Región |
|--------|--------|
| NA1 | Norteamérica |
| EUW1 | Europa Occidental |
| LATAM | América Latina |
| BRA1 | Brasil |
| AP1 | APAC |
| KR | Corea |

## 📡 API Backend

**Endpoint:** `POST /tracker`

```json
{
  "username": "nombreJugador",
  "tag": "NA1",
  "discord_user_id": "opcional"
}
```

## 🆘 Troubleshooting

| Error | Solución |
|-------|----------|
| "Jugador no encontrado" | Verifica nombre y región |
| "DISCORD_TOKEN not found" | Configura `.env` correctamente |
| "Connection refused" | Asegúrate que webhook.py está corriendo |
