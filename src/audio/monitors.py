# src/audio/monitors.py
from __future__ import annotations
import sounddevice as sd

def _match(hay: str, needle: str) -> bool:
    return needle.lower() in (hay or "").lower()

def choose_monitor_device(hint: str = "", logger=None):
    try:
        devs = sd.query_devices()
    except Exception as e:
        if logger: logger.warning(f"Nu pot interoga device-urile: {e}")
        return None
    candidates = [(i, d) for i, d in enumerate(devs) if d.get("max_input_channels", 0) > 0]
    keys = []
    if hint: keys.append(hint)
    keys += ["monitor", "loopback", "stereo mix", "what u hear"]

    for i, d in candidates:
        name = (d.get("name") or "")
        if any(_match(name, k) for k in keys):
            if logger: logger.info(f"🔁 selectez monitor '{name}' (far-end pentru AEC)")
            return i
    if logger: logger.warning("⚠️ Nu am găsit monitor/loopback; AEC WebRTC va folosi far-end=0 (mai slab).")
    return None
