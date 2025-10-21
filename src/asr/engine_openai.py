# src/asr/engine_openai.py
from __future__ import annotations
from pathlib import Path
from typing import Dict, Any, Optional
import whisper

# metrics
from src.telemetry.metrics import observe_hist, asr_latency

class ASREngine:
    def __init__(
        self,
        model_size: str = "tiny",
        compute_type: str | None = None,
        device: str = "cpu",
        force_language: Optional[str] = None,
    ):
        self.device = "cuda" if device == "cuda" else "cpu"
        self.fp16 = (self.device == "cuda")
        name = model_size if model_size in {"tiny","base","small","medium","large"} else "tiny"
        self.model = whisper.load_model(name, device=self.device)
        self.force_language = (force_language or "").strip().lower() or None
        print(f"[ASR] openai-whisper model={name} device={self.device} fp16={self.fp16} force_language={self.force_language}")

    def transcribe(self, wav_path: str | Path, language_override: Optional[str] = None) -> Dict[str, Any]:
        lang = (language_override or self.force_language or None)
        with observe_hist(asr_latency):
            res = self.model.transcribe(
                str(wav_path),
                fp16=self.fp16,
                language=lang,
                temperature=0.0,
                condition_on_previous_text=False,
                no_speech_threshold=0.6,
                logprob_threshold=-0.5,
            )
        text = (res.get("text") or "").strip()
        out_lang = res.get("language") or (lang or "en")
        return {"text": text, "lang": out_lang, "language_probability": 0.0}
