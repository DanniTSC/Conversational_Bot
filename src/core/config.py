import yaml
from pathlib import Path
from typing import Dict, Any
import os, re

# Suntem în src/core/config.py -> urcăm două nivele: core -> src -> (root)
ROOT = Path(__file__).resolve().parents[2]
CFG = ROOT / "configs"

# --- interpolare ENV pentru stringuri din YAML: ${VAR} sau $VAR ---
_ENV_VAR = re.compile(r"\$\{([^}]+)\}|\$([A-Za-z_][A-Za-z0-9_]*)")

def _expand_env_in_obj(obj):
    if isinstance(obj, dict):
        return {k: _expand_env_in_obj(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand_env_in_obj(v) for v in obj]
    if isinstance(obj, str):
        def repl(m):
            var = m.group(1) or m.group(2)
            return os.getenv(var, "")
        return _ENV_VAR.sub(repl, obj)
    return obj

def load_yaml(name: str):
    # name = "audio.yaml", "asr.yaml", etc. (NU cu "configs/")
    with open(CFG / name, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return _expand_env_in_obj(data)

def load_all() -> Dict[str, Any]:
    raw = {
        "audio": load_yaml("audio.yaml"),
        "asr":   load_yaml("asr.yaml"),
        "llm":   load_yaml("llm.yaml"),
        "tts":   load_yaml("tts.yaml"),
        "wake":  load_yaml("wake.yaml"),
        "route": load_yaml("routing.yaml"),
        "paths": {
            "data": str((ROOT / "data").absolute()),
            "models": str((ROOT / "models").absolute()),
        }
    }
    from src.core.config_schema import validate_all
    return validate_all(raw)
