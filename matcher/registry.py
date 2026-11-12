"""MLflow model registry: the trainer publishes models here, workers pick them up (DESIGN 9.4).

A registered version is a run artifact folder holding matcher.json + matcher.meta.json. The
"production" alias points at the version workers should use.
"""
import os
import tempfile
from pathlib import Path

NAME = "gstr2b-matcher"
ALIAS = "production"
EXPERIMENT = "gstr2b-matcher"


def enabled() -> bool:
    return bool(os.environ.get("MLFLOW_TRACKING_URI"))


def client():
    from mlflow import MlflowClient  # imported lazily: the api never needs mlflow

    return MlflowClient()


def production_version(c=None):
    """The ModelVersion behind the production alias, or None if nothing is promoted yet."""
    from mlflow.exceptions import MlflowException

    try:
        return (c or client()).get_model_version_by_alias(NAME, ALIAS)
    except MlflowException:
        return None


def load_version(mv):
    """Downloads a registered version and loads it. Its version label becomes r<registry no>."""
    import mlflow

    from matcher.model import MatchModel

    with tempfile.TemporaryDirectory() as tmp:  # the booster is in memory once loaded
        folder = mlflow.artifacts.download_artifacts(mv.source, dst_path=tmp)
        model = MatchModel.load(Path(folder) / "matcher.json")
    model.meta["version"] = f"r{mv.version}"
    return model


def publish(model, metrics: dict, promote: bool, tags: dict) -> str:
    """Logs a run with the model, registers it as a new version, and moves the production alias
    to it only when promote is True. Returns the registry version number."""
    import mlflow

    mlflow.set_experiment(EXPERIMENT)
    c = client()
    with tempfile.TemporaryDirectory() as tmp, mlflow.start_run() as run:
        mlflow.log_params({k: v for k, v in model.meta["params"].items()})
        mlflow.log_metrics({k: float(v) for k, v in metrics.items()})
        mlflow.set_tags({**tags, "gate": "pass" if promote else "fail"})
        model.save(Path(tmp) / "matcher.json")
        mlflow.log_artifacts(tmp, "model")
        source = f"{run.info.artifact_uri}/model"
    if not c.search_registered_models(filter_string=f"name='{NAME}'"):
        c.create_registered_model(NAME)
    mv = c.create_model_version(NAME, source, run.info.run_id,
                                tags={"gate": "pass" if promote else "fail"})
    if promote:
        c.set_registered_model_alias(NAME, ALIAS, mv.version)
    return mv.version
