# 🧩 Code bundle export

---
## configs/asr.yaml
```yaml
   1  model_size: base
   2  compute_type: int8
   3  device: cpu
   4  beam_size: 1
   5  
   6  sample_rate: 16000
   7  block_ms: 30
   8  vad_aggressiveness: 2
   9  silence_ms_to_end: 10000
  10  max_record_seconds: 8
  11  
  12  force_language: en
```

---
## configs/audio.yaml
```yaml
   1  sample_rate: 16000
   2  block_ms: 30          # 10 / 20 / 30 ms (webrtcvad acceptă doar aceste valori)
   3  vad_aggressiveness: 2 # 0..3 (3 = mai agresiv)
   4  silence_ms_to_end: 600
   5  max_record_seconds: 30
```

---
## configs/llm.yaml
```yaml
   1  provider: ollama
   2  host: "http://127.0.0.1:11434"
   3  model: "llama3.2"
   4  max_tokens: 120
   5  temperature: 0.4
   6  language_policy: auto
   7  system_prompt: >
   8    You are a helpful assistant for a humanoid robot. That answears in romanian or english based on the language of asking
   9  default_mode: precise         
  10  strict_facts: true  #daca nu stie spune ca nu stie 
```

---
## configs/routing.yaml
```yaml
   1  rules: []
```

---
## configs/tts.yaml
```yaml
   1  backend: pyttsx3        # pyttsx3 | piper (later)
   2  rate: 180
   3  volume: 0.9
   4  voice_ro_hint: "ro"
   5  voice_en_hint: "en"
```

---
## configs/wake.yaml
```yaml
   1  wake_phrases:
   2    - "hello robot"
   3    - "hey robot"
   4    - "salut robot"
   5    - "hei robot"
   6    - "bună robot"
   7    - "buna robot"
   8  
   9  acknowledgement:
  10    ro: "Da, te ascult."
  11    en: "Yes, I'm listening."
```

---
## requirements.txt
```
   1  # Core audio I/O
   2  sounddevice==0.4.6
   3  soundfile==0.12.1
   4  webrtcvad==2.0.14
   5  PyYAML==6.0.2
   6  numpy==1.26.4
   7  
   8  # Speech-to-text (ASR)
   9  #faster-whisper==1.0.3
  10  openai-whisper==20231117
  11  
  12  # Text-to-speech (TTS)
  13  pyttsx3==2.91
  14  
  15  # LLM / HTTP
  16  requests==2.32.3
  17  
  18  # Logging / dev utilities
  19  coloredlogs==15.0.1
  20  
  21  # (Optional) quality-of-life tools
  22  tqdm==4.66.5
  23  rapidfuzz==3.9.6
```

