# src/asr/engine_openai.py
from __future__ import annotations
from pathlib import Path
from typing import Dict, Any
import whisper

class ASREngine:
    """
    ASR pe openai-whisper (Torch). Compatibil cu semnătura existentă:
      ASREngine(model_size, compute_type, device)
    """
    def __init__(self, model_size: str = "tiny", compute_type: str | None = None, device: str = "cpu"):
        self.device = "cuda" if device == "cuda" else "cpu"
        # pe CPU, fp16 trebuie dezactivat
        self.fp16 = (self.device == "cuda")
        # tiny/base/small/medium/large
        name = model_size if model_size in {"tiny","base","small","medium","large"} else "tiny"
        self.model = whisper.load_model(name, device=self.device)

    def transcribe(self, wav_path: str | Path) -> Dict[str, Any]:
        res = self.model.transcribe(str(wav_path), fp16=self.fp16, language=None)
        text = (res.get("text") or "").strip()
        lang = res.get("language") or "en"
        return {"text": text, "lang": lang, "language_probability": 0.0}
