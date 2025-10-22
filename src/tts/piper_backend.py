# src/tts/piper_backend.py
from __future__ import annotations
from typing import Dict, Optional, Iterable, Callable
import os, re, threading, subprocess, tempfile, time
import sounddevice as sd
import soundfile as sf

_SENT_SPLIT = re.compile(r'([.!?…:;]+)\s+')

class PiperTTS:
    """
    Backend TTS pentru Piper (folosește binarul `piper` prin subprocess).
    - Generează WAV per frază (sau bucăți) și redă cu sounddevice.
    - Dacă lipsesc binarul sau modelele -> aruncă excepție (app va face fallback la pyttsx3).
    """
    def __init__(self, cfg: Dict, logger):
        self.log = logger
        self.cfg = cfg or {}
        self.eng = None  # doar pentru simetrie cu pyttsx3

        self.exe = (self.cfg.get("piper", {}).get("exe") or "").strip()
        self.model_ro = (self.cfg.get("piper", {}).get("model_ro") or "").strip()
        self.config_ro = (self.cfg.get("piper", {}).get("config_ro") or "").strip()
        self.model_en = (self.cfg.get("piper", {}).get("model_en") or "").strip()
        self.config_en = (self.cfg.get("piper", {}).get("config_en") or "").strip()

        self.speaker_id = self.cfg.get("piper", {}).get("speaker_id", None)
        self.length_scale = float(self.cfg.get("piper", {}).get("length_scale", 1.0))
        self.noise_scale  = float(self.cfg.get("piper", {}).get("noise_scale", 0.667))
        self.noise_w      = float(self.cfg.get("piper", {}).get("noise_w", 0.8))
        self.sil_ms       = int(self.cfg.get("piper", {}).get("sentence_silence_ms", 80))

        # controale runtime
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._speaking = threading.Event()
        self._speak_th: Optional[threading.Thread] = None

        # sanity checks
        if not (self.exe and os.path.exists(self.exe)):
            raise RuntimeError("Piper binar lipsă sau cale greșită. Verifică tts.piper.exe")
        if not (os.path.exists(self.model_ro) and os.path.exists(self.model_en)):
            raise RuntimeError("Modelele Piper lipsă sau căi greșite (model_ro/model_en).")

        self.log.info(f"Piper TTS ready (exe={self.exe})")

    def is_speaking(self) -> bool:
        return self._speaking.is_set()

    # -------------- synth helpers --------------
    def _model_for_lang(self, lang: str):
        if str(lang).lower().startswith("ro"):
            return self.model_ro, (self.config_ro if self.config_ro else None)
        return self.model_en, (self.config_en if self.config_en else None)

    def _synth_to_wav(self, text: str, lang: str) -> str:
        """Rulează `piper` pe text și returnează path-ul unui WAV temporar."""
        model, cfg = self._model_for_lang(lang)
        out_wav = tempfile.NamedTemporaryFile(prefix="piper_", suffix=".wav", delete=False)
        out_wav_path = out_wav.name
        out_wav.close()

        # Construim comanda Piper (folosim opțiuni uzuale; cfg/speaker sunt opționale)
        cmd = [self.exe, "--model", model, "--output_file", out_wav_path,
               "--length_scale", str(self.length_scale),
               "--noise_scale", str(self.noise_scale),
               "--noise_w", str(self.noise_w),
        ]
        if cfg and os.path.exists(cfg):
            cmd += ["--config", cfg]
        if self.speaker_id is not None:
            cmd += ["--speaker", str(self.speaker_id)]

        try:
            # piper citește textul de la stdin (utf-8)
            proc = subprocess.run(
                cmd, input=text.encode("utf-8"),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True
            )
        except subprocess.CalledProcessError as e:
            stderr = (e.stderr or b"").decode("utf-8", "ignore")
            self.log.error(f"Piper synth error: {stderr}")
            raise
        return out_wav_path

    def _play_wav_blocking(self, wav_path: str):
        """Redă WAV blocking. Respectă self._stop pentru barge/stop imediat."""
        try:
            data, sr = sf.read(wav_path, dtype="int16", always_2d=False)
            # data poate fi (n,) mono sau (n, ch). Piper e mono.
            if data.ndim == 2:
                # mix la mono dacă e cazul
                data = data.mean(axis=1).astype("int16")
        except Exception as e:
            self.log.error(f"Nu pot citi WAV generat de Piper: {e}")
            return

        # redare frame-by-frame ca să putem opri repede
        block = int(sr * 0.05)  # 50ms
        try:
            with sd.OutputStream(samplerate=sr, channels=1, dtype="int16") as stream:
                i = 0
                while i < len(data) and not self._stop.is_set():
                    chunk = data[i:i+block]
                    stream.write(chunk)
                    i += block
        except Exception as e:
            self.log.error(f"Eroare la redare audio: {e}")

    def _sleep_ms(self, ms: int):
        t0 = time.time()
        while (time.time() - t0) * 1000 < ms and not self._stop.is_set():
            time.sleep(0.005)

    # -------------- public API (similar cu TTSLocal) --------------
    def say(self, text: str, lang: str = "en"):
        """Sinteză blocking, pe propoziții."""
        self._stop.clear()
        self._speaking.set()
        try:
            parts = _SENT_SPLIT.split(text)
            sentences = []
            if len(parts) >= 2:
                for i in range(0, len(parts)-1, 2):
                    frag, punct = parts[i], parts[i+1]
                    s = (frag + punct).strip()
                    if s: sentences.append(s)
                tail = parts[-1].strip() if (len(parts) % 2 == 1) else ""
                if tail: sentences.append(tail)
            else:
                if text.strip():
                    sentences = [text.strip()]

            for s in sentences:
                if self._stop.is_set(): break
                wav = self._synth_to_wav(s, lang)
                try:
                    self._play_wav_blocking(wav)
                finally:
                    try: os.remove(wav)
                    except: pass
                if self.sil_ms > 0:
                    self._sleep_ms(self.sil_ms)
        finally:
            self._speaking.clear()

    def say_async(self, text: str, lang: str = "en"):
        def worker():
            try:
                self.say(text, lang=lang)
            except Exception as e:
                self.log.error(f"Piper async error: {e}")
            finally:
                self._speaking.clear()
        self.stop()
        self._stop.clear()
        self._speaking.set()
        self._speak_th = threading.Thread(target=worker, daemon=True)
        self._speak_th.start()

    def say_async_stream(
        self,
        token_iter: Iterable[str],
        lang: str = "en",
        on_first_speak: Optional[Callable[[], None]] = None,
        min_chunk_chars: int = 80,
        on_done: Optional[Callable[[], None]] = None,
    ):
        """
        Stream: acumulează tokeni până la final de propoziție sau buffer >= min_chunk_chars,
        sintetizează și redă imediat (cu pauze scurte între bucăți).
        """
        def worker():
            first_spoken = False
            buf = ""
            self._speaking.set()
            try:
                for tok in token_iter:
                    if self._stop.is_set(): break
                    buf += tok

                    # taie la propoziții complete
                    parts = _SENT_SPLIT.split(buf)
                    out = []
                    if len(parts) >= 2:
                        for i in range(0, len(parts)-1, 2):
                            frag, punct = parts[i], parts[i+1]
                            s = (frag + punct).strip()
                            if s:
                                out.append(s)
                        buf = parts[-1] if (len(parts) % 2 == 1) else ""

                    # sau dacă e foarte lung și n-avem punctuație, taie la cel mai apropiat spațiu
                    if not out and len(buf) >= min_chunk_chars:
                        last_space = buf.rfind(" ")
                        if last_space > 20:
                            out.append(buf[:last_space].strip())
                            buf = buf[last_space+1:]

                    for s in out:
                        if self._stop.is_set(): break
                        if on_first_speak and not first_spoken:
                            first_spoken = True
                            try: on_first_speak()
                            except Exception: pass
                        wav = self._synth_to_wav(s, lang)
                        try:
                            self._play_wav_blocking(wav)
                        finally:
                            try: os.remove(wav)
                            except: pass
                        if self.sil_ms > 0:
                            self._sleep_ms(self.sil_ms)

                # finalizează ce-a rămas
                tail = buf.strip()
                if (not self._stop.is_set()) and tail:
                    if on_first_speak and not first_spoken:
                        first_spoken = True
                        try: on_first_speak()
                        except Exception: pass
                    wav = self._synth_to_wav(tail, lang)
                    try:
                        self._play_wav_blocking(wav)
                    finally:
                        try: os.remove(wav)
                        except: pass
            except Exception as e:
                self.log.error(f"Piper stream error: {e}")
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
            try: sd.stop()
            except Exception: pass
        self._speaking.clear()
