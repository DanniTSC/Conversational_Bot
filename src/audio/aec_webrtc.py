# src/audio/aec_webrtc.py
from __future__ import annotations
import numpy as np

class WebRTCAEC:
    """
    Stub AEC: întoarce frame-ul nemodificat.
    Înlocuim cu implementare reală (WebRTC APM) când dorim aec_mode=webrtc.
    """
    def __init__(self, sample_rate: int = 16000, frame_ms: int = 20):
        self.sr = sample_rate
        self.frame_ms = frame_ms

    def process_frame(self, pcm_i16: np.ndarray) -> np.ndarray:
        return pcm_i16

    def close(self):
        pass
