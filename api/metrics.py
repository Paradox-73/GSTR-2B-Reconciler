"""Prometheus metrics (#66). Names and labels are what deploy/k8s-monitoring's dashboard queries.

The api serves them on GET /metrics, the worker on :9100 (api/worker.py). Both run one process,
so the default registry is enough. Labels stay low-cardinality: route templates, never raw paths.
"""
from prometheus_client import Counter, Gauge, Histogram

HTTP_REQUESTS = Counter("http_requests_total", "HTTP requests handled by the api",
                        ["method", "route", "status"])
HTTP_DURATION = Histogram("http_request_duration_seconds", "HTTP request duration", ["route"])

RUNS = Counter("reconcile_runs", "Reconciliation runs that finished", ["status"])
RUN_SECONDS = Histogram("reconcile_run_seconds", "Reconciliation run duration",
                        buckets=(0.25, 0.5, 1, 2, 5, 10, 30, 60, 120, 300, 600))
INVOICES = Counter("reconcile_invoices", "Reconciliation results by category", ["category"])

APP_INFO = Gauge("app_info", "Running app version (git sha baked into the image)", ["version"])
MODEL_VERSION = Gauge("model_version_info", "Model version this process scores with",
                      ["version"])


def set_model_version(version: str) -> None:
    # One series at a time, so count by (version) shows the swap instead of both versions
    MODEL_VERSION.clear()
    MODEL_VERSION.labels(version=version).set(1)
