# src/tts/engine.py
from __future__ import annotations
from typing import Dict, Iterable
import threading, queue, re, pyttsx3

_SENT_SPLIT = re.compile(r'([.!?…]+)\s+')

class TTSLocal:
    def __init__(self, cfg: Dict, logger):
        self.log = logger
        self.eng = pyttsx3.init()
        self.rate = int(cfg.get("rate", 180))
        self.volume = float(cfg.get("volume", 1.0))
        self.voice_ro_hint = (cfg.get("voice_ro_hint") or "ro").lower()
        self.voice_en_hint = (cfg.get("voice_en_hint") or "en").lower()
        self.eng.setProperty("rate", self.rate)
        self.eng.setProperty("volume", self.volume)
        self._voices = self.eng.getProperty("voices")
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._speak_th = None

    def _pick_voice(self, lang: str):
        target = self.voice_ro_hint if lang.startswith("ro") else self.voice_en_hint
        for v in self._voices:
            name = (getattr(v,"name","") or "").lower()
            _id  = (getattr(v,"id","") or "").lower()
            if target in name or target in _id:
                return v.id
        return self._voices[0].id if self._voices else None

    def say(self, text: str, lang: str = "en"):
        with self._lock:
            self._stop.clear()
            vid = self._pick_voice(lang)
            if vid: self.eng.setProperty("voice", vid)
            self.eng.say(text)
            self.eng.runAndWait()

    def say_async_stream(self, token_iter: Iterable[str], lang: str = "en"):
        """Primește token-uri; bufează până la final de propoziție, apoi rostește."""
        def worker():
            buf = ""
            vid = self._pick_voice(lang)
            if vid: self.eng.setProperty("voice", vid)
            for tok in token_iter:
                if self._stop.is_set(): break
                buf += tok
                # împărțim pe fraze; vorbim când avem un delimitator
                parts = _SENT_SPLIT.split(buf)
                # parts = [frag, punct, frag, punct, ... , rest]
                out = []
                rebuilt = ""
                for i in range(0, len(parts)-1, 2):
                    frag, punct = parts[i], parts[i+1]
                    out.append((frag+punct).strip())
                # restul fără delimitator rămâne în buf
                if len(parts) % 2 == 1:
                    buf = parts[-1]
                else:
                    buf = ""
                for sentence in out:
                    if sentence and not self._stop.is_set():
                        self.eng.say(sentence)
                        self.eng.runAndWait()
            # finalul rămas
            if not self._stop.is_set() and buf.strip():
                self.eng.say(buf.strip())
                self.eng.runAndWait()

        self.stop()  # oprește orice vorbire anterioară
        self._stop.clear()
        self._speak_th = threading.Thread(target=worker, daemon=True)
        self._speak_th.start()

    def stop(self):
        with self._lock:
            self._stop.set()
            try: self.eng.stop()
            except Exception: pass
