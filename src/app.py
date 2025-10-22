# src/app.py
from src.core.states import BotState
from src.core.logger import setup_logger
from src.core.config import load_all
from src.audio.input import record_until_silence
from src.audio.barge import BargeInListener
from src.asr import make_asr
from src.llm.engine import LLMLocal
from src.tts.engine import TTSLocal
from src.core.wake import WakeDetector
from src.utils.textnorm import normalize_text
from pathlib import Path
import time
from rapidfuzz import fuzz

from src.telemetry.metrics import (
    boot_metrics, round_trip, wake_triggers, sessions_started,
    sessions_ended, interactions, unknown_answer, errors_total,
    tts_speak_calls
)

LANG_MAP = {"ro": "ro", "en": "en"}

def _lang_from_code(code: str) -> str:
    code = (code or "en").lower()
    for k in LANG_MAP:
        if code.startswith(k):
            return LANG_MAP[k]
    return "en"

def is_goodbye(text: str) -> bool:
    t = normalize_text(text)
    if not t:
        return False
    bye_phrases = [
        "ok bye", "okay bye", "bye", "goodbye", "stop", "cancel", "enough",
        "gata", "la revedere", "opreste", "oprim", "terminam", "pa"
    ]
    return any(p in t for p in bye_phrases)

def main():
    logger = setup_logger()
    addr, port = boot_metrics()
    logger.info(f"📈 Metrics UI: http://{addr}:{port}/vitals  |  Prometheus: http://{addr}:{port}/metrics")
    cfg = load_all()
    data_dir = Path(cfg["paths"]["data"])
    data_dir.mkdir(parents=True, exist_ok=True)

    # Engines
    asr = make_asr(cfg["asr"], logger)
    llm = LLMLocal(cfg["llm"], logger)
    tts = TTSLocal(cfg["tts"], logger)

    # Wake detector
    wake = WakeDetector(cfg["wake"]["wake_phrases"])
    ack_ro = cfg["wake"]["acknowledgement"]["ro"]
    ack_en = cfg["wake"]["acknowledgement"]["en"]

    logger.info("🤖 Standby: spune „hello robot” sau „salut robot” ca să pornești conversația.")
    state = BotState.LISTENING
    last_bot_reply = ""  # pentru filtrul anti-eco

    try:
        while True:
            # ——— STANDBY: ascultă până detectează wake ———
            standby_cfg = dict(cfg["audio"])
            standby_cfg.update({
                "silence_ms_to_end": 1000,
                "max_record_seconds": 4,
                "vad_aggressiveness": 3,
            })
            standby_wav = data_dir / "cache" / "standby.wav"
            standby_wav.parent.mkdir(parents=True, exist_ok=True)
            path, dur = record_until_silence(standby_cfg, standby_wav, logger)

            if dur < float(cfg["audio"].get("min_valid_seconds", 0.7)):
                logger.info(f"⏭️ standby prea scurt (dur={dur:.2f}s) — reiau")
                continue

            # Forțăm EN în standby ca să evităm detectări greșite de limbă
            result = asr.transcribe(path, language_override="en")
            heard_text = (result.get("text") or "").strip()
            heard_lang = "en"

            scores = wake.debug_scores(heard_text)
            logger.info(f"👂 [standby:{heard_lang}] {heard_text} | wake-scores: {scores}")

            if not heard_text:
                continue

            matched = wake.match(heard_text)
            if not matched:
                continue

            # ——— Wake confirm ———
            logger.info(f"🔔 Wake phrase detectată: {matched}")
            wake_triggers.inc()
            ack = ack_ro if heard_lang == "ro" else ack_en
            tts_speak_calls.inc()
            tts.say(ack, lang=heard_lang)

            # ——— SESIUNE MULTI-TURN ———
            ask_cfg = dict(cfg["audio"])
            ask_cfg.update({
                "silence_ms_to_end": int(cfg["audio"].get("silence_ms_to_end", 600)),
                "max_record_seconds": int(cfg["audio"].get("max_record_seconds", 6)),
                "vad_aggressiveness": int(cfg["audio"].get("vad_aggressiveness", 3)),
            })
            session_idle_seconds = int(cfg["audio"].get("session_idle_seconds", 12))
            last_activity = time.time()

            logger.info("🟢 Sesiune activă (spune „ok bye” ca să închizi).")
            state = BotState.LISTENING
            sessions_started.inc()

            while time.time() - last_activity < session_idle_seconds:
                user_wav = data_dir / "cache" / "user_utt.wav"
                path_user, dur = record_until_silence(ask_cfg, user_wav, logger)

                if dur < float(cfg["audio"].get("min_valid_seconds", 0.5)):
                    continue

                state = BotState.THINKING

                # ——— ASR: strict RO/EN ———
                asr_res = None
                user_text = ""
                user_lang = "en"
                try:
                    if hasattr(asr, "transcribe_ro_en"):
                        asr_res = asr.transcribe_ro_en(path_user)
                    else:
                        asr_res = asr.transcribe(path_user, language_override="en")
                    user_text = (asr_res.get("text") or "").strip()
                    user_lang = asr_res.get("lang", "en")
                    if user_lang not in ("ro", "en"):
                        user_lang = "en"
                except Exception:
                    asr_res = {"text": "", "lang": "en"}
                    user_text = ""
                    user_lang = "en"

                logger.info(f"🧏 [{user_lang}] {user_text}")

                # ——— Anti-eco textual: ignoră dacă seamănă cu ce tocmai a spus robotul ———
                try:
                    ut = normalize_text(user_text)
                    bt = normalize_text(last_bot_reply)
                    if len(ut) > 8 and len(bt) > 8:
                        sim = fuzz.partial_ratio(ut, bt)
                        if sim >= 85:
                            logger.info(f"🔇 Ignor input (eco TTS) sim={sim}")
                            continue
                except Exception:
                    pass

                if not user_text:
                    continue

                # închidere sesiune pe "ok bye"
                if is_goodbye(user_text):
                    state = BotState.SPEAKING
                    tts_speak_calls.inc()
                    tts.say("Bine, pa!" if user_lang == "ro" else "Okay, bye!", lang=user_lang)
                    logger.info("🔴 Sesiune închisă de utilizator (ok bye).")
                    break

                # ——— STREAMING: LLM → TTS ———
                interactions.inc()
                rt_start = time.perf_counter()

                # capturăm ce spune botul pentru filtrul anti-eco la tura următoare
                reply_buf = []
                def _capture(gen):
                    for tok in gen:
                        reply_buf.append(tok)
                        yield tok

                token_iter_raw = llm.generate_stream(user_text, lang_hint=user_lang, mode="precise")
                token_iter = _capture(token_iter_raw)

                def _mark_tts_start():
                    round_trip.observe(time.perf_counter() - rt_start)

                state = BotState.SPEAKING
                #  (opțional) bucăți mai mici -> întreruperi mai „snappy”
                tts.say_async_stream(
                    token_iter,
                    lang=user_lang,
                    on_first_speak=_mark_tts_start,
                    min_chunk_chars=60,
                )

                # BARGE-IN: ascultă în paralel; dacă detectează voce umană ≥ 300ms, oprește TTS
                barge = BargeInListener(cfg["audio"], logger)
                try:
                    while tts.is_speaking():
                        if barge.heard_speech(need_ms=300):
                            logger.info("⛔ Barge-in detectat — opresc TTS și trec la listening.")
                            tts.stop()
                            break
                        time.sleep(0.03)
                finally:
                    barge.close()


                last_bot_reply = "".join(reply_buf)
                last_activity = time.time()

            # ——— ieșire din sesiune => revenire în standby ———
            state = BotState.LISTENING
            logger.info("⏳ Revenire în standby (spune din nou wake-phrase pentru o nouă sesiune).")
            sessions_ended.inc()

    except KeyboardInterrupt:
        logger.info("Bye!")
    except Exception as e:
        errors_total.inc()
        logger.exception(f"Fatal error: {e}")

if __name__ == "__main__":
    main()