---
## src/app.py
```python
   1  # src/app.py
   2  from src.states import BotState
   3  from src.logger import setup_logger
   4  from src.config import load_all
   5  from src.audio.input import record_until_silence
   6  from src.asr.engine_openai import ASREngine
   7  from src.llm.engine import LLMLocal
   8  from src.tts.engine import TTSLocal
   9  from src.wake import WakeDetector
  10  from src.utils.textnorm import normalize_text
  11  from pathlib import Path
  12  import time
  13  
  14  
  15  LANG_MAP = {"ro": "ro", "en": "en"}
  16  
  17  def _lang_from_code(code: str) -> str:
  18      code = (code or "en").lower()
  19      for k in LANG_MAP:
  20          if code.startswith(k):
  21              return LANG_MAP[k]
  22      return "en"
  23  
  24  def is_goodbye(text: str) -> bool:
  25      """Detectează comenzi de închidere a sesiunii (ex. 'ok bye')."""
  26      t = normalize_text(text)
  27      if not t:
  28          return False
  29      bye_phrases = [
  30          "ok bye", "okay bye", "bye", "goodbye", "stop", "cancel", "enough",
  31          "gata", "la revedere", "opreste", "oprim", "terminam", "pa"
  32      ]
  33      return any(p in t for p in bye_phrases)
  34  
  35  def main():
  36      logger = setup_logger()
  37      cfg = load_all()
  38      data_dir = Path(cfg["paths"]["data"])
  39      data_dir.mkdir(parents=True, exist_ok=True)
  40  
  41      # Engines
  42      asr = ASREngine(
  43          cfg["asr"]["model_size"],
  44          cfg["asr"]["compute_type"],
  45          cfg["asr"].get("device", "cpu"),
  46          cfg["asr"].get("force_language"),   # opțional: en/ro/None
  47      )
  48      llm = LLMLocal(cfg["llm"], logger)
  49      tts = TTSLocal(cfg["tts"], logger)
  50  
  51      # Wake detector
  52      wake = WakeDetector(cfg["wake"]["wake_phrases"])
  53      ack_ro = cfg["wake"]["acknowledgement"]["ro"]
  54      ack_en = cfg["wake"]["acknowledgement"]["en"]
  55  
  56      logger.info("🤖 Standby: spune „hello robot” sau „salut robot” ca să pornești conversația.")
  57      state = BotState.LISTENING
  58  
  59      try:
  60          while True:
  61              # ——— STANDBY: ascultă până detectează wake ———
  62              standby_cfg = dict(cfg["audio"])
  63              standby_cfg.update({
  64                  "silence_ms_to_end": 1000,   # dă timp să spui wake-ul complet
  65                  "max_record_seconds": 4,     # probe scurte în standby
  66                  "vad_aggressiveness": 3,     # mai agresiv la zgomot
  67              })
  68              standby_wav = data_dir / "cache" / "standby.wav"
  69              standby_wav.parent.mkdir(parents=True, exist_ok=True)
  70              path, dur = record_until_silence(standby_cfg, standby_wav, logger)
  71  
  72              if dur < float(cfg["audio"].get("min_valid_seconds", 0.7)):
  73                  logger.info(f"⏭️ standby prea scurt (dur={dur:.2f}s) — reiau")
  74                  continue
  75  
  76              # Forțăm EN în standby ca să evităm detectări greșite de limbă
  77              result = asr.transcribe(path, language_override="en")
  78              heard_text = (result.get("text") or "").strip()
  79              heard_lang = "en"
  80  
  81              # debug scoruri pentru wake
  82              scores = wake.debug_scores(heard_text)
  83              logger.info(f"👂 [standby:{heard_lang}] {heard_text} | wake-scores: {scores}")
  84  
  85              if not heard_text:
  86                  continue
  87  
  88              matched = wake.match(heard_text)
  89              if not matched:
  90                  continue  # nu e wake, rămânem în standby
  91  
  92              # ——— Wake confirm ———
  93              logger.info(f"🔔 Wake phrase detectată: {matched}")
  94              ack = ack_ro if heard_lang == "ro" else ack_en
  95              tts.say(ack, lang=heard_lang)
  96  
  97              # ——— SESIUNE MULTI-TURN până la "ok bye" sau timeout ———
  98              ask_cfg = dict(cfg["audio"])
  99              ask_cfg.update({
 100                  "silence_ms_to_end": 1000,   # nu tăia finalul propozițiilor
 101                  "max_record_seconds": 10,
 102                  "vad_aggressiveness": 2,     # mai iertător în conversație
 103              })
 104              session_idle_seconds = int(cfg["audio"].get("session_idle_seconds", 12))
 105              last_activity = time.time()
 106  
 107              logger.info("🟢 Sesiune activă (spune „ok bye” ca să închizi).")
 108              state = BotState.LISTENING
 109  
 110              while time.time() - last_activity < session_idle_seconds:
 111                  user_wav = data_dir / "cache" / "user_utt.wav"
 112                  path_user, dur = record_until_silence(ask_cfg, user_wav, logger)
 113  
 114                  # ignoră capturile foarte scurte (respirații, click-uri, tuse)
 115                  if dur < 0.7:
 116                      continue
 117  
 118                  state = BotState.THINKING
 119                  # dacă vrei bilingv, pune language_override=None
 120                  asr_res = asr.transcribe(path_user, language_override="en")
 121                  user_text = (asr_res.get("text") or "").strip()
 122                  user_lang = _lang_from_code(asr_res.get("lang", "en"))
 123                  logger.info(f"🧏 [{user_lang}] {user_text}")
 124  
 125                  if not user_text:
 126                      continue
 127  
 128                  # închidere sesiune pe "ok bye"
 129                  if is_goodbye(user_text):
 130                      state = BotState.SPEAKING
 131                      tts.say("Okay, bye!", lang="en")
 132                      logger.info("🔴 Sesiune închisă de utilizator (ok bye).")
 133                      break
 134  
 135                  # Răspuns normal
 136                  reply = llm.generate(user_text, lang_hint="en", mode = "precise")  # menții ENG în sesiune
 137                  logger.info(f"💬 Răspuns: {reply}")
 138  
 139                  state = BotState.SPEAKING
 140                  tts.say(reply, lang="en")
 141  
 142                  # prelungește fereastra de inactivitate la fiecare schimb valid
 143                  last_activity = time.time()
 144  
 145              # ——— ieșire din sesiune => revenire în standby ———
 146              state = BotState.LISTENING
 147              logger.info("⏳ Revenire în standby (spune din nou wake-phrase pentru o nouă sesiune).")
 148  
 149      except KeyboardInterrupt:
 150          logger.info("Bye!")
 151  
 152  if __name__ == "__main__":
 153      main()
```

