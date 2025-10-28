# src/core/wake.py
from typing import List, Optional, Tuple, Dict, Any
from rapidfuzz import fuzz
from src.utils.textnorm import normalize_text

class _FuzzyWake:
    def __init__(self, phrases: List[str], threshold: int = 72):
        self.raw = list(phrases or [])
        self.norm = [normalize_text(p) for p in (phrases or [])]
        self.threshold = int(threshold)

    def match(self, user_text: str) -> Optional[str]:
        t = normalize_text(user_text)
        if not t:
            return None
        best: Tuple[str, int] = ("", -1)
        for raw, n in zip(self.raw, self.norm):
            score = fuzz.partial_ratio(n, t)
            if score > best[1]:
                best = (raw, score)
        return best[0] if best[1] >= self.threshold else None

    def debug_scores(self, user_text: str):
        t = normalize_text(user_text or "")
        return {raw: fuzz.partial_ratio(n, t) for raw, n in zip(self.raw, self.norm)}

class WakeDetector:
    """
    Facade peste mai multe motoare:
      - engine = 'asr'       -> fuzzy match pe text (ce aveai deja)
      - engine = 'porcupine' -> KWS offline, direct pe WAV (fără ASR)
    """
    def __init__(self, cfg: Dict[str, Any], logger=None):
        self.cfg = cfg or {}
        self.log = logger
        self.engine = (self.cfg.get("engine") or "asr").lower()
        self.fuzzy = _FuzzyWake(self.cfg.get("wake_phrases") or [], threshold=int(self.cfg.get("threshold", 72)))
        self.porc = None

        if self.engine == "porcupine":
            try:
                from src.wake.porcupine_engine import PorcupineWake
                pcfg = self.cfg.get("porcupine") or {}
                self.porc = PorcupineWake(
                    access_key=pcfg.get("access_key", ""),
                    keyword_paths=pcfg.get("keyword_paths"),
                    keywords=pcfg.get("keywords"),
                    sensitivities=pcfg.get("sensitivities"),
                    logger=logger,
                )
            except Exception as e:
                if logger: logger.error(f"Porcupine indisponibil: {e}. Revin pe engine=asr.")
                self.engine = "asr"
                self.porc = None

    # pentru engine=asr
    def match(self, user_text: str) -> Optional[str]:
        return self.fuzzy.match(user_text)

    def debug_scores(self, user_text: str):
        return self.fuzzy.debug_scores(user_text)

    # pentru engine=porcupine
    def detect_in_wav(self, wav_path: str) -> Optional[str]:
        if self.engine == "porcupine" and self.porc:
            return self.porc.detect_in_wav(wav_path)
        return None

    def close(self):
        try:
            if self.porc:
                self.porc.close()
        except Exception:
            pass
