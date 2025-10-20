from src.states import BotState
from src.logger import setup_logger
from src.config import load_all
from src.audio.input import record_until_silence
from src.asr.engine_openai import ASREngine
from src.llm.engine import LLMLocal
from src.tts.engine import TTSLocal
from src.wake import WakeDetector
from pathlib import Path


LANG_MAP = {"ro": "ro", "en": "en"}

def _lang_from_code(code: str) -> str:
    code = (code or "en").lower()
    for k in LANG_MAP:
        if code.startswith(k):
            return LANG_MAP[k]
    return "en"

def main():
    logger = setup_logger()
    cfg = load_all()
    data_dir = Path(cfg["paths"]["data"])
    data_dir.mkdir(parents=True, exist_ok=True)

    # Engines
    asr = ASREngine(cfg["asr"]["model_size"], cfg["asr"]["compute_type"], cfg["asr"].get("device", "cpu"))
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
            standby_wav = data_dir / "cache" / "standby.wav"
            standby_wav.parent.mkdir(parents=True, exist_ok=True)
            path, _ = record_until_silence(cfg["audio"], standby_wav, logger)

            result = asr.transcribe(path)
            heard_text = result["text"]
            heard_lang = _lang_from_code(result.get("lang", "en"))
            # debug scoruri
            scores = wake.debug_scores(heard_text)
            logger.info(f"👂 [standby:{heard_lang}] {heard_text} | wake-scores: {scores}")

            if not heard_text:
                continue

            logger.info(f"👂 [standby:{heard_lang}] {heard_text}")
            matched = wake.match(heard_text)
            if not matched:
                continue  # nu e wake, rămânem în standby

            # ——— Wake confirm ———
            logger.info(f"🔔 Wake phrase detectată: {matched}")
            ack = ack_ro if heard_lang == "ro" else ack_en
            tts.say(ack, lang=heard_lang)

            # ——— UN TUR DE CONVERSAȚIE: user întreabă, bot răspunde ———
            user_wav = data_dir / "cache" / "user_utt.wav"
            path_user, _ = record_until_silence(cfg["audio"], user_wav, logger)

            state = BotState.THINKING
            asr_res = asr.transcribe(path_user)
            user_text = asr_res["text"]
            user_lang = _lang_from_code(asr_res.get("lang", "en"))
            logger.info(f"🧏 [{user_lang}] {user_text}")

            if not user_text:
                logger.info("N-am înțeles întrebarea. Revin în standby.")
                continue

            reply = llm.generate(user_text, lang_hint=user_lang)
            logger.info(f"💬 Răspuns: {reply}")

            state = BotState.SPEAKING
            tts.say(reply, lang=user_lang)

            # ——— revenim în standby după un singur schimb ———
            state = BotState.LISTENING
            logger.info("⏳ Standby (spune din nou wake-phrase pentru următoarea întrebare).")

    except KeyboardInterrupt:
        logger.info("Bye!")

if __name__ == "__main__":
    main()
