"""The pair-scoring model: an XGBoost booster plus a small metadata file next to it."""
import json
from pathlib import Path

import numpy as np
import xgboost as xgb

from matcher.features import NAMES, features
from matcher.models import Invoice

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "models" / "matcher.json"


class MatchModel:
    def __init__(self, booster: xgb.Booster, meta: dict):
        if meta.get("features") != NAMES:
            raise ValueError("model was trained on a different feature list; retrain it")
        self.booster, self.meta = booster, meta

    @property
    def version(self) -> str:
        return self.meta["version"]

    def score(self, pairs: list[tuple[Invoice, Invoice]]) -> list[float]:
        if not pairs:
            return []
        x = np.array([features(b, g) for b, g in pairs], dtype=np.float32)
        return self.booster.predict(xgb.DMatrix(x, feature_names=NAMES)).tolist()

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.booster.save_model(path)
        meta_path(path).write_text(json.dumps(self.meta, indent=1) + "\n", encoding="utf-8",
                                   newline="\n")

    @classmethod
    def load(cls, path: str | Path = DEFAULT_PATH) -> "MatchModel":
        booster = xgb.Booster()
        booster.load_model(path)
        return cls(booster, json.loads(meta_path(Path(path)).read_text(encoding="utf-8")))


def meta_path(model_path: Path) -> Path:
    return model_path.with_name(model_path.stem + ".meta.json")
