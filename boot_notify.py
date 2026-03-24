#!/usr/bin/env python3
"""
Raspberry Pi 5 — Boot Notification → Discord Webhook
Sends a "Pi is back online" alert when the system starts up.
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime

# ─── Configuration ────────────────────────────────────────────────────────────
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
USERNAME = os.environ.get("NOTIFY_USERNAME", "methxmaster")
BOOT_DELAY = int(os.environ.get("BOOT_DELAY", "15"))  # seconds to wait for network
# ──────────────────────────────────────────────────────────────────────────────


def get_local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "unknown"


def get_uptime() -> str:
    with open("/proc/uptime") as f:
        secs = float(f.read().split()[0])
    h, rem = divmod(int(secs), 3600)
    m, s   = divmod(rem, 60)
    return f"{h}h {m}m {s}s"


def get_cpu_temp() -> float:
    with open("/sys/class/thermal/thermal_zone0/temp") as f:
        return int(f.read().strip()) / 1000.0


def get_disk() -> dict:
    usage = shutil.disk_usage("/")
    return {
        "total_gb": round(usage.total / 1024**3, 1),
        "used_gb":  round(usage.used  / 1024**3, 1),
        "pct":      round(usage.used  / usage.total * 100, 1),
    }


def get_kernel() -> str:
    result = subprocess.run(["uname", "-r"], capture_output=True, text=True)
    return result.stdout.strip()


def build_embed(data: dict) -> dict:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    disk = data["disk"]

    desc = (
        f"```\n"
        f"  🌐  NETWORK\n"
        f"  Local IP    {data['local_ip']}\n"
        f"\n"
        f"  🌡️  TEMPERATURE\n"
        f"  CPU         {data['cpu_temp']:.1f} °C\n"
        f"\n"
        f"  💾  STORAGE\n"
        f"  Disk        {disk['used_gb']} / {disk['total_gb']} GB  ({disk['pct']}%)\n"
        f"\n"
        f"  ⚙️  SYSTEM\n"
        f"  Kernel      {data['kernel']}\n"
        f"  Uptime      {data['uptime']}\n"
        f"```"
    )

    return {
        "embeds": [
            {
                "title": f"🟢  Raspberry Pi 5 is back online  —  {USERNAME}",
                "description": desc,
                "color": 0x57F287,
                "footer": {
                    "text": f"🕐  {now}   •   Boot event   •   Raspberry Pi 5 Model B"
                },
            }
        ]
    }


def send_to_discord(payload: dict) -> None:
    if not DISCORD_WEBHOOK_URL:
        print("ERROR: DISCORD_WEBHOOK_URL is not set.", file=sys.stderr)
        sys.exit(1)

    data = json.dumps(payload).encode("utf-8")
    req  = urllib.request.Request(
        DISCORD_WEBHOOK_URL,
        data=data,
        headers={
            "Content-Type": "application/json",
            "User-Agent":   "DiscordBot (RaspberryPi, 1.0)",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.getcode() in (200, 204):
                print("Boot notification sent.")
    except urllib.error.HTTPError as exc:
        print(f"HTTP error {exc.code}: {exc.reason}\n{exc.read().decode()}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as exc:
        print(f"Network error: {exc.reason}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    # Wait for network to come up before sending
    time.sleep(BOOT_DELAY)

    data = {
        "local_ip": get_local_ip(),
        "cpu_temp": get_cpu_temp(),
        "disk":     get_disk(),
        "kernel":   get_kernel(),
        "uptime":   get_uptime(),
    }

    print(f"Boot detected — IP: {data['local_ip']}  CPU: {data['cpu_temp']:.1f}°C")
    payload = build_embed(data)
    send_to_discord(payload)


if __name__ == "__main__":
    main()
