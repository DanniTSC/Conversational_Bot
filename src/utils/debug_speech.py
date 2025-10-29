from __future__ import annotations
from pathlib import Path
from datetime import datetime
from typing import Iterable, Generator, Optional

class DebugSpeech:
    """
    Colectează ce intră/iese în pipeline:
    - asr.txt          -> ce a auzit ASR
    - llm_stream.txt   -> token cu token (pe măsură ce vin)
    - spoken_text.txt  -> tot textul trimis spre TTS (concat)
    - session.log      -> timpi, praguri, evenimente
    """
    def __init__(self, base_dir: Path, lang: str, logger):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.lang = lang
        self.logger = logger
        self._buf = []
        self._ttft_ms: Optional[float] = None
        self._started_tts = False

        self._asr_f = (self.base_dir / "00_asr.txt").open("w", encoding="utf-8")
        self._llm_f = (self.base_dir / "10_llm_stream.txt").open("w", encoding="utf-8")
        self._spoken_f = (self.base_dir / "20_spoken_text.txt").open("w", encoding="utf-8")
        self._sess_f = (self.base_dir / "session.log").open("a", encoding="utf-8")

        self._log(f"# Session {datetime.now().isoformat(timespec='seconds')} lang={lang}")

    def _log(self, msg: str):
        self._sess_f.write(msg.rstrip() + "\n")
        self._sess_f.flush()
        self.logger.debug(msg)

    def write_asr(self, text: str):
        self._asr_f.write((text or "").rstrip() + "\n")
        self._asr_f.flush()
        self._log(f"[ASR] {text}")

    def on_first_token(self, ttft_seconds: float):
        self._ttft_ms = ttft_seconds * 1000.0
        self._log(f"[LLM] TTFT={self._ttft_ms:.1f} ms")

    def on_token(self, tok: str):
        if not tok:
            return
        self._buf.append(tok)
        self._llm_f.write(tok)
        self._llm_f.flush()

    def on_tts_start(self):
        self._started_tts = True
        self._log("[TTS] start")

    def on_tts_end(self):
        self._log("[TTS] end")

    def tee(self, gen: Iterable[str]) -> Generator[str, None, None]:
        """
        Împachetează generatorul de tokeni: loghează și relay-uiește mai departe.
        """
        first = True
        import time
        t0 = time.perf_counter()
        for tok in gen:
            if first:
                first = False
                ttft = time.perf_counter() - t0
                # dacă nu vine din wrap_stream_for_first_token, măcar aproximăm aici
                if self._ttft_ms is None:
                    self.on_first_token(ttft)
            self.on_token(tok)
            yield tok

    def finish(self):
        text = "".join(self._buf)
        self._spoken_f.write(text)
        self._spoken_f.flush()
        self._log(f"[SPOKEN] {len(text)} chars")
        # close files
        for f in (self._asr_f, self._llm_f, self._spoken_f, self._sess_f):
            try:
                f.close()
            except Exception:
                pass
