# tests/autotest_audio.py
from __future__ import annotations
import os, time, math, threading
from pathlib import Path

import numpy as np
import sounddevice as sd

from src.core.logger import setup_logger
from src.core.config import load_all
from src.audio.input import record_until_silence
from src.audio.barge import BargeInListener
from src.tts.engine import TTSLocal


def banner(title: str):
    print("\n" + "=" * 72)
    print(f"🔎 {title}")
    print("=" * 72)


def wait_countdown(sec: int = 3, note: str | None = None):
    if note:
        print(note)
    for i in range(sec, 0, -1):
        print(f"  {i}…")
        time.sleep(1)


def result(ok: bool, msg_ok: str, msg_bad: str):
    print(("✅ " + msg_ok) if ok else ("❌ " + msg_bad))
    return ok


def play_metronome(seconds=8, bpm=60, sr=16000, click_ms=8, amp=0.12):
    """Generates quiet clicks to speakers. Headphones recommended."""
    click_len = int(sr * (click_ms / 1000.0))
    t = np.arange(click_len) / sr
    # short sine burst shaped by exp decay
    click = (np.sin(2 * np.pi * 1200 * t) * np.exp(-t * 40)).astype(np.float32)
    click *= amp

    total = int(sr * seconds)
    out = np.zeros(total, dtype=np.float32)
    interval_s = 60.0 / bpm
    positions = []
    pos = 0
    while pos < seconds:
        positions.append(pos)
        pos += interval_s
    for p in positions:
        i = int(p * sr)
        if i + click_len < total:
            out[i:i+click_len] += click

    def _play():
        sd.play(out, sr)
        sd.wait()
    th = threading.Thread(target=_play, daemon=True)
    th.start()
    return th


