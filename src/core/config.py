import yaml
from pathlib import Path
from typing import Dict, Any

# Suntem în src/core/config.py -> urcăm două nivele: core -> src -> (root)
ROOT = Path(__file__).resolve().parents[2]
CFG = ROOT / "configs"

def load_yaml(name: str):
    # name = "audio.yaml", "asr.yaml", etc. (NU cu "configs/")
    with open(CFG / name, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

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
