# src/config_schema.py
from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional, List, Dict, Any

class AudioCfg(BaseModel):
    sample_rate: int = Field(16000, ge=8000, le=48000)
    block_ms: int = Field(30)
    vad_aggressiveness: int = Field(2, ge=0, le=3)
    silence_ms_to_end: int = Field(600, ge=100, le=5000)
    max_record_seconds: int = Field(30, ge=1, le=300)
    session_idle_seconds: Optional[int] = Field(12, ge=3, le=120)
    min_valid_seconds: Optional[float] = Field(0.7, ge=0.0, le=3.0)

    @field_validator("block_ms")
    @classmethod
    def check_block_ms(cls, v: int):
        if v not in (10, 20, 30):
            raise ValueError("audio.block_ms must be one of: 10, 20, 30")
        return v

class ASRCfg(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    model_size: str = Field("base")
    compute_type: Optional[str] = Field("int8")
    device: str = Field("cpu")
    beam_size: Optional[int] = Field(1, ge=1, le=8)
    force_language: Optional[str] = None

class LLMCfg(BaseModel):
    provider: str = Field("ollama")
    host: str = Field("http://127.0.0.1:11434")
    model: str = Field("llama3.2")
    max_tokens: int = Field(120, ge=16, le=4096)
    temperature: float = Field(0.4, ge=0.0, le=1.5)
    language_policy: Optional[str] = Field("auto")
    system_prompt: Optional[str] = ""
    default_mode: Optional[str] = Field("precise")
    strict_facts: Optional[bool] = Field(True)

class TTSCfg(BaseModel):
    backend: str = Field("pyttsx3")
    rate: int = Field(180, ge=60, le=400)
    volume: float = Field(0.9, ge=0.0, le=1.0)
    voice_ro_hint: Optional[str] = Field("ro")
    voice_en_hint: Optional[str] = Field("en")

class WakeCfg(BaseModel):
    wake_phrases: List[str]
    acknowledgement: Dict[str, str]

class RouteCfg(BaseModel):
    rules: List[Dict[str, Any]] = []

class PathsCfg(BaseModel):
    data: str
    models: str

class AppCfg(BaseModel):
    audio: AudioCfg
    asr: ASRCfg
    llm: LLMCfg
    tts: TTSCfg
    wake: WakeCfg
    route: RouteCfg
    paths: PathsCfg

def validate_all(raw: dict) -> dict:
    """Returnează dict validat (cu valori normalizate). Ridică ValueError dacă invalid."""
    model = AppCfg(**raw)
    return model.model_dump()
