import re
import unicodedata

_ROM_DIACRITICS = str.maketrans({
    "ă": "a", "â": "a", "î": "i", "ş": "s", "ș": "s", "ţ": "t", "ț": "t",
    "Ă": "a", "Â": "a", "Î": "i", "Ş": "s", "Ș": "s", "Ţ": "t", "Ț": "t",
})

def normalize_text(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = s.translate(_ROM_DIACRITICS)
    s = s.lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s
