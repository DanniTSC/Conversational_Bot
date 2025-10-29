# 🧠 Conversational Bot

Private, local, low-latency voice assistant with hotword, ASR, **streaming LLM → streaming TTS**, barge-in, and a tidy `/vitals` dashboard.

---

## ✨ What’s implemented (and how)

- **Wake word with safe fallback** — Porcupine hotword; if it’s missing or fails, the app switches to **text-based wake matching** without crashing.  
- **ASR with clean endpointing** — Faster-Whisper tuned for short turns; **standby** listens in tight windows; **active sessions** auto-detect RO/EN (standby prefers EN for reliable hotwords).  
- **Streaming LLM → streaming TTS** — Real-time token streaming to speech; **time-to-first-token** measured so replies feel snappy.  
- **Audio hygiene** — System echo-cancel (AEC), noise suppression, high-pass filter; **AGC off** to avoid noise pumping & false VAD triggers.  
- **No accidental “pa…” exits** — Session closes **only** on exact goodbyes (ex. „ok bye”, „gata”, „la revedere”).  
- **Observability** — Prometheus counters + a simple **/vitals** page for round-trip, ASR, TTFB, sessions, turns, errors.

---

## 🔜 To-do (next iterations)

- **Barge-in: human-voice only** — tighten gating so knocks/claps don’t interrupt; focus on voiced-only detection + slightly higher voice-duration thresholds.  
- **Instant feedback while thinking** — quick filler like “Thanks — give me a sec…” if the first token is slow, then continue streaming the real answer.  
- **Better English understanding** — run command/QA flow in **EN-focused** mode for precision (RO remains supported).  
- **Model bake-off** — compare **Phi-3 Mini (3.8B)** vs **Qwen-2.5 (3B)** vs current **Llama**; choose by scenario (snappy vs factual).  
- **Clear code docs** — docstrings & concise architecture notes per module.

---

## 🧩 Mini flow (pipeline)

**Standby & Wake** → (Porcupine **or** text fallback)  
→ **Acknowledgement** (“Yes, I’m listening.” / “Da, te ascult.”)  
→ **Record & endpoint** (VAD on silence; AEC + NS + HPF; AGC off)  
→ **ASR** (Faster-Whisper; session auto RO/EN; standby favors EN)  
→ **LLM** (streamed generation; **strict-facts** mode to avoid nonsense)  
→ **TTS** (streamed **sentence chunks**; Piper preferred, pyttsx3 fallback)  
→ **Barge-in** (if user speaks, TTS stops; return to listening)  
→ **Session end** (idle timeout **or** exact-match goodbye)

---

## 🧪 Biggest build obstacles (and fixes)

- **Echo loop (bot talks to itself)** → solved with system echo-cancel, selecting the echo-canceled mic, keeping **AGC off**, plus an **anti-echo textual guard** (ignore inputs ~85% similar to the last bot reply).  
- **False exits on “pa…”** → fixed by switching to **exact goodbye phrases only**.  
- **Barge-in firing on any noise** → still open (see To-do #1).

---

## 📊 Vitals screenshot

![Robot Vitals](src/utils/vitals.png)

