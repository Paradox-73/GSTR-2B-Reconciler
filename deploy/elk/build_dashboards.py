"""Generates deploy/elk/kibana-export.ndjson: the data view plus the 4 dashboards in DESIGN.md 14.3.

python deploy/elk/build_dashboards.py   (then commit the ndjson; kibana-setup imports it)
Fields come from the app's JSON logs, parsed under app.* by deploy/elk/logstash.conf.
"""
import json
from pathlib import Path

OUT = Path(__file__).with_name("kibana-export.ndjson")
DATA_VIEW = "gstr2b-logs"
KIBANA = "8.15.3"


def _search(query: str) -> dict:
    return {"searchSourceJSON": json.dumps({
        "query": {"query": query, "language": "kuery"}, "filter": [],
        "indexRefName": "kibanaSavedObjectMeta.searchSourceJSON.index"})}


def _vis(vid: str, title: str, query: str, vtype: str, aggs: list, params: dict) -> dict:
    for i, a in enumerate(aggs, start=1):
        a.setdefault("id", str(i))
        a.setdefault("enabled", True)
        a.setdefault("params", {})
    return {"type": "visualization", "id": vid, "attributes": {
        "title": title, "description": "", "version": 1, "uiStateJSON": "{}",
        "visState": json.dumps({"title": title, "type": vtype, "aggs": aggs, "params": params}),
        "kibanaSavedObjectMeta": _search(query)},
        "references": [{"name": "kibanaSavedObjectMeta.searchSourceJSON.index",
                        "type": "index-pattern", "id": DATA_VIEW}]}


def count():
    return {"type": "count", "schema": "metric"}


def metric(kind, field, **extra):
    return {"type": kind, "schema": "metric", "params": {"field": field, **extra}}


def over_time():
    return {"type": "date_histogram", "schema": "segment",
            "params": {"field": "@timestamp", "interval": "auto", "min_doc_count": 1,
                       "extended_bounds": {}}}


def split(field, schema="group", size=10, order_by="1"):
    """order_by must name a single-value metric agg id (or "_key"); percentiles can't sort."""
    return {"type": "terms", "schema": schema,
            "params": {"field": field, "size": size, "order": "desc", "orderBy": order_by,
                       "missingBucket": False, "otherBucket": False}}


def line(vid, title, query, aggs, y_title, chart="line"):
    series = [{"show": True, "type": chart, "mode": "stacked" if chart == "histogram" else "normal",
               "data": {"label": y_title, "id": "1"}, "valueAxis": "ValueAxis-1",
               "drawLinesBetweenPoints": True, "lineWidth": 2, "interpolate": "linear",
               "showCircles": True}]
    params = {
        "type": chart, "grid": {"categoryLines": False}, "addTooltip": True, "addLegend": True,
        "legendPosition": "right", "times": [], "addTimeMarker": False, "labels": {},
        "categoryAxes": [{"id": "CategoryAxis-1", "type": "category", "position": "bottom",
                          "show": True, "scale": {"type": "linear"},
                          "labels": {"show": True, "filter": True, "truncate": 100},
                          "title": {}}],
        "valueAxes": [{"id": "ValueAxis-1", "name": "LeftAxis-1", "type": "value",
                       "position": "left", "show": True,
                       "scale": {"type": "linear", "mode": "normal"},
                       "labels": {"show": True, "rotate": 0, "filter": False, "truncate": 100},
                       "title": {"text": y_title}}],
        "seriesParams": series,
        "thresholdLine": {"show": False, "value": 10, "width": 1, "style": "full",
                          "color": "#E7664C"}}
    return _vis(vid, title, query, chart, aggs, params)


def pie(vid, title, query, field):
    params = {"type": "pie", "addTooltip": True, "legendDisplay": "show",
              "legendPosition": "right", "isDonut": True, "nestedLegend": False,
              "distinctColors": True, "palette": {"type": "palette", "name": "default"},
              "labels": {"show": True, "values": True, "last_level": True, "truncate": 100}}
    return _vis(vid, title, query, "pie", [count(), split(field, "segment")], params)


def table(vid, title, query, aggs):
    params = {"perPage": 10, "showPartialRows": False, "showMetricsAtAllLevels": False,
              "showTotal": False, "totalFunc": "sum", "percentageCol": ""}
    return _vis(vid, title, query, "table", aggs, params)


def big_number(vid, title, query, aggs):
    params = {"addTooltip": True, "addLegend": False, "type": "metric", "metric": {
        "percentageMode": False, "useRanges": False, "colorSchema": "Green to Red",
        "metricColorMode": "None", "colorsRange": [{"from": 0, "to": 10000}],
        "labels": {"show": True}, "invertColors": False,
        "style": {"bgFill": "#000", "bgColor": False, "labelColor": False, "subText": "",
                  "fontSize": 36}}}
    return _vis(vid, title, query, "metric", aggs, params)


REQ = 'app.event:"request"'
DONE = 'app.event:"run_completed"'
CATEGORIES = ["matched", "probable_match", "needs_review", "mismatch", "missing_in_2b",
              "missing_in_books", "itc_not_available"]

