import webrtcvad

class VAD:
    def __init__(self, sample_rate: int, aggressiveness: int = 2, frame_ms: int = 30):
        assert frame_ms in (10, 20, 30), "VAD frame must be 10/20/30 ms"
        self.sr = sample_rate
        self.frame_ms = frame_ms
        self.vad = webrtcvad.Vad(aggressiveness)

    def is_speech(self, pcm_bytes: bytes) -> bool:
        return self.vad.is_speech(pcm_bytes, self.sr)
