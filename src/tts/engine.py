# src/tts/engine.py
from __future__ import annotations
from typing import Dict, Optional, Iterable, Callable
import threading, re
import pyttsx3

from src.telemetry.metrics import tts_speak_calls

_SENT_SPLIT = re.compile(r'([.!?…:;]+)\s+')

class TTSLocal:
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

        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._speaking = threading.Event()   # <— nou
        self._speak_th: Optional[threading.Thread] = None

    def _pick_voice(self, lang: str) -> Optional[str]:
        target = (self.voice_ro_hint if lang.startswith("ro") else self.voice_en_hint or "").lower()
        for v in self._voices:
            name = (getattr(v, "name", "") or "").lower()
            _id  = (getattr(v, "id", "") or "").lower()
            if target and (target in name or target in _id):
                return v.id
        return self._voices[0].id if self._voices else None

    def is_speaking(self) -> bool:          # <— nou
        return self._speaking.is_set()

    def say(self, text: str, lang: str = "en"):
        vid = self._pick_voice(lang)
        if vid: self.eng.setProperty("voice", vid)
        else:   self.log.warning("⚠️ Nicio voce potrivită găsită, folosesc default.")
        tts_speak_calls.inc()
        self._speaking.set()
        try:
            self.eng.say(text)
            self.eng.runAndWait()
        finally:
            self._speaking.clear()

    def say_async(self, text: str, lang: str = "en"):
        def worker():
            try:
                self.say(text, lang=lang)
            except Exception as e:
                self.log.error(f"TTS async error: {e}")
        self.stop()
        self._stop.clear()
        self._speak_th = threading.Thread(target=worker, daemon=True)
        self._speak_th.start()

    def say_async_stream(
        self,
        token_iter: Iterable[str],
        lang: str = "en",
        on_first_speak: Optional[Callable[[], None]] = None,
        min_chunk_chars: int = 80,
        on_done: Optional[Callable[[], None]] = None,  # <— nou
    ):
        def worker():
            first_spoken = False
            buf = ""
            vid = self._pick_voice(lang)
            if vid: self.eng.setProperty("voice", vid)
            tts_speak_calls.inc()
            self._speaking.set()
            try:
                for tok in token_iter:
                    if self._stop.is_set():
                        break
                    buf += tok

                    parts = _SENT_SPLIT.split(buf)
                    out = []
                    if len(parts) >= 2:
                        for i in range(0, len(parts)-1, 2):
                            frag, punct = parts[i], parts[i+1]
                            s = (frag + punct).strip()
                            if s:
                                out.append(s)
                        buf = parts[-1] if (len(parts) % 2 == 1) else ""

                    if not out and len(buf) >= min_chunk_chars:
                        last_space = buf.rfind(" ")
                        if last_space > 20:
                            out.append(buf[:last_space].strip())
                            buf = buf[last_space+1:]

                    for sentence in out:
                        if self._stop.is_set():
                            break
                        if on_first_speak and not first_spoken:
                            first_spoken = True
                            try: on_first_speak()
                            except Exception: pass
                        self.eng.say(sentence)
                        self.eng.runAndWait()

                if not self._stop.is_set() and buf.strip():
                    if on_first_speak and not first_spoken:
                        first_spoken = True
                        try: on_first_speak()
                        except Exception: pass
                    self.eng.say(buf.strip())
                    self.eng.runAndWait()
            except Exception as e:
                self.log.error(f"TTS stream error: {e}")
            finally:
                self._speaking.clear()
                if on_done:
                    try: on_done()
                    except Exception: pass

        self.stop()
        self._stop.clear()
        self._speak_th = threading.Thread(target=worker, daemon=True)
        self._speak_th.start()
        return self._speaking  # poți da wait pe el în app

    def stop(self):
        with self._lock:
            self._stop.set()
            try: self.eng.stop()
            except Exception: pass
        self._speaking.clear()
