# src/audio/input.py
import queue, time, struct
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

from .vad import VAD  # sau: from src.audio.vad import VAD


def _float_to_int16(audio_f32: np.ndarray) -> np.ndarray:
    """Convert [-1, 1] float32 to int16 PCM."""
    audio_f32 = np.clip(audio_f32, -1.0, 1.0)
    return (audio_f32 * 32767.0).astype(np.int16)


def record_until_silence(cfg_audio: dict, out_wav_path: Path, logger):
    """
    Înregistrează mono 16kHz și se oprește după `silence_ms_to_end` ms de liniște
    (detectată de VAD) sau după `max_record_seconds` (fallback).
    Returnează (path, durată_sec).
    """
    sr = int(cfg_audio["sample_rate"])
    block_ms = int(cfg_audio["block_ms"])              # 10/20/30 ms
    silence_ms_to_end = int(cfg_audio["silence_ms_to_end"])
    max_secs = int(cfg_audio["max_record_seconds"])

    assert block_ms in (10, 20, 30), "VAD frame must be 10/20/30 ms"
    block_size = int(sr * (block_ms / 1000.0))

    q = queue.Queue()
    vad = VAD(sr, cfg_audio.get("vad_aggressiveness", 2), block_ms)

    logger.info(f"🎤 Vorbește… (se oprește după {silence_ms_to_end}ms de liniște)")
    started = time.time()
    last_voice_ms = 0
    collected = []

    def callback(indata, frames, time_info, status):
        if status:
            logger.debug(f"Audio status: {status}")
        q.put(indata.copy())

    with sd.InputStream(channels=1, samplerate=sr, blocksize=block_size,
                        dtype="float32", callback=callback):
        while True:
            try:
                block = q.get(timeout=0.5)  # float32 [-1,1], mono
            except queue.Empty:
                if time.time() - started > max_secs:
                    break
                continue

            pcm_i16 = _float_to_int16(block[:, 0])
            collected.append(pcm_i16)

            # VAD pe bytes little-endian
            pcm_bytes = struct.pack("<%dh" % len(pcm_i16), *pcm_i16)
            if vad.is_speech(pcm_bytes):
                last_voice_ms = 0
            else:
                last_voice_ms += block_ms

            if last_voice_ms >= silence_ms_to_end:
                break
            if time.time() - started > max_secs:
                break

    audio = np.concatenate(collected, axis=0) if collected else np.zeros(1, dtype=np.int16)
    out_wav_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out_wav_path), audio, sr, subtype="PCM_16")
    dur = len(audio) / sr
    logger.info(f"✅ Înregistrare salvată: {out_wav_path} (~{dur:.2f}s)")
    return str(out_wav_path), dur