---
## src/asr/engine.py
```python
   1  # src/tts/engine.py
   2  from __future__ import annotations
   3  from typing import Dict, Iterable
   4  import threading, queue, re, pyttsx3
   5  
   6  _SENT_SPLIT = re.compile(r'([.!?…]+)\s+')
   7  
   8  class TTSLocal:
   9      def __init__(self, cfg: Dict, logger):
  10          self.log = logger
  11          self.eng = pyttsx3.init()
  12          self.rate = int(cfg.get("rate", 180))
  13          self.volume = float(cfg.get("volume", 1.0))
  14          self.voice_ro_hint = (cfg.get("voice_ro_hint") or "ro").lower()
  15          self.voice_en_hint = (cfg.get("voice_en_hint") or "en").lower()
  16          self.eng.setProperty("rate", self.rate)
  17          self.eng.setProperty("volume", self.volume)
  18          self._voices = self.eng.getProperty("voices")
  19          self._stop = threading.Event()
  20          self._lock = threading.Lock()
  21          self._speak_th = None
  22  
  23      def _pick_voice(self, lang: str):
  24          target = self.voice_ro_hint if lang.startswith("ro") else self.voice_en_hint
  25          for v in self._voices:
  26              name = (getattr(v,"name","") or "").lower()
  27              _id  = (getattr(v,"id","") or "").lower()
  28              if target in name or target in _id:
  29                  return v.id
  30          return self._voices[0].id if self._voices else None
  31  
  32      def say(self, text: str, lang: str = "en"):
  33          with self._lock:
  34              self._stop.clear()
  35              vid = self._pick_voice(lang)
  36              if vid: self.eng.setProperty("voice", vid)
  37              self.eng.say(text)
  38              self.eng.runAndWait()
  39  
  40      def say_async_stream(self, token_iter: Iterable[str], lang: str = "en"):
  41          """Primește token-uri; bufează până la final de propoziție, apoi rostește."""
  42          def worker():
  43              buf = ""
  44              vid = self._pick_voice(lang)
  45              if vid: self.eng.setProperty("voice", vid)
  46              for tok in token_iter:
  47                  if self._stop.is_set(): break
  48                  buf += tok
  49                  # împărțim pe fraze; vorbim când avem un delimitator
  50                  parts = _SENT_SPLIT.split(buf)
  51                  # parts = [frag, punct, frag, punct, ... , rest]
  52                  out = []
  53                  rebuilt = ""
  54                  for i in range(0, len(parts)-1, 2):
  55                      frag, punct = parts[i], parts[i+1]
  56                      out.append((frag+punct).strip())
  57                  # restul fără delimitator rămâne în buf
  58                  if len(parts) % 2 == 1:
  59                      buf = parts[-1]
  60                  else:
  61                      buf = ""
  62                  for sentence in out:
  63                      if sentence and not self._stop.is_set():
  64                          self.eng.say(sentence)
  65                          self.eng.runAndWait()
  66              # finalul rămas
  67              if not self._stop.is_set() and buf.strip():
  68                  self.eng.say(buf.strip())
  69                  self.eng.runAndWait()
  70  
  71          self.stop()  # oprește orice vorbire anterioară
  72          self._stop.clear()
  73          self._speak_th = threading.Thread(target=worker, daemon=True)
  74          self._speak_th.start()
  75  
  76      def stop(self):
  77          with self._lock:
  78              self._stop.set()
  79              try: self.eng.stop()
  80              except Exception: pass
```

