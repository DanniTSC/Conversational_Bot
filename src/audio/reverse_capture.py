# src/audio/reverse_capture.py
from __future__ import annotations
import sounddevice as sd
import numpy as np, queue

class ReverseCapture:
    def __init__(self, device_index, samplerate, block_size, logger=None):
        self.device = device_index
        self.sr = samplerate
        self.block = block_size
        self.q = queue.Queue(maxsize=100)
        self.logger = logger
        self.stream = None

    def start(self):
        def cb(indata, frames, time_info, status):
            if status and self.logger:
                self.logger.debug(f"Monitor status: {status}")
            try:
                self.q.put_nowait(indata.copy())
            except queue.Full:
                try: self.q.get_nowait()
                except: pass
                self.q.put_nowait(indata.copy())

        self.stream = sd.InputStream(
            channels=1, samplerate=self.sr, blocksize=self.block,
            dtype="float32", callback=cb, device=self.device
        )
        self.stream.start()

    def get_frame_i16(self):
        try:
            block = self.q.get_nowait()
            return np.clip(block[:, 0] * 32767.0, -32768, 32767).astype(np.int16)
        except queue.Empty:
            return np.zeros(self.block, dtype=np.int16)

    def stop(self):
        try:
            if self.stream:
                self.stream.stop()
                self.stream.close()
        except Exception:
            pass
