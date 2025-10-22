# src/asr/engine_faster.py
from __future__ import annotations
from pathlib import Path
from typing import Dict, Any, Optional
from faster_whisper import WhisperModel

# metrics
from src.telemetry.metrics import observe_hist, asr_latency

class ASREngine:
    def __init__(
        self,
        model_size: str = "base",
        compute_type: str = "int8",     # int8 / int8_float16 / float16 / float32
        device: str = "cpu",            # cpu / cuda
        force_language: Optional[str] = None,
        beam_size: int = 1,
        vad_min_silence_ms: int = 300,
    ):
        self.force_language = (force_language or "").strip().lower() or None
        self.beam_size = int(beam_size or 1)
        self.vad_min_silence_ms = int(vad_min_silence_ms or 300)

        # Inițializează modelul
        self.model = WhisperModel(
            model_size,
            device=device,
            compute_type=compute_type,
            download_root=None,  # default cache (~/.cache/whisper)
        )
        print(f"[ASR] faster-whisper model={model_size} device={device} compute_type={compute_type} "
              f"force_language={self.force_language} vad_min_silence_ms={self.vad_min_silence_ms}")

    def transcribe(self, wav_path: str | Path, language_override: Optional[str] = None) -> Dict[str, Any]:
        lang = (language_override or self.force_language or None)
        with observe_hist(asr_latency):
            segments, info = self.model.transcribe(
                str(wav_path),
                language=lang,
                beam_size=self.beam_size,
                temperature=0.0,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": self.vad_min_silence_ms},
                # Tweak-uri de stabilitate:
                no_speech_threshold=0.6,   # filtrează „aer”
                log_prob_threshold=-0.5,   # aruncă rezultate foarte improbabile
                condition_on_previous_text=False,
            )
            text = "".join(s.text for s in segments).strip()
        out_lang = info.language or (lang or "en")
        return {"text": text, "lang": out_lang, "language_probability": getattr(info, "language_probability", 0.0)}