---
## src/asr/engine_faster.py
```python
   1  # src/asr/engine_faster.py
   2  from __future__ import annotations
   3  from pathlib import Path
   4  from typing import Dict, Any, Optional
   5  from faster_whisper import WhisperModel
   6  
   7  class ASREngine:
   8      def __init__(
   9          self,
  10          model_size: str = "tiny",
  11          compute_type: str = "int8",       # int8 / int8_float16 / float16 / float32
  12          device: str = "cpu",
  13          force_language: Optional[str] = None,
  14          beam_size: int = 1,
  15      ):
  16          self.force_language = (force_language or "").strip().lower() or None
  17          self.beam_size = int(beam_size or 1)
  18          self.model = WhisperModel(
  19              model_size,
  20              device=device,
  21              compute_type=compute_type,
  22          )
  23          print(f"[ASR] faster-whisper model={model_size} device={device} compute_type={compute_type} force_language={self.force_language}")
  24  
  25      def transcribe(self, wav_path: str | Path, language_override: Optional[str] = None) -> Dict[str, Any]:
  26          lang = (language_override or self.force_language or None)
  27          segments, info = self.model.transcribe(
  28              str(wav_path),
  29              language=lang,
  30              beam_size=self.beam_size,
  31              temperature=0.0,
  32              vad_filter=True,
  33              vad_parameters={"min_silence_duration_ms": 500},
  34          )
  35          text = "".join(s.text for s in segments).strip()
  36          out_lang = info.language or (lang or "en")
  37          return {"text": text, "lang": out_lang, "language_probability": getattr(info, "language_probability", 0.0)}
```

---
## src/asr/engine_openai.py
```python
   1  # src/asr/engine_openai.py
   2  from __future__ import annotations
   3  from pathlib import Path
   4  from typing import Dict, Any, Optional
   5  import whisper
   6  
   7  class ASREngine:
   8      def __init__(
   9          self,
  10          model_size: str = "tiny",
  11          compute_type: str | None = None,
  12          device: str = "cpu",
  13          force_language: Optional[str] = None,
  14      ):
  15          self.device = "cuda" if device == "cuda" else "cpu"
  16          self.fp16 = (self.device == "cuda")
  17          name = model_size if model_size in {"tiny","base","small","medium","large"} else "tiny"
  18          self.model = whisper.load_model(name, device=self.device)
  19          self.force_language = (force_language or "").strip().lower() or None
  20          print(f"[ASR] openai-whisper model={name} device={self.device} fp16={self.fp16} force_language={self.force_language}")
  21  
  22      def transcribe(self, wav_path: str | Path, language_override: Optional[str] = None) -> Dict[str, Any]:
  23          lang = (language_override or self.force_language or None)
  24          res = self.model.transcribe(
  25              str(wav_path),
  26              fp16=self.fp16,
  27              language=lang,                     # <- forțăm limba dacă e setată
  28              temperature=0.0,                   # mai puțină “imaginație”
  29              condition_on_previous_text=False,
  30              no_speech_threshold=0.6,           # filtrează “aer”
  31              logprob_threshold=-0.5,            # aruncă rezultate foarte improbabile
  32          )
  33          text = (res.get("text") or "").strip()
  34          out_lang = res.get("language") or (lang or "en")
  35          return {"text": text, "lang": out_lang, "language_probability": 0.0}
```

