# src/llm/engine.py
from __future__ import annotations
from typing import Dict
import os, requests, json

class LLMLocal:
    def __init__(self, cfg: Dict, logger):
        self.cfg = cfg or {}
        self.log = logger

        # Acceptă fie "provider", fie "backend" (alias)
        provider = (self.cfg.get("provider") or self.cfg.get("backend") or "rule").lower()
        if provider == "echo":
            provider = "rule"
        self.provider = provider

        self.system = self.cfg.get("system_prompt", "")
        self.host = self.cfg.get("host", "http://localhost:11434")
        self.model = self.cfg.get("model", "llama3.1:8b-instruct")
        self.max_tokens = int(self.cfg.get("max_tokens", 120))
        self.temperature = float(self.cfg.get("temperature", 0.4))

        # OpenAI optional
        self._openai = None
        if self.provider == "openai":
            try:
                from openai import OpenAI
                self._openai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            except Exception as e:
                self.log.error(f"OpenAI client indisponibil: {e}. Revin pe 'rule'.")
                self.provider = "rule"

        self.log.info(f"LLM provider activ: {self.provider}")

    def generate(self, user_text: str, lang_hint: str = "en") -> str:
        if self.provider == "rule":
            return self._rule_based(user_text, lang_hint)
        if self.provider == "ollama":
            return self._ollama_http(user_text, lang_hint)
        if self.provider == "openai" and self._openai:
            return self._openai_chat(user_text, lang_hint)
        return "No LLM provider configured."

    def _rule_based(self, user_text: str, lang_hint: str) -> str:
        if not (user_text or "").strip():
            return "Nu am auzit întrebarea. Poți repeta?"
        return f"{'Am înțeles' if lang_hint.startswith('ro') else 'I heard'}: \"{user_text}\"."

    def _ollama_http(self, user_text: str, lang_hint: str) -> str:
        url = f"{self.host.rstrip('/')}/api/generate"
        prompt = f"{self.system}\nUser ({lang_hint}): {user_text}\nAssistant:"
        try:
            resp = requests.post(url, json={
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": self.temperature,
                    "num_predict": self.max_tokens
                }
            }, timeout=120)
            resp.raise_for_status()
            data = resp.json()
            # pentru /api/generate, răspunsul e în "response"
            return (data.get("response") or "").strip() or "…"
        except Exception as e:
            self.log.error(f"Ollama HTTP error: {e}")
            return self._rule_based(user_text, lang_hint)

    def _openai_chat(self, user_text: str, lang_hint: str) -> str:
        try:
            msg = [
                {"role": "system", "content": self.system or "You are concise."},
                {"role": "user", "content": f"[lang={lang_hint}] {user_text}"},
            ]
            r = self._openai.chat.completions.create(
                model=self.cfg.get("model", "gpt-4o-mini"),
                messages=msg,
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )
            return (r.choices[0].message.content or "").strip()
        except Exception as e:
            self.log.error(f"OpenAI error: {e}")
            return self._rule_based(user_text, lang_hint)
