import yaml


def test_configs_load():
    for path in ("config/matching.yaml", "config/quality_gate.yaml"):
        with open(path) as f:
            assert yaml.safe_load(f)