---
## src/audio/input.py
```python
   1  # src/audio/input.py
   2  import queue, time, struct
   3  from pathlib import Path
   4  
   5  import numpy as np
   6  import sounddevice as sd
   7  import soundfile as sf
   8  
   9  from .vad import VAD  # sau: from src.audio.vad import VAD
  10  
  11  
  12  def _float_to_int16(audio_f32: np.ndarray) -> np.ndarray:
  13      """Convert [-1, 1] float32 to int16 PCM."""
  14      audio_f32 = np.clip(audio_f32, -1.0, 1.0)
  15      return (audio_f32 * 32767.0).astype(np.int16)
  16  
  17  
  18  def record_until_silence(cfg_audio: dict, out_wav_path: Path, logger):
  19      """
  20      Înregistrează mono 16kHz și se oprește după `silence_ms_to_end` ms de liniște
  21      (detectată de VAD) sau după `max_record_seconds` (fallback).
  22      Returnează (path, durată_sec).
  23      """
  24      sr = int(cfg_audio["sample_rate"])
  25      block_ms = int(cfg_audio["block_ms"])              # 10/20/30 ms
  26      silence_ms_to_end = int(cfg_audio["silence_ms_to_end"])
  27      max_secs = int(cfg_audio["max_record_seconds"])
  28  
  29      assert block_ms in (10, 20, 30), "VAD frame must be 10/20/30 ms"
  30      block_size = int(sr * (block_ms / 1000.0))
  31  
  32      q = queue.Queue()
  33      vad = VAD(sr, cfg_audio.get("vad_aggressiveness", 2), block_ms)
  34  
  35      logger.info(f"🎤 Vorbește… (se oprește după {silence_ms_to_end}ms de liniște)")
  36      started = time.time()
  37      last_voice_ms = 0
  38      collected = []
  39  
  40      def callback(indata, frames, time_info, status):
  41          if status:
  42              logger.debug(f"Audio status: {status}")
  43          q.put(indata.copy())
  44  
  45      with sd.InputStream(channels=1, samplerate=sr, blocksize=block_size,
  46                          dtype="float32", callback=callback):
  47          while True:
  48              try:
  49                  block = q.get(timeout=0.5)  # float32 [-1,1], mono
  50              except queue.Empty:
  51                  if time.time() - started > max_secs:
  52                      break
  53                  continue
  54  
  55              pcm_i16 = _float_to_int16(block[:, 0])
  56              collected.append(pcm_i16)
  57  
  58              # VAD pe bytes little-endian
  59              pcm_bytes = struct.pack("<%dh" % len(pcm_i16), *pcm_i16)
  60              if vad.is_speech(pcm_bytes):
  61                  last_voice_ms = 0
  62              else:
  63                  last_voice_ms += block_ms
  64  
  65              if last_voice_ms >= silence_ms_to_end:
  66                  break
  67              if time.time() - started > max_secs:
  68                  break
  69  
  70      audio = np.concatenate(collected, axis=0) if collected else np.zeros(1, dtype=np.int16)
  71      out_wav_path.parent.mkdir(parents=True, exist_ok=True)
  72      sf.write(str(out_wav_path), audio, sr, subtype="PCM_16")
  73      dur = len(audio) / sr
  74      logger.info(f"✅ Înregistrare salvată: {out_wav_path} (~{dur:.2f}s)")
  75      return str(out_wav_path), dur
```

