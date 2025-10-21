# src/tts/engine.py
from __future__ import annotations
from typing import Dict, Optional
import pyttsx3

# metrics
from src.telemetry.metrics import observe_hist, tts_latency, tts_speak_calls

class TTSLocal:
    """
    TTS simplu, offline, prin pyttsx3 (espeak-ng pe Linux).
    Config în tts.yaml: rate, volume, voice_ro_hint, voice_en_hint
    """

    def __init__(self, cfg: Dict, logger):
        self.log = logger
        self.eng = pyttsx3.init()
        self.rate = int(cfg.get("rate", 170))
        self.volume = float(cfg.get("volume", 1.0))
        self.voice_ro_hint = cfg.get("voice_ro_hint", "ro")
        self.voice_en_hint = cfg.get("voice_en_hint", "en")
        self.eng.setProperty("rate", self.rate)
        self.eng.setProperty("volume", self.volume)
        self._voices = self.eng.getProperty("voices")

    def _pick_voice(self, lang: str) -> Optional[str]:
        target = self.voice_ro_hint if lang.startswith("ro") else self.voice_en_hint
        target = (target or "").lower()
        for v in self._voices:
            name = (getattr(v, "name", "") or "").lower()
            _id = (getattr(v, "id", "") or "").lower()
            if target and (target in name or target in _id):
                return v.id
        return self._voices[0].id if self._voices else None

    def say(self, text: str, lang: str = "en"):
        vid = self._pick_voice(lang)
        if vid:
            self.eng.setProperty("voice", vid)
        else:
            self.log.warning("⚠️ Nicio voce potrivită găsită, folosesc default.")
        tts_speak_calls.inc()
        with observe_hist(tts_latency):
            self.eng.say(text)
            self.eng.runAndWait()
