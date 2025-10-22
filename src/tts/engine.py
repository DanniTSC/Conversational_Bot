# src/tts/engine.py
from __future__ import annotations
from typing import Dict, Optional, Iterable, Callable
import threading, re, os, shutil, subprocess, tempfile, time
import soundfile as sf
import sounddevice as sd

from src.telemetry.metrics import tts_speak_calls

_SENT_SPLIT = re.compile(r'([.!?…:;]+)\s+')

# -------------------- PYTTSX3 BACKEND --------------------
class _Pyttsx3TTS:
    def __init__(self, cfg: Dict, logger):
        import pyttsx3
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
        self._speaking = threading.Event()
        self._speak_th: Optional[threading.Thread] = None

    def _pick_voice(self, lang: str) -> Optional[str]:
        target = (self.voice_ro_hint if lang.startswith("ro") else self.voice_en_hint or "").lower()
        for v in self._voices:
            name = (getattr(v, "name", "") or "").lower()
            _id  = (getattr(v, "id", "") or "").lower()
            if target and (target in name or target in _id):
                return v.id
        return self._voices[0].id if self._voices else None

    def is_speaking(self) -> bool:
        return self._speaking.is_set()

    def say(self, text: str, lang: str = "en"):
        vid = self._pick_voice(lang)
        if vid: self.eng.setProperty("voice", vid)
        else:   self.log.warning("⚠️ Nicio voce potrivită (pyttsx3) – folosesc default.")
        tts_speak_calls.inc()
        self._speaking.set()
        try:
            self.eng.say(text)
            self.eng.runAndWait()
        finally:
            self._speaking.clear()

    def say_async_stream(
        self,
        token_iter: Iterable[str],
        lang: str = "en",
        on_first_speak: Optional[Callable[[], None]] = None,
        min_chunk_chars: int = 80,
        on_done: Optional[Callable[[], None]] = None,
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
                            if s: out.append(s)
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
                self.log.error(f"TTS stream error (pyttsx3): {e}")
            finally:
                self._speaking.clear()
                if on_done:
                    try: on_done()
                    except Exception: pass

        self.stop()
        self._stop.clear()
        self._speak_th = threading.Thread(target=worker, daemon=True)
        self._speak_th.start()
        return self._speaking

    def stop(self):
        with self._lock:
            self._stop.set()
            try: self.eng.stop()
            except Exception: pass
        self._speaking.clear()

# -------------------- PIPER (CLI) BACKEND --------------------
class _PiperCmdTTS:
    def __init__(self, cfg: Dict, logger):
        self.log = logger
        self.cfg = cfg or {}
        self.p = self.cfg.get("piper", {}) or {}
        self.exe = self.p.get("exe") or shutil.which("piper")
        self.model_ro = self.p.get("model_ro")
        self.config_ro = self.p.get("config_ro")
        self.model_en = self.p.get("model_en")
        self.config_en = self.p.get("config_en")
        self.speaker_id = self.p.get("speaker_id", None)
        self.length_scale = float(self.p.get("length_scale", 1.0))
        self.noise_scale = float(self.p.get("noise_scale", 0.667))
        self.noise_w = float(self.p.get("noise_w", 0.8))
        self.sentence_silence_ms = int(self.p.get("sentence_silence_ms", 80))

        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._speaking = threading.Event()
        self._speak_th: Optional[threading.Thread] = None
        self._play_proc: Optional[subprocess.Popen] = None

        if not self.exe or not os.path.exists(self.exe):
            raise RuntimeError("Piper executable not found. Set tts.piper.exe or install piper-tts.")

    def is_speaking(self) -> bool:
        return self._speaking.is_set()

    def _pick_model(self, lang: str):
        if lang.startswith("ro"):
            return self.model_ro, self.config_ro
        return self.model_en, self.config_en

    def _synth_to_wav(self, text: str, lang: str) -> str:
        model, cfg = self._pick_model(lang)
        if not (model and cfg):
            raise RuntimeError("Piper model/config not set for selected language.")
        fd, path = tempfile.mkstemp(prefix=f"piper_{lang}_", suffix=".wav")
        os.close(fd)

        cmd = [self.exe, "--model", model, "--config", cfg, "--output_file", path]
        # Parametri opționali – doar dacă sunt setați
        if self.speaker_id is not None:
            cmd += ["--speaker", str(self.speaker_id)]
        # Notă: nu toate build-urile Piper au aceleași flag-uri; ținem doar strictul necesar.

        try:
            subprocess.run(cmd, input=text.encode("utf-8"), check=True)
            return path
        except subprocess.CalledProcessError as e:
            self.log.error(f"Piper synth failed: {e}")
            raise

    def _play_wav(self, wav_path: str):
        # 1) paplay (PulseAudio/PipeWire)
        player = shutil.which("paplay")
        if player:
            self.log.debug(f"🔊 Piper: redare via paplay: {wav_path}")
            self._play_proc = subprocess.Popen([player, wav_path])
            while self._play_proc.poll() is None:
                if self._stop.is_set():
                    self._play_proc.terminate()
                    break
                time.sleep(0.02)
            return

        # 2) aplay (ALSA)
        player = shutil.which("aplay")
        if player:
            self.log.debug(f"🔊 Piper: redare via aplay: {wav_path}")
            self._play_proc = subprocess.Popen([player, "-q", wav_path])
            while self._play_proc.poll() is None:
                if self._stop.is_set():
                    self._play_proc.terminate()
                    break
                time.sleep(0.02)
            return

        # 3) fallback Python (sounddevice)
        try:
            data, sr = sf.read(wav_path, dtype="float32")
            sd.play(data, sr)
            while sd.get_stream() and sd.get_stream().active:
                if self._stop.is_set():
                    sd.stop()
                    break
                time.sleep(0.02)
            sd.wait()
        except Exception as e:
            self.log.error(f"Audio playback error: {e}")

    def _speak_once(self, text: str, lang: str, on_first_speak: Optional[Callable[[], None]] = None, first_flag=None):
        wav = self._synth_to_wav(text, lang)
        try:
            if on_first_speak and first_flag is not None and not first_flag["done"]:
                first_flag["done"] = True
                try: on_first_speak()
                except Exception: pass
            self._play_wav(wav)
        finally:
            try: os.remove(wav)
            except Exception: pass

    def say(self, text: str, lang: str = "en"):
        tts_speak_calls.inc()
        self._speaking.set()
        try:
            self._speak_once(text, lang)
        finally:
            self._speaking.clear()

    def say_async_stream(
        self,
        token_iter: Iterable[str],
        lang: str = "en",
        on_first_speak: Optional[Callable[[], None]] = None,
        min_chunk_chars: int = 80,
        on_done: Optional[Callable[[], None]] = None,
    ):
        def worker():
            first_flag = {"done": False}
            buf = ""
            self._speaking.set()
            tts_speak_calls.inc()
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
                            if s: out.append(s)
                        buf = parts[-1] if (len(parts) % 2 == 1) else ""

                    if not out and len(buf) >= min_chunk_chars:
                        last_space = buf.rfind(" ")
                        if last_space > 20:
                            out.append(buf[:last_space].strip())
                            buf = buf[last_space+1:]

                    for sentence in out:
                        if self._stop.is_set():
                            break
                        self._speak_once(sentence, lang, on_first_speak, first_flag)

                if not self._stop.is_set() and buf.strip():
                    self._speak_once(buf.strip(), lang, on_first_speak, first_flag)
            except Exception as e:
                self.log.error(f"TTS stream error (piper): {e}")
            finally:
                self._speaking.clear()
                if on_done:
                    try: on_done()
                    except Exception: pass

        self.stop()
        self._stop.clear()
        th = threading.Thread(target=worker, daemon=True)
        th.start()
        self._speak_th = th
        return self._speaking

    def stop(self):
        with self._lock:
            self._stop.set()
            # oprește playerul dacă e
            try:
                if self._play_proc and self._play_proc.poll() is None:
                    self._play_proc.terminate()
            except Exception:
                pass
        self._speaking.clear()

# -------------------- FACADE --------------------
class TTSLocal:
    """
    Wrapper: alege backendul în funcție de configs/tts.yaml:
      - backend: piper  -> _PiperCmdTTS
      - altfel         -> _Pyttsx3TTS (fallback)
    """
    def __init__(self, cfg: Dict, logger):
        self.log = logger
        backend = (cfg.get("backend") or "pyttsx3").lower()
        try:
            if backend == "piper":
                self.impl = _PiperCmdTTS(cfg, logger)
                self.log.info("TTS backend: Piper")
            else:
                raise RuntimeError("force pyttsx3")
        except Exception as e:
            self.log.warning(f"Piper indisponibil ({e}). Revin pe pyttsx3.")
            self.impl = _Pyttsx3TTS(cfg, logger)
            self.log.info("TTS backend: pyttsx3")

    def is_speaking(self) -> bool:
        return self.impl.is_speaking()

    def say(self, text: str, lang: str = "en"):
        return self.impl.say(text, lang)

    def say_async_stream(
        self,
        token_iter: Iterable[str],
        lang: str = "en",
        on_first_speak: Optional[Callable[[], None]] = None,
        min_chunk_chars: int = 80,
        on_done: Optional[Callable[[], None]] = None,
    ):
        return self.impl.say_async_stream(token_iter, lang, on_first_speak, min_chunk_chars, on_done)

    def stop(self):
        return self.impl.stop()