---
## src/audio/output.py
```python

```

---
## src/audio/vad.py
```python
   1  import webrtcvad
   2  
   3  class VAD:
   4      def __init__(self, sample_rate: int, aggressiveness: int = 2, frame_ms: int = 30):
   5          assert frame_ms in (10, 20, 30), "VAD frame must be 10/20/30 ms"
   6          self.sr = sample_rate
   7          self.frame_ms = frame_ms
   8          self.vad = webrtcvad.Vad(aggressiveness)
   9  
  10      def is_speech(self, pcm_bytes: bytes) -> bool:
  11          return self.vad.is_speech(pcm_bytes, self.sr)
```

---
## src/config.py
```python
   1  import os, yaml
   2  from pathlib import Path
   3  
   4  ROOT = Path(__file__).resolve().parents[1]
   5  CFG = ROOT / "configs"
   6  
   7  def load_yaml(name: str):
   8      with open(CFG / name, "r", encoding="utf-8") as f:
   9          return yaml.safe_load(f)
  10  
  11  def load_all():
  12      return {
  13          "audio": load_yaml("audio.yaml"),
  14          "asr":   load_yaml("asr.yaml"),
  15          "llm":   load_yaml("llm.yaml"),
  16          "tts":   load_yaml("tts.yaml"),
  17          "wake":  load_yaml("wake.yaml"),   
  18          "route": load_yaml("routing.yaml"),
  19          "paths": {
  20              "data": str((ROOT / "data").absolute()),
  21              "models": str((ROOT / "models").absolute()),
  22          }
  23      }
```

