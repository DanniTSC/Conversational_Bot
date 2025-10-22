# src/audio/devices.py
from __future__ import annotations
from typing import Optional, Tuple, List
import sounddevice as sd

def _match(hay: str, needle: str) -> bool:
    return (needle or "").lower() in (hay or "").lower()

def list_input_devices() -> List[Tuple[int, str]]:
    try:
        devs = sd.query_devices()
    except Exception:
        return []
    out = []
    for i, d in enumerate(devs):
        if d.get("max_input_channels", 0) > 0:
            name = d.get("name", "")
            host = d.get("hostapi", None)
            out.append((i, name))
    return out

def choose_input_device(
    prefer_echo_cancel: bool = True,
    hint: str = "",
    index: Optional[int] = None,
    logger=None
) -> Optional[int]:
    """Returnează indexul dispozitivului de intrare preferat.
       Prioritate: index explicit > nume "echo-cancel" > hint > default(None)
    """
    # 0) index explicit?
    if index is not None:
        if logger: logger.info(f"🎙️ selectez input prin index forțat: {index}")
        return index

    # 1) listă device-uri (pt. debug)
    devs = list_input_devices()
    if logger:
        if not devs:
            logger.warning("Nu pot interoga dispozitivele audio (sounddevice/PortAudio). Folosesc default OS.")
        else:
            names = " | ".join([f"[{i}] {n}" for i, n in devs])
            logger.info(f"🔎 Input devices: {names}")

    # 2) echo-cancel după mai multe pattern-uri
    if prefer_echo_cancel and devs:
        keys = ["echo-cancel", "echo cancel", "cancelled", "ec_mic", "aec"]
        for i, n in devs:
            if any(_match(n, k) for k in keys):
                if logger: logger.info(f"🎙️ selectez input '{n}' (echo-cancel).")
                return i

    # 3) după hint liber
    if hint and devs:
        for i, n in devs:
            if _match(n, hint):
                if logger: logger.info(f"🎙️ selectez input după hint '{hint}': {n}")
                return i

    if logger: logger.info("🎙️ folosesc input audio implicit (OS default).")
    return None
