#!/usr/bin/env python3
"""
Raspberry Pi 5 — Detailed System Monitor → Discord Webhook
"""

import json
import os
import subprocess
import sys
import urllib.request
import urllib.error
from datetime import datetime

# ─── Configuration ────────────────────────────────────────────────────────────
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
USERNAME = os.environ.get("NOTIFY_USERNAME", "methxmaster")

COOL_THRESHOLD  = float(os.environ.get("TEMP_COOL",  "40"))
WARN_THRESHOLD  = float(os.environ.get("TEMP_WARN",  "70"))
ALERT_THRESHOLD = float(os.environ.get("TEMP_ALERT", "80"))
# ──────────────────────────────────────────────────────────────────────────────


# ── Sensor readers ────────────────────────────────────────────────────────────

def _sysfs_temp(path: str) -> float:
    with open(path) as f:
        return int(f.read().strip()) / 1000.0


def get_cpu_temp() -> float:
    return _sysfs_temp("/sys/class/thermal/thermal_zone0/temp")


def get_gpu_temp() -> float:
    result = subprocess.run(["vcgencmd", "measure_temp"],
                            capture_output=True, text=True, check=True)
    return float(result.stdout.strip().split("=")[1].replace("'C", ""))


def get_rp1_temp() -> float:
    return _sysfs_temp("/sys/class/hwmon/hwmon1/temp1_input")


def _vcgencmd_float(cmd: list[str], prefix: str) -> float:
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(result.stdout.strip().split("=")[1].replace(prefix, ""))


def get_core_voltage() -> float:
    return _vcgencmd_float(["vcgencmd", "measure_volts", "core"], "V")


def get_arm_clock_mhz() -> int:
    hz = _vcgencmd_float(["vcgencmd", "measure_clock", "arm"], "")
    return int(hz / 1_000_000)


def get_gpu_clock_mhz() -> int:
    hz = _vcgencmd_float(["vcgencmd", "measure_clock", "core"], "")
    return int(hz / 1_000_000)


def get_throttle() -> dict:
    result = subprocess.run(["vcgencmd", "get_throttled"],
                            capture_output=True, text=True, check=True)
    raw = int(result.stdout.strip().split("=")[1], 16)
    return {
        "raw":          raw,
        "under_voltage":       bool(raw & 0x00001),
        "arm_freq_capped":     bool(raw & 0x00002),
        "throttled":           bool(raw & 0x00004),
        "soft_temp_limit":     bool(raw & 0x00008),
        "uv_occurred":         bool(raw & 0x10000),
        "freq_cap_occurred":   bool(raw & 0x20000),
        "throttle_occurred":   bool(raw & 0x40000),
        "soft_limit_occurred": bool(raw & 0x80000),
    }


def get_uptime() -> str:
    with open("/proc/uptime") as f:
        secs = float(f.read().split()[0])
    h, rem = divmod(int(secs), 3600)
    m, s   = divmod(rem, 60)
    return f"{h}h {m}m {s}s"


def get_cpu_usage() -> float:
    """Two-sample CPU utilisation over ~0.2 s."""
    def read_stat():
        with open("/proc/stat") as f:
            parts = f.readline().split()
        vals = list(map(int, parts[1:]))
        idle  = vals[3]
        total = sum(vals)
        return idle, total

    i1, t1 = read_stat()
    import time; time.sleep(0.2)
    i2, t2 = read_stat()
    dt = t2 - t1
    return round((1 - (i2 - i1) / dt) * 100, 1) if dt else 0.0


def get_memory() -> dict:
    info = {}
    with open("/proc/meminfo") as f:
        for line in f:
            k, v = line.split(":")
            info[k.strip()] = int(v.split()[0])   # kB
    total = info["MemTotal"]
    avail = info["MemAvailable"]
    used  = total - avail
    return {
        "total_mb": total // 1024,
        "used_mb":  used  // 1024,
        "pct":      round(used / total * 100, 1),
    }


# ── Visual helpers ────────────────────────────────────────────────────────────

def mono_bar(pct: float, length: int = 10) -> str:
    """Monospace ASCII bar: ██████░░░░"""
    filled = max(0, min(length, round((pct / 100.0) * length)))
    return "█" * filled + "░" * (length - filled)


def throttle_summary(t: dict) -> str:
    flags = []
    if t["under_voltage"]:     flags.append("⚡ Under-voltage (active)")
    if t["throttled"]:         flags.append("🔻 CPU throttled (active)")
    if t["arm_freq_capped"]:   flags.append("📉 Freq capped (active)")
    if t["soft_temp_limit"]:   flags.append("🌡️ Soft temp limit (active)")
    if t["uv_occurred"]:       flags.append("⚡ Under-voltage (occurred)")
    if t["throttle_occurred"]: flags.append("🔻 Throttle (occurred)")
    return "  ".join(flags) if flags else "✅  No issues detected"


