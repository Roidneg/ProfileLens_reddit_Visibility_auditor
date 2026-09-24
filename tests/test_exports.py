import csv
import io
import json

from profilelens.demo import demo_report
from profilelens.exports import report_to_csv, report_to_json


def test_csv_export_redacts_full_body_by_default():
    report = demo_report()
    rows = list(csv.DictReader(io.StringIO(report_to_csv(report).decode("utf-8"))))
    assert len(rows) == len(report.rows)
    assert "status" in rows[0]


def test_json_export_contains_metadata_and_results():
    report = demo_report()
    payload = json.loads(report_to_json(report).decode("utf-8"))
    assert payload["metadata"]["username"] == "demo_account"
    assert len(payload["results"]) == len(report.rows)
    assert payload["metadata"]["summary"]
