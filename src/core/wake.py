# src/wake.py
from typing import List, Optional, Tuple
from src.utils.textnorm import normalize_text
from rapidfuzz import fuzz

class WakeDetector:
    def __init__(self, phrases: List[str], threshold: int = 72):
        self.raw = list(phrases)
        self.norm = [normalize_text(p) for p in phrases]
        self.threshold = threshold

    def match(self, user_text: str) -> Optional[str]:
        t = normalize_text(user_text)
        if not t: return None
        best: Tuple[str, int] = ("", -1)
        for raw, n in zip(self.raw, self.norm):
            score = fuzz.partial_ratio(n, t)
            if score > best[1]:
                best = (raw, score)
        return best[0] if best[1] >= self.threshold else None

    def debug_scores(self, user_text: str):
        t = normalize_text(user_text)
        return {raw: fuzz.partial_ratio(n, t) for raw, n in zip(self.raw, self.norm)}