# ── Embed builder ─────────────────────────────────────────────────────────────

def build_embed(data: dict) -> dict:
    cpu    = data["cpu_temp"]
    gpu    = data["gpu_temp"]
    rp1    = data["rp1_temp"]
    volt   = data["voltage"]
    arm    = data["arm_mhz"]
    gclk   = data["gpu_mhz"]
    thr    = data["throttle"]
    mem    = data["memory"]
    cpupct = data["cpu_pct"]
    uptime = data["uptime"]
    now    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    max_temp = max(cpu, gpu, rp1)

    if max_temp >= ALERT_THRESHOLD or thr["throttled"] or thr["under_voltage"]:
        color        = 0xFF4444
        status_emoji = "🔴"
        status_label = "CRITICAL"
    elif max_temp >= WARN_THRESHOLD or thr["throttle_occurred"]:
        color        = 0xFF9500
        status_emoji = "🟠"
        status_label = "WARNING"
    elif max_temp >= COOL_THRESHOLD:
        color        = 0xFEE75C
        status_emoji = "🟡"
        status_label = "NORMAL"
    else:
        color        = 0x57F287
        status_emoji = "🟢"
        status_label = "COOL"

    # monospace description block — all in one clean panel
    desc = (
        f"```\n"
        f"  🌡️  TEMPERATURE\n"
        f"  CPU  {mono_bar(cpu)}  {cpu:5.1f} °C\n"
        f"  GPU  {mono_bar(gpu)}  {gpu:5.1f} °C\n"
        f"  RP1  {mono_bar(rp1)}  {rp1:5.1f} °C\n"
        f"\n"
        f"  📊  PERFORMANCE\n"
        f"  CPU  {mono_bar(cpupct)}  {cpupct:5.1f} %\n"
        f"  RAM  {mono_bar(mem['pct'])}  {mem['pct']:5.1f} %  ({mem['used_mb']} / {mem['total_mb']} MB)\n"
        f"\n"
        f"  ⚙️  SYSTEM\n"
        f"  ARM Clock   {arm:>6,} MHz\n"
        f"  GPU Clock   {gclk:>6,} MHz\n"
        f"  Voltage     {volt:.4f} V\n"
        f"  Uptime      {uptime}\n"
        f"```"
    )

    return {
        "embeds": [
            {
                "title": f"🖥️  Raspberry Pi 5  —  {USERNAME}",
                "description": desc,
                "color": color,
                "fields": [
                    {
                        "name": f"{status_emoji}  Status",
                        "value": f"**{status_label}**",
                        "inline": True,
                    },
                    {
                        "name": "🛡️  Throttle / Voltage",
                        "value": throttle_summary(thr),
                        "inline": False,
                    },
                ],
                "footer": {
                    "text": (
                        f"🕐  {now}   •   Raspberry Pi 5 Model B   •   "
                        f"Cool <{COOL_THRESHOLD}°C  /  Warn ≥{WARN_THRESHOLD}°C  /  Critical ≥{ALERT_THRESHOLD}°C"
                    )
                },
            }
        ]
    }


# ── Discord sender ────────────────────────────────────────────────────────────

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
                print("Notification sent.")
    except urllib.error.HTTPError as exc:
        print(f"HTTP error {exc.code}: {exc.reason}\n{exc.read().decode()}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as exc:
        print(f"Network error: {exc.reason}", file=sys.stderr)
        sys.exit(1)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    data = {
        "cpu_temp": get_cpu_temp(),
        "gpu_temp": get_gpu_temp(),
        "rp1_temp": get_rp1_temp(),
        "voltage":  get_core_voltage(),
        "arm_mhz":  get_arm_clock_mhz(),
        "gpu_mhz":  get_gpu_clock_mhz(),
        "throttle": get_throttle(),
        "memory":   get_memory(),
        "cpu_pct":  get_cpu_usage(),
        "uptime":   get_uptime(),
    }

    print(
        f"CPU {data['cpu_temp']:.1f}°C  "
        f"GPU {data['gpu_temp']:.1f}°C  "
        f"RP1 {data['rp1_temp']:.1f}°C  "
        f"ARM {data['arm_mhz']} MHz  "
        f"MEM {data['memory']['pct']}%  "
        f"CPU% {data['cpu_pct']}%  "
        f"throttled=0x{data['throttle']['raw']:05X}"
    )

    payload = build_embed(data)
    send_to_discord(payload)


if __name__ == "__main__":
    main()
