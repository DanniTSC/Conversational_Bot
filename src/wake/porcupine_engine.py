from __future__ import annotations
from typing import List, Optional
import os
import pvporcupine
import soundfile as sf
import numpy as np

class PorcupineWake:
    def __init__(
        self,
        access_key: str,
        keyword_paths: Optional[List[str]] = None,
        keywords: Optional[List[str]] = None,
        sensitivities: Optional[List[float]] = None,
        logger=None,
    ):
        self.log = logger
        ak = (access_key or "").strip() or os.getenv("PICOVOICE_ACCESS_KEY", "")
        if not ak:
            raise RuntimeError("Porcupine access_key lipsește (setează wake.porcupine.access_key sau env PICOVOICE_ACCESS_KEY).")

        kws = keyword_paths or None
        kbn = keywords or None
        if not (kws or kbn):
            raise RuntimeError("Porcupine: configurează fie 'keyword_paths', fie 'keywords' în configs/wake.yaml.")

        sens = sensitivities or [0.5] * (len(kws or kbn))
        self.ppn = pvporcupine.create(
            access_key=ak,
            keyword_paths=kws,
            keywords=kbn,
            sensitivities=sens,
        )
        self.frame_len = self.ppn.frame_length
        self.sr = self.ppn.sample_rate

        if kws:
            self.labels = [os.path.splitext(os.path.basename(p))[0] for p in kws]
        else:
            self.labels = list(kbn)

    def close(self):
        try:
            if self.ppn:
                self.ppn.delete()
        except Exception:
            pass

    def detect_in_wav(self, wav_path: str) -> Optional[str]:
        try:
            audio, sr = sf.read(wav_path, dtype="int16", always_2d=False)
        except Exception as e:
            if self.log: self.log.error(f"Porcupine: nu pot citi WAV: {e}")
            return None

        if sr != self.sr:
            if self.log: self.log.warning(f"Porcupine cere {self.sr} Hz, dar WAV are {sr} Hz. Setează audio.sample_rate={self.sr}.")
            return None

        if audio.ndim == 2:
            audio = audio.mean(axis=1).astype("int16")

        n = len(audio) - (len(audio) % self.frame_len)
        for i in range(0, n, self.frame_len):
            frame = np.array(audio[i:i+self.frame_len], dtype=np.int16)
            res = self.ppn.process(frame)
            if res >= 0:
                idx = int(res)
                return self.labels[idx] if 0 <= idx < len(self.labels) else "wake"
        return None