def main():
    logger = setup_logger("autotest")
    cfg = load_all()
    audio = dict(cfg["audio"])

    data_dir = Path(cfg["paths"]["data"])
    (data_dir / "autotest").mkdir(parents=True, exist_ok=True)

    # Summary collection
    passed = []

    # ---------------------------------------------------------------------
    banner("TEST 1 — Silence should NOT produce a saved recording")
    input("Please ensure a quiet room, then press ENTER… ")
    tcfg = dict(audio)
    tcfg["max_record_seconds"] = 8
    tcfg["silence_ms_to_end"] = audio.get("silence_ms_to_end", 1400)
    out1 = data_dir / "autotest" / "test1_silence.wav"
    path, voice_sec = record_until_silence(tcfg, out1, logger)
    file_exists = Path(path).exists()
    ok = (voice_sec < float(audio.get("min_valid_seconds", 1.1))) and (not file_exists)
    passed.append(result(
        ok,
        f"No file saved and voice={voice_sec:.2f}s < min_valid ({audio.get('min_valid_seconds', 1.1):.2f}s).",
        f"Unexpected save or too much voice: file_exists={file_exists}, voice={voice_sec:.2f}s."
    ))

    # ---------------------------------------------------------------------
    banner("TEST 2 — 2s sentence should create exactly one useful utterance")
    print('Say: "Azi testez robotul, unu doi trei" as one sentence (~2s).')
    wait_countdown(3, "Starting recording in:")
    out2 = data_dir / "autotest" / "test2_sentence.wav"
    tcfg2 = dict(audio)
    # normal session params
    path2, voice_sec2 = record_until_silence(tcfg2, out2, logger)
    file2 = Path(path2).exists()
    ok2 = file2 and (voice_sec2 >= 1.0) and (voice_sec2 <= 4.0)
    passed.append(result(
        ok2,
        f"Saved one utterance with voice={voice_sec2:.2f}s.",
        f"Either no file or invalid voice duration: exists={file2}, voice={voice_sec2:.2f}s."
    ))

    # ---------------------------------------------------------------------
    banner("TEST 3 — Quiet metronome should NOT trigger speech")
    print("Playing a quiet metronome in your speakers. Use HEADPHONES if possible.")
    th = play_metronome(seconds=8, bpm=60, sr=audio["sample_rate"], click_ms=8, amp=0.10)
    out3 = data_dir / "autotest" / "test3_metronome.wav"
    tcfg3 = dict(audio)
    tcfg3["max_record_seconds"] = 8
    # slightly strict end silence to avoid endless wait
    tcfg3["silence_ms_to_end"] = max(1000, int(audio.get("silence_ms_to_end", 1400)))
    path3, voice_sec3 = record_until_silence(tcfg3, out3, logger)
    th.join(timeout=1.0)
    file3 = Path(path3).exists()
    ok3 = (voice_sec3 < float(audio.get("min_valid_seconds", 1.1))) and (not file3)
    passed.append(result(
        ok3,
        f"No save on metronome: voice={voice_sec3:.2f}s.",
        f"Metronome caused speech: voice={voice_sec3:.2f}s, file_exists={file3}."
    ))

    # ---------------------------------------------------------------------
    banner("TEST 4 — Barge-in should NOT trigger on desk taps/noise")
    print("We'll speak TTS for ~6–8s. For 2 seconds, tap lightly on the desk/wheels.")
    print("It SHOULD NOT stop.")
    tts = TTSLocal(cfg["tts"], logger)
    long_text = (
        "Acesta este un text de test pentru verificarea robustății barge in. "
        "Ar trebui să pot vorbi în continuare fără să fiu întrerupt de zgomote scurte."
    )
    # start speaking async
    speaking = tts.say_async_stream(iter([long_text]), lang="ro", min_chunk_chars=60)

    # start barge listener
    barge = BargeInListener(audio, logger)
    trig = False
    start = time.time()
    tap_window = 2.5
    wait_countdown(2, "Start tapping softly in:")
    while tts.is_speaking() and (time.time() - start) < tap_window:
        need = int(audio.get("barge_min_voice_ms", 700))
        if barge.heard_speech(need_ms=need):
            trig = True
            break
        time.sleep(0.03)
    tts.stop()
    barge.close()
    ok4 = (trig is False)
    passed.append(result(
        ok4,
        "No barge-in triggered on taps/noise.",
        "Barge-in TRIGGERED on taps — increase barge_min_voice_ms or check mic placement."
    ))

    # ---------------------------------------------------------------------
    banner("TEST 5 — Barge-in SHOULD trigger when you speak ≥0.7s")
    print('TTS will play again. After it starts, say clearly: "Stai" or begin a normal sentence.')
    print("Speak for ~1 second continuously. It SHOULD stop.")
    speaking = tts.say_async_stream(iter([long_text]), lang="ro", min_chunk_chars=60)
    barge = BargeInListener(audio, logger)
    trig2 = False
    start = time.time()
    # allow up to 6s for you to speak
    while tts.is_speaking() and (time.time() - start) < 6.0:
        need = int(audio.get("barge_min_voice_ms", 700))
        if barge.heard_speech(need_ms=need):
            trig2 = True
            tts.stop()
            break
        time.sleep(0.03)
    # safety stop
    tts.stop()
    barge.close()
    ok5 = trig2 is True
    passed.append(result(
        ok5,
        "Barge-in triggered correctly on your voice.",
        "Did not detect your speech — reduce barge_min_voice_ms or check input device."
    ))

    # ---------------------------------------------------------------------
    banner("SUMMARY")
    total_ok = sum(1 for p in passed if p)
    total = len(passed)
    print(f"Passed {total_ok}/{total} tests.")
    if total_ok == total:
        print("🎉 All good! Your anti-spam + barge-in configuration looks solid.")
    else:
        print("ℹ️ You can tweak in configs/audio.yaml: min_valid_seconds, silence_ms_to_end, barge_* params.")
        print("   Also verify OS input device (avoid monitor/loopback) and disable AGC in OS/apps.")


if __name__ == "__main__":
    # Tip: run from repo root
    #   python -m tests.autotest_audio
    main()
