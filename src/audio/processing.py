# src/audio/processing.py
from __future__ import annotations
from typing import Optional
import numpy as np

class AudioEffects:
    """
    NS/AGC/HPF simple, per-frame (int16).
    - HPF: DC blocker (y[n] = x[n] - x[n-1] + r*y[n-1], r≈0.995)
    - NS: noise gate blând (~-50 dBFS)
    - AGC: nivelare către un RMS-țintă, cu clamp pe factor
    Nu introduce dependențe grele; latență ~0.
    """

    def __init__(self, ns: bool = True, agc: bool = True, hpf: bool = True):
        self.ns = ns
        self.agc = agc
        self.hpf = hpf
        # state pentru HPF
        self._x1 = 0.0
        self._y1 = 0.0
        self._r = 0.995  # coef. DC blocker

        # AGC
        self._target_rms = 0.05   # ~-26 dBFS țintă „confort”
        self._agc_max_gain = 6.0  # max 6x (~+15.6 dB)
        self._agc_min_gain = 0.5  # -6 dB
        self._agc_smooth = 0.2    # smoothing (0..1), 1 = instant

        self._gain = 1.0

    def _apply_hpf(self, x: np.ndarray) -> np.ndarray:
        # int16 -> float32
        xf = x.astype(np.float32) / 32768.0
        y = np.empty_like(xf)
        x1 = self._x1
        y1 = self._y1
        r = self._r
        for i in range(len(xf)):
            yn = xf[i] - x1 + r * y1
            y[i] = yn
            x1 = xf[i]
            y1 = yn
        self._x1, self._y1 = x1, y1
        # back to int16
        y = np.clip(y * 32768.0, -32768, 32767).astype(np.int16)
        return y

    def _apply_ns(self, x: np.ndarray) -> np.ndarray:
        # noise gate simplu: dacă RMS < thr, atenuăm cu -20 dB
        xf = x.astype(np.float32) / 32768.0
        rms = float(np.sqrt(np.mean(xf * xf)) + 1e-9)
        thr = 0.003  # ~ -50 dBFS
        if rms < thr:
            xf *= 0.1  # -20 dB
        y = np.clip(xf * 32768.0, -32768, 32767).astype(np.int16)
        return y

    def _apply_agc(self, x: np.ndarray) -> np.ndarray:
        xf = x.astype(np.float32) / 32768.0
        rms = float(np.sqrt(np.mean(xf * xf)) + 1e-9)
        if rms > 0:
            desired_gain = self._target_rms / rms
            desired_gain = float(np.clip(desired_gain, self._agc_min_gain, self._agc_max_gain))
            # smooth
            self._gain = (1 - self._agc_smooth) * self._gain + self._agc_smooth * desired_gain
        y = np.clip(xf * self._gain, -1.0, 1.0)
        return (y * 32768.0).astype(np.int16)

    def process_frame(self, pcm_i16: np.ndarray) -> np.ndarray:
        y = pcm_i16
        try:
            if self.hpf:
                y = self._apply_hpf(y)
            if self.ns:
                y = self._apply_ns(y)
            if self.agc:
                y = self._apply_agc(y)
        except Exception:
            # fail-safe: dacă ceva nu merge, trecem frame-ul nemodificat
            return pcm_i16
        return y
