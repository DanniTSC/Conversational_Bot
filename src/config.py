import os, yaml
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "configs"

def load_yaml(name: str):
    with open(CFG / name, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def load_all():
    return {
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
