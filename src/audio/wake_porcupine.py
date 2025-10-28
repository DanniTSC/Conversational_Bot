# src/audio/wake_porcupine.py
from __future__ import annotations
import queue, time
from typing import Optional
import numpy as np
import sounddevice as sd

from .devices import choose_input_device

def wait_for_wake(
    cfg_audio: dict,
    access_key: str,
    keyword_path: str,
    sensitivity: float = 0.6,
    logger=None,
    timeout_seconds: Optional[float] = None,
) -> bool:
    """
    Blochează până detectează wake-word cu Porcupine.
    Returnează True dacă s-a detectat, False pe eroare/timeout.
    """
    try:
        import pvporcupine as pv
    except Exception as e:
        if logger: logger.error(f"Porcupine indisponibil: {e}")
        return False

    porcupine = None
    stream = None
    q = queue.Queue(maxsize=16)

    try:
        porcupine = pv.create(
            access_key=access_key,
            keyword_paths=[keyword_path],
            sensitivities=[float(sensitivity)],
        )
        sr = porcupine.sample_rate
        frame_len = porcupine.frame_length

        dev_index = choose_input_device(
            prefer_echo_cancel=bool(cfg_audio.get("prefer_echo_cancel", True)),
            hint=str(cfg_audio.get("input_device_hint", "") or ""),
            logger=logger
        )

        if logger:
            logger.info(f"🎧 Standby (Porcupine) — sr={sr}, frame={frame_len}, sens={sensitivity}")

        def cb(indata, frames, time_info, status):
            # indata: int16 mono (dacă cerem dtype="int16")
            if status and logger:
                logger.debug(f"Porcupine input status: {status}")
            try:
                q.put_nowait(indata.copy())
            except queue.Full:
                try: q.get_nowait()
                except Exception: pass
                try: q.put_nowait(indata.copy())
                except Exception: pass

        stream = sd.InputStream(
            channels=1,
            samplerate=sr,
            blocksize=frame_len,
            dtype="int16",
            callback=cb,
            device=dev_index
        )
        stream.start()

        t0 = time.time()
        while True:
            try:
                block = q.get(timeout=0.5)  # shape: (frame_len, 1) int16
            except queue.Empty:
                if timeout_seconds and (time.time() - t0) > timeout_seconds:
                    if logger: logger.info("⏳ Porcupine timeout în standby.")
                    return False
                continue

            # aplatizează pe 1-D
            if block.ndim == 2:
                pcm_i16 = block[:, 0]
            else:
                pcm_i16 = block

            # Porcupine vrea int16 1-D de lungime frame_len
            if len(pcm_i16) != frame_len:
                # în cazuri rare, re-sample blocul
                pcm_i16 = pcm_i16[:frame_len].astype("int16")

            res = porcupine.process(pcm_i16)
            if res >= 0:
                if logger: logger.info("🔔 Wake (Porcupine) detectată.")
                return True

    except KeyboardInterrupt:
        if logger: logger.info("Stop (CTRL+C).")
        return False
    except Exception as e:
        if logger: logger.error(f"Porcupine runtime error: {e}")
        return False
    finally:
        try:
            if stream:
                stream.stop(); stream.close()
        except Exception:
            pass
        try:
            if porcupine:
                porcupine.delete()
        except Exception:
            pass
