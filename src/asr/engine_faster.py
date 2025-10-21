# src/asr/engine_faster.py
from __future__ import annotations
from pathlib import Path
from typing import Dict, Any, Optional
from faster_whisper import WhisperModel

class ASREngine:
    def __init__(
        self,
        model_size: str = "tiny",
        compute_type: str = "int8",       # int8 / int8_float16 / float16 / float32
        device: str = "cpu",
        force_language: Optional[str] = None,
        beam_size: int = 1,
    ):
        self.force_language = (force_language or "").strip().lower() or None
        self.beam_size = int(beam_size or 1)
        self.model = WhisperModel(
            model_size,
            device=device,
            compute_type=compute_type,
        )
        print(f"[ASR] faster-whisper model={model_size} device={device} compute_type={compute_type} force_language={self.force_language}")

    def transcribe(self, wav_path: str | Path, language_override: Optional[str] = None) -> Dict[str, Any]:
        lang = (language_override or self.force_language or None)
        segments, info = self.model.transcribe(
            str(wav_path),
            language=lang,
            beam_size=self.beam_size,
            temperature=0.0,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
        )
        text = "".join(s.text for s in segments).strip()
        out_lang = info.language or (lang or "en")
        return {"text": text, "lang": out_lang, "language_probability": getattr(info, "language_probability", 0.0)}
