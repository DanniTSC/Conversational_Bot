# src/core/health.py
from __future__ import annotations
import os, shutil
from typing import Dict, Tuple
from src.audio.devices import list_input_devices, choose_input_device

def _yes(b): return "✅" if b else "❌"

def run_health_checks(cfg: Dict, logger) -> Tuple[int, int]:
    """Returnează (warn_count, err_count). Loghează un sumar drăguț în consolă."""
    warns = errs = 0
    logger.info("🩺  Health check — pornire")

    # Piper
    tts = cfg.get("tts", {})
    p = (tts.get("piper") or {})
    exe = (p.get("exe") or shutil.which("piper"))
    if exe and os.path.exists(exe):
        logger.info(f"  {_yes(True)} Piper exe: {exe}")
    else:
        warns += 1
        logger.warning(f"  {_yes(False)} Piper nu a fost găsit (exe={exe}). Dacă vrei voce umană, instalează piper-tts.")

    # Modele Piper
    for lang, mk, ck in [
        ("ro", p.get("model_ro"), p.get("config_ro")),
        ("en", p.get("model_en"), p.get("config_en")),
    ]:
        if mk and os.path.exists(mk):
            logger.info(f"  {_yes(True)} Piper model [{lang}]: {mk}")
        else:
            warns += 1
            logger.warning(f"  {_yes(False)} Piper model [{lang}] lipsă sau cale greșită: {mk}")
        if ck and os.path.exists(ck):
            logger.info(f"     {_yes(True)} config: {ck}")
        else:
            logger.info(f"     ℹ️ config: {ck or '—'}")

    # Player audio
    paplay = shutil.which("paplay")
    aplay = shutil.which("aplay")
    if paplay:
        logger.info(f"  {_yes(True)} Player: paplay ({paplay})")
    elif aplay:
        logger.info(f"  {_yes(True)} Player: aplay ({aplay})")
    else:
        warns += 1
        logger.warning(f"  {_yes(False)} Fără paplay/aplay — voi încerca fallback Python (sounddevice).")

    # Dispozitive intrare & selecția curentă
    devs = list_input_devices()
    if not devs:
        warns += 1
        logger.warning("  ❌ Nu pot interoga dispozitivele audio — merg pe OS default.")
    else:
        # încearcă să „alegi” ce ar alege app-ul
        try:
            idx = choose_input_device(
                prefer_echo_cancel=bool(cfg["audio"].get("prefer_echo_cancel", True)),
                hint=str(cfg["audio"].get("input_device_hint", "") or ""),
                logger=logger
            )
        except Exception:
            idx = None
        pretty = " | ".join([f"[{i}] {n}" + (" ★" if idx == i else "") for i, n in devs])
        logger.info(f"  🎙️ Input devices: {pretty or '—'}")

    # Parametri audio de bază
    a = cfg.get("audio", {})
    logger.info(f"  🔧 Audio: sr={a.get('sample_rate')}Hz, block={a.get('block_ms')}ms, vad={a.get('vad_aggressiveness')}")

    logger.info(f"🩺  Health check — gata (warns={warns}, errors={errs})")
    return warns, errs
