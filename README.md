# Raspberry Pi 5 — System Monitor → Discord

Monitors system health on a Raspberry Pi 5 and sends a formatted notification to a Discord webhook every hour via cron.

## What it monitors

| Metric | Source |
|--------|--------|
| CPU temperature | `/sys/class/thermal/thermal_zone0` |
| GPU temperature | `vcgencmd measure_temp` |
| RP1 chip temperature | `/sys/class/hwmon/hwmon1` |
| CPU usage % | `/proc/stat` (two-sample) |
| RAM usage % / MB | `/proc/meminfo` |
| ARM clock (MHz) | `vcgencmd measure_clock arm` |
| GPU clock (MHz) | `vcgencmd measure_clock core` |
| Core voltage (V) | `vcgencmd measure_volts core` |
| Throttle / under-voltage flags | `vcgencmd get_throttled` |
| System uptime | `/proc/uptime` |

## Discord notification preview

```
🖥️  Raspberry Pi 5 — methxmaster
╔══════════════════════════════════╗
  🌡️  TEMPERATURE
  CPU  ████░░░░░░   49.6 °C
  GPU  ████░░░░░░   49.9 °C
  RP1  ████░░░░░░   44.4 °C

  📊  PERFORMANCE
  CPU  █░░░░░░░░░    7.5 %
  RAM  ██░░░░░░░░   18.7 %  (340 / 1820 MB)

  ⚙️  SYSTEM
  ARM Clock    2,400 MHz
  GPU Clock      682 MHz
  Voltage      0.7200 V
  Uptime       2h 15m 30s
╚══════════════════════════════════╝

🟡 Status: NORMAL
🛡️ Throttle / Voltage: ✅ No issues detected

🕐 2026-03-24 01:00:01  •  Raspberry Pi 5 Model B  •  Cool <40°C / Warn ≥70°C / Critical ≥80°C
```

### Status levels

| Temp | Status | Color |
|------|--------|-------|
| < 40°C | 🟢 COOL | Green |
| 40 – 69°C | 🟡 NORMAL | Yellow |
| 70 – 79°C | 🟠 WARNING | Orange |
| ≥ 80°C | 🔴 CRITICAL | Red |

Status also escalates to WARNING/CRITICAL if throttle or under-voltage flags are detected.

## Requirements

- Raspberry Pi 5 running Raspberry Pi OS
- Python 3.x (stdlib only — no pip installs needed)
- `vcgencmd` (pre-installed on Raspberry Pi OS)

## Setup

**1. Clone the repo**
```bash
git clone https://github.com/your-username/meth-RaspPi-gamma.git
cd meth-RaspPi-gamma
```

**2. Create a Discord webhook**

Discord → Server Settings → Integrations → Webhooks → New Webhook → Copy Webhook URL

**3. Set the webhook URL**

Add to `~/.bashrc` or `~/.profile`:
```bash
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/YOUR_ID/YOUR_TOKEN"
```

Or create a `.env` file (never commit this):
```bash
echo 'DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_ID/YOUR_TOKEN' > .env
```

**4. Run manually**
```bash
DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..." python3 temp_notify.py
```

## Schedule with cron (every hour)

```bash
crontab -e
```

Add this line:
```
0 * * * * DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..." /usr/bin/python3 /path/to/temp_notify.py >> /path/to/temp_notify.log 2>&1
```

**Other intervals:**
```
*/10 * * * *   # every 10 minutes
*/30 * * * *   # every 30 minutes
0 * * * *      # every hour
```

**View logs:**
```bash
tail -f temp_notify.log
```

## Configuration

All settings can be overridden via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `DISCORD_WEBHOOK_URL` | *(required)* | Discord webhook URL |
| `NOTIFY_USERNAME` | `methxmaster` | Name shown in the embed title |
| `TEMP_COOL` | `40` | Below this = COOL (green) |
| `TEMP_WARN` | `70` | Above this = WARNING (orange) |
| `TEMP_ALERT` | `80` | Above this = CRITICAL (red) |

Example:
```bash
DISCORD_WEBHOOK_URL="..." TEMP_WARN=65 TEMP_ALERT=75 python3 temp_notify.py
```

## Security

- Never commit your webhook URL to Git
- Add `.env` to `.gitignore`
- If a webhook URL is accidentally leaked, delete it in Discord immediately (Server Settings → Integrations → Webhooks) and create a new one