---
## src/llm/engine.py
```python
   1  # src/llm/engine.py
   2  from __future__ import annotations
   3  from typing import Dict, Optional
   4  import os, requests, json
   5  
   6  class LLMLocal:
   7      def __init__(self, cfg: Dict, logger):
   8          self.cfg = cfg or {}
   9          self.log = logger
  10  
  11          provider = (self.cfg.get("provider") or self.cfg.get("backend") or "rule").lower()
  12          if provider == "echo":
  13              provider = "rule"
  14          self.provider = provider
  15  
  16          self.system = self.cfg.get("system_prompt", "")
  17          self.host = self.cfg.get("host", "http://localhost:11434")
  18          self.model = self.cfg.get("model", "llama3.2")
  19          self.max_tokens = int(self.cfg.get("max_tokens", 120))
  20          self.temperature = float(self.cfg.get("temperature", 0.4))
  21  
  22          # noi:
  23          self.default_mode = (self.cfg.get("default_mode") or "precise").lower()   # precise | creative
  24          self.strict_facts = bool(self.cfg.get("strict_facts", True))
  25  
  26          self._openai = None
  27          if self.provider == "openai":
  28              try:
  29                  from openai import OpenAI
  30                  self._openai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
  31              except Exception as e:
  32                  self.log.error(f"OpenAI client indisponibil: {e}. Revin pe 'rule'.")
  33                  self.provider = "rule"
  34  
  35          self.log.info(f"LLM provider activ: {self.provider}")
  36  
  37      # === API public: poți pasa mode="precise" sau "creative" din app.py ===
  38      def generate(self, user_text: str, lang_hint: str = "en", mode: Optional[str] = None) -> str:
  39          mode = (mode or self.default_mode).lower()
  40          if self.provider == "rule":
  41              return self._rule_based(user_text, lang_hint)
  42          if self.provider == "ollama":
  43              return self._ollama_http(user_text, lang_hint, mode=mode)
  44          if self.provider == "openai" and self._openai:
  45              return self._openai_chat(user_text, lang_hint)
  46          return "No LLM provider configured."
  47  
  48      def _rule_based(self, user_text: str, lang_hint: str) -> str:
  49          if not (user_text or "").strip():
  50              return "Nu am auzit întrebarea. Poți repeta?"
  51          return f"{'Am înțeles' if lang_hint.startswith('ro') else 'I heard'}: \"{user_text}\"."
  52  
  53      def _ollama_http(self, user_text: str, lang_hint: str, mode: str = "precise") -> str:
  54          url = f"{self.host.rstrip('/')}/api/generate"
  55  
  56          # gard de siguranță în prompt
  57          if mode == "precise":
  58              safety = (
  59                  "IMPORTANT: Answer only with verified facts. "
  60                  "If you are uncertain or the information may be outdated, say "
  61                  "'Nu știu cu certitudine' and suggest checking a reliable source. "
  62                  "Never invent names, dates, or sources. Be concise."
  63              )
  64              temperature = 0.0
  65              top_p = 0.9
  66              top_k = 40
  67          else:
  68              safety = "Be helpful and friendly."
  69              temperature = self.temperature
  70              top_p = 0.95
  71              top_k = 50
  72  
  73          sys = (self.system or "").strip()
  74          preface = f"{sys}\n{safety}".strip()
  75          prompt = f"{preface}\nUser ({lang_hint}): {user_text}\nAssistant:"
  76  
  77          try:
  78              resp = requests.post(url, json={
  79                  "model": self.model,
  80                  "prompt": prompt,
  81                  "stream": False,
  82                  "options": {
  83                      "temperature": temperature,
  84                      "top_p": top_p,
  85                      "top_k": top_k,
  86                      "repeat_penalty": 1.1,
  87                      "num_predict": self.max_tokens
  88                  }
  89              }, timeout=120)
  90              resp.raise_for_status()
  91              data = resp.json()
  92              text = (data.get("response") or "").strip()
  93  
  94              # opțional: dacă strict_facts și textul pare “inventat”, întoarce fallback
  95              if self.strict_facts and not text:
  96                  return "Nu știu cu certitudine. Vrei să verific o sursă?"
  97              return text or "…"
  98          except Exception as e:
  99              self.log.error(f"Ollama HTTP error: {e}")
 100              return self._rule_based(user_text, lang_hint)
 101  
 102      def _openai_chat(self, user_text: str, lang_hint: str) -> str:
 103          try:
 104              msg = [
 105                  {"role": "system", "content": self.system or "You are concise."},
 106                  {"role": "user", "content": f"[lang={lang_hint}] {user_text}"},
 107              ]
 108              r = self._openai.chat.completions.create(
 109                  model=self.cfg.get("model", "gpt-4o-mini"),
 110                  messages=msg,
 111                  temperature=self.temperature,
 112                  max_tokens=self.max_tokens
 113              )
 114              return (r.choices[0].message.content or "").strip()
 115          except Exception as e:
 116              self.log.error(f"OpenAI error: {e}")
 117              return self._rule_based(user_text, lang_hint)
```

---
## src/logger.py
```python
   1  import logging
   2  try:
   3      import coloredlogs
   4  except Exception:
   5      coloredlogs = None
   6  
   7  def setup_logger(name: str = "convo"):
   8      logger = logging.getLogger(name)
   9      logger.setLevel(logging.INFO)
  10      if not logger.handlers:
  11          handler = logging.StreamHandler()
  12          fmt = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
  13          handler.setFormatter(logging.Formatter(fmt))
  14          logger.addHandler(handler)
  15          if coloredlogs:
  16              coloredlogs.install(level="INFO", logger=logger, fmt=fmt)
  17      return logger
```

---
## src/states.py
```python
   1  from enum import Enum, auto
   2  
   3  class BotState(Enum):
   4      LISTENING = auto()
   5      THINKING  = auto()
   6      SPEAKING  = auto()
```

