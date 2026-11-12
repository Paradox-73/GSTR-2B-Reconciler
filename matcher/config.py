from pathlib import Path

import yaml

DEFAULT = Path(__file__).resolve().parent.parent / "config" / "matching.yaml"


def load(path: str | Path = DEFAULT) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)