VISUALS = [
    # operations
    line("ops-requests", "Requests per endpoint", REQ,
         [count(), over_time(), split("app.path.keyword")], "requests"),
    line("ops-errors", "Errors (5xx responses and ERROR logs)",
         f"({REQ} and app.status_code >= 500) or app.level:\"ERROR\"",
         [count(), over_time(), split("app.service.keyword")], "errors", chart="histogram"),
    table("ops-latency", "Latency per endpoint (ms)", REQ,
          [metric("percentiles", "app.duration_ms", percents=[50, 95]),
           metric("max", "app.duration_ms"),
           split("app.path.keyword", "bucket", 20, order_by="2")]),
    line("ops-status", "Responses by status code", REQ,
         [count(), over_time(), split("app.status_code")], "responses", chart="histogram"),
    pie("ops-logs-per-container", "Log lines per container", "", "container.name.keyword"),
    # reconciliation
    big_number("rec-runs", "Runs completed", DONE, [count()]),
    line("rec-runs-time", "Runs over time", 'app.event:("run_completed" or "run_failed")',
         [count(), over_time(), split("app.event.keyword")], "runs", chart="histogram"),
    line("rec-duration", "Run duration (ms, p95)", DONE,
         [metric("percentiles", "app.duration_ms", percents=[95]), over_time()], "ms"),
    table("rec-categories", "Invoices per result category", DONE,
          [metric("sum", f"app.counts.{c}", customLabel=c) for c in CATEGORIES]),
    table("rec-events", "Activity", 'app.event:("upload_saved" or "run_queued" or '
          '"review_decision" or "export" or "client_created" or "runs_reaped")',
          [count(), split("app.event.keyword", "bucket")]),
    # model
    line("model-version-runs", "Runs per model version", DONE,
         [count(), over_time(), split("app.model_version.keyword")], "runs", chart="histogram"),
    table("model-auto-match", "Auto-matched by the model, per version", DONE,
          [metric("sum", "app.counts.probable_match", customLabel="probable"),
           metric("sum", "app.counts.needs_review", customLabel="needs review"),
           metric("sum", "app.counts.matched", customLabel="exact matched"),
           split("app.model_version.keyword", "bucket")]),
    pie("model-decisions", "Review decisions (accept / reject / link)",
        'app.event:"review_decision"', "app.decision.keyword"),
    table("model-gate", "Quality gate history", 'app.event:"gate_result"',
          [count(), split("app.model_version.keyword", "bucket", 50),
           split("app.passed", "bucket", 2)]),
    table("model-swaps", "Model swaps on workers", 'app.event:"model_swapped"',
          [count(), split("app.model_version.keyword", "bucket", 50),
           split("container.name.keyword", "bucket", 20)]),
    # pipeline
    line("pipe-deploys", "Deploys: containers started, by build", 'app.event:"app_started"',
         [count(), over_time(), split("app.version.keyword")], "starts", chart="histogram"),
    table("pipe-versions", "Builds seen", 'app.event:"app_started"',
          [count(), metric("min", "@timestamp", customLabel="first seen"),
           split("app.version.keyword", "bucket", 30)]),
    line("pipe-failures", "Failed runs, reaped runs and 5xx",
         f'app.event:("run_failed" or "runs_reaped") or ({REQ} and app.status_code >= 500)',
         [count(), over_time(), split("app.event.keyword")], "events", chart="histogram"),
    table("pipe-promotions", "Model promotions", 'app.event:"model_promoted"',
          [count(), split("app.model_version.keyword", "bucket", 50),
           split("app.source.keyword", "bucket", 5)]),
]

DASHBOARDS = {
    "dash-operations": ("GSTR-2B: Operations", ["ops-requests", "ops-errors", "ops-latency",
                                                "ops-status", "ops-logs-per-container"]),
    "dash-reconciliation": ("GSTR-2B: Reconciliation", ["rec-runs", "rec-runs-time",
                                                        "rec-duration", "rec-categories",
                                                        "rec-events"]),
    "dash-model": ("GSTR-2B: Model", ["model-version-runs", "model-auto-match",
                                      "model-decisions", "model-gate", "model-swaps"]),
    "dash-pipeline": ("GSTR-2B: Pipeline", ["pipe-deploys", "pipe-versions", "pipe-failures",
                                            "pipe-promotions"]),
}


def dashboard(did: str, title: str, panels: list[str]) -> dict:
    grid, refs = [], []
    for i, vid in enumerate(panels):
        grid.append({"version": KIBANA, "type": "visualization", "panelIndex": str(i),
                     "gridData": {"x": (i % 2) * 24, "y": (i // 2) * 15, "w": 24, "h": 15,
                                  "i": str(i)},
                     "embeddableConfig": {}, "panelRefName": f"panel_{i}"})
        refs.append({"name": f"panel_{i}", "type": "visualization", "id": vid})
    return {"type": "dashboard", "id": did, "attributes": {
        "title": title, "description": "", "version": 1, "timeRestore": True,
        "timeFrom": "now-24h", "timeTo": "now", "refreshInterval": {"pause": False,
                                                                     "value": 30000},
        "panelsJSON": json.dumps(grid),
        "optionsJSON": json.dumps({"useMargins": True, "syncColors": False,
                                   "hidePanelTitles": False}),
        "kibanaSavedObjectMeta": {"searchSourceJSON": json.dumps(
            {"query": {"query": "", "language": "kuery"}, "filter": []})}},
        "references": refs}


def main() -> None:
    objects = [{"type": "index-pattern", "id": DATA_VIEW, "attributes": {
        "title": "gstr2b-logs-*", "timeFieldName": "@timestamp", "name": "gstr2b logs"},
        "references": []}]
    objects += VISUALS
    known = {v["id"] for v in VISUALS}
    for did, (title, panels) in DASHBOARDS.items():
        assert set(panels) <= known, set(panels) - known
        objects.append(dashboard(did, title, panels))
    OUT.write_text("".join(json.dumps(o) + "\n" for o in objects), encoding="utf-8")
    print(f"wrote {len(objects)} objects to {OUT}")


if __name__ == "__main__":
    main()
