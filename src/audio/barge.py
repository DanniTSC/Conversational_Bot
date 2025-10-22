# src/audio/barge.py
from __future__ import annotations
import sounddevice as sd
import numpy as np, queue, time, struct
from .vad import VAD
from .devices import choose_input_device

class BargeInListener:
    def __init__(self, cfg_audio: dict, logger):
        self.log = logger
        self.sr = int(cfg_audio["sample_rate"])
        self.block_ms = int(cfg_audio["block_ms"])
        self.block = int(self.sr * (self.block_ms / 1000.0))
        self.dev_index = choose_input_device(
            prefer_echo_cancel=bool(cfg_audio.get("prefer_echo_cancel", True)),
            hint=str(cfg_audio.get("input_device_hint", "") or ""),
            logger=logger
        )
        self.vad = VAD(self.sr, cfg_audio.get("vad_aggressiveness", 2), self.block_ms)
        self.q = queue.Queue()
        self._open_stream()
        self._voiced_ms = 0

    def _open_stream(self):
        def cb(indata, frames, time_info, status):
            try: self.q.put_nowait(indata.copy())
            except: pass
        self.stream = sd.InputStream(
            channels=1, samplerate=self.sr, blocksize=self.block,
            dtype="float32", callback=cb, device=self.dev_index
        )
        self.stream.start()

    def heard_speech(self, need_ms=300) -> bool:
        # „ronțăie” rapid niște cadre și acumulează vocea
        deadline = time.time() + 0.02
        while time.time() < deadline:
            try:
                block = self.q.get_nowait()
            except queue.Empty:
                break
            pcm = np.clip(block[:, 0], -1, 1)
            pcm_i16 = (pcm * 32767.0).astype(np.int16)
            if self.vad.is_speech(struct.pack("<%dh" % len(pcm_i16), *pcm_i16)):
                self._voiced_ms += self.block_ms
            else:
                self._voiced_ms = 0
            if self._voiced_ms >= need_ms:
                self._voiced_ms = 0
                return True
        return False

    def close(self):
        try:
            self.stream.stop(); self.stream.close()
        except Exception:
            pass