---
## src/tts/engine.py
```python
   1  # src/tts/engine.py
   2  from __future__ import annotations
   3  from typing import Dict, Optional
   4  import pyttsx3
   5  
   6  
   7  class TTSLocal:
   8      """
   9      TTS simplu, offline, prin pyttsx3 (espeak-ng pe Linux).
  10      Config în tts.yaml: rate, volume, voice_ro_hint, voice_en_hint
  11      """
  12  
  13      def __init__(self, cfg: Dict, logger):
  14          self.log = logger
  15          self.eng = pyttsx3.init()
  16          self.rate = int(cfg.get("rate", 170))
  17          self.volume = float(cfg.get("volume", 1.0))
  18          self.voice_ro_hint = cfg.get("voice_ro_hint", "ro")
  19          self.voice_en_hint = cfg.get("voice_en_hint", "en")
  20          self.eng.setProperty("rate", self.rate)
  21          self.eng.setProperty("volume", self.volume)
  22          self._voices = self.eng.getProperty("voices")
  23  
  24      def _pick_voice(self, lang: str) -> Optional[str]:
  25          target = self.voice_ro_hint if lang.startswith("ro") else self.voice_en_hint
  26          target = (target or "").lower()
  27          for v in self._voices:
  28              # pe Linux (espeak-ng) id/name conțin "romanian"/"ro" sau "english"/"en"
  29              name = (getattr(v, "name", "") or "").lower()
  30              _id = (getattr(v, "id", "") or "").lower()
  31              if target and (target in name or target in _id):
  32                  return v.id
  33          # fallback: prima voce
  34          return self._voices[0].id if self._voices else None
  35  
  36      def say(self, text: str, lang: str = "en"):
  37          voice_id = self._pick_voice(lang)
  38          if voice_id:
  39              self.eng.setProperty("voice", voice_id)
  40          else:
  41              self.log.warning("⚠️ Nicio voce potrivită găsită, folosesc default.")
  42          self.eng.say(text)
  43          self.eng.runAndWait()
```

---
## src/utils/textnorm.py
```python
   1  import re
   2  import unicodedata
   3  
   4  _ROM_DIACRITICS = str.maketrans({
   5      "ă": "a", "â": "a", "î": "i", "ş": "s", "ș": "s", "ţ": "t", "ț": "t",
   6      "Ă": "a", "Â": "a", "Î": "i", "Ş": "s", "Ș": "s", "Ţ": "t", "Ț": "t",
   7  })
   8  
   9  def normalize_text(s: str) -> str:
  10      if not s:
  11          return ""
  12      s = unicodedata.normalize("NFKC", s)
  13      s = s.translate(_ROM_DIACRITICS)
  14      s = s.lower()
  15      s = re.sub(r"[^a-z0-9\s]", " ", s)
  16      s = re.sub(r"\s+", " ", s).strip()
  17      return s
```

---
## src/wake.py
```python
   1  # src/wake.py
   2  from typing import List, Optional, Tuple
   3  from src.utils.textnorm import normalize_text
   4  from rapidfuzz import fuzz
   5  
   6  class WakeDetector:
   7      def __init__(self, phrases: List[str], threshold: int = 72):
   8          self.raw = list(phrases)
   9          self.norm = [normalize_text(p) for p in phrases]
  10          self.threshold = threshold
  11  
  12      def match(self, user_text: str) -> Optional[str]:
  13          t = normalize_text(user_text)
  14          if not t: return None
  15          best: Tuple[str, int] = ("", -1)
  16          for raw, n in zip(self.raw, self.norm):
  17              score = fuzz.partial_ratio(n, t)
  18              if score > best[1]:
  19                  best = (raw, score)
  20          return best[0] if best[1] >= self.threshold else None
  21  
  22      def debug_scores(self, user_text: str):
  23          t = normalize_text(user_text)
  24          return {raw: fuzz.partial_ratio(n, t) for raw, n in zip(self.raw, self.norm)}
```
