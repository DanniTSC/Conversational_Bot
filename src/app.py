# src/app.py
from src.core.states import BotState
from src.core.logger import setup_logger
from src.core.config import load_all
from src.audio.input import record_until_silence
from src.asr.engine_openai import ASREngine
from src.llm.engine import LLMLocal
from src.tts.engine import TTSLocal
from src.core.wake import WakeDetector
from src.telemetry.metrics import boot_metrics
from src.utils.textnorm import normalize_text
from pathlib import Path
import time


LANG_MAP = {"ro": "ro", "en": "en"}

def _lang_from_code(code: str) -> str:
    code = (code or "en").lower()
    for k in LANG_MAP:
        if code.startswith(k):
            return LANG_MAP[k]
    return "en"

def is_goodbye(text: str) -> bool:
    """Detectează comenzi de închidere a sesiunii (ex. 'ok bye')."""
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
    asr = ASREngine(
        cfg["asr"]["model_size"],
        cfg["asr"]["compute_type"],
        cfg["asr"].get("device", "cpu"),
        cfg["asr"].get("force_language"),   # opțional: en/ro/None
    )
    llm = LLMLocal(cfg["llm"], logger)
    tts = TTSLocal(cfg["tts"], logger)

    # Wake detector
    wake = WakeDetector(cfg["wake"]["wake_phrases"])
    ack_ro = cfg["wake"]["acknowledgement"]["ro"]
    ack_en = cfg["wake"]["acknowledgement"]["en"]

    logger.info("🤖 Standby: spune „hello robot” sau „salut robot” ca să pornești conversația.")
    state = BotState.LISTENING

    try:
        while True:
            # ——— STANDBY: ascultă până detectează wake ———
            standby_cfg = dict(cfg["audio"])
            standby_cfg.update({
                "silence_ms_to_end": 1000,   # dă timp să spui wake-ul complet
                "max_record_seconds": 4,     # probe scurte în standby
                "vad_aggressiveness": 3,     # mai agresiv la zgomot
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

            # debug scoruri pentru wake
            scores = wake.debug_scores(heard_text)
            logger.info(f"👂 [standby:{heard_lang}] {heard_text} | wake-scores: {scores}")

            if not heard_text:
                continue

            matched = wake.match(heard_text)
            if not matched:
                continue  # nu e wake, rămânem în standby

            # ——— Wake confirm ———
            logger.info(f"🔔 Wake phrase detectată: {matched}")
            ack = ack_ro if heard_lang == "ro" else ack_en
            tts.say(ack, lang=heard_lang)

            # ——— SESIUNE MULTI-TURN până la "ok bye" sau timeout ———
            ask_cfg = dict(cfg["audio"])
            ask_cfg.update({
                "silence_ms_to_end": 1000,   # nu tăia finalul propozițiilor
                "max_record_seconds": 10,
                "vad_aggressiveness": 2,     # mai iertător în conversație
            })
            session_idle_seconds = int(cfg["audio"].get("session_idle_seconds", 12))
            last_activity = time.time()

            logger.info("🟢 Sesiune activă (spune „ok bye” ca să închizi).")
            state = BotState.LISTENING

            while time.time() - last_activity < session_idle_seconds:
                user_wav = data_dir / "cache" / "user_utt.wav"
                path_user, dur = record_until_silence(ask_cfg, user_wav, logger)

                # ignoră capturile foarte scurte (respirații, click-uri, tuse)
                if dur < 0.7:
                    continue

                state = BotState.THINKING
                # dacă vrei bilingv, pune language_override=None
                asr_res = asr.transcribe(path_user, language_override="en")
                user_text = (asr_res.get("text") or "").strip()
                user_lang = _lang_from_code(asr_res.get("lang", "en"))
                logger.info(f"🧏 [{user_lang}] {user_text}")

                if not user_text:
                    continue

                # închidere sesiune pe "ok bye"
                if is_goodbye(user_text):
                    state = BotState.SPEAKING
                    tts.say("Okay, bye!", lang="en")
                    logger.info("🔴 Sesiune închisă de utilizator (ok bye).")
                    break

                # Răspuns normal
                reply = llm.generate(user_text, lang_hint="en", mode = "precise")  # menții ENG în sesiune
                logger.info(f"💬 Răspuns: {reply}")

                state = BotState.SPEAKING
                tts.say(reply, lang="en")

                # prelungește fereastra de inactivitate la fiecare schimb valid
                last_activity = time.time()

            # ——— ieșire din sesiune => revenire în standby ———
            state = BotState.LISTENING
            logger.info("⏳ Revenire în standby (spune din nou wake-phrase pentru o nouă sesiune).")

    except KeyboardInterrupt:
        logger.info("Bye!")

if __name__ == "__main__":
    main()
