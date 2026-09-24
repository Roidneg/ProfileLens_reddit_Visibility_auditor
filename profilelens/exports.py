"""Portable report exports."""

from __future__ import annotations

import csv
import io
import json

from .models import AuditReport


def report_to_csv(report: AuditReport, *, include_body: bool = False) -> bytes:
    """Serialize result rows to UTF-8 CSV bytes."""

    rows = [row.to_dict(include_body=include_body) for row in report.rows]
    output = io.StringIO(newline="")
    if not rows:
        output.write("comment_id,status\r\n")
        return output.getvalue().encode("utf-8")
    writer = csv.DictWriter(output, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def report_to_json(report: AuditReport, *, include_body: bool = False) -> bytes:
    """Serialize the report, methodology metadata, and rows to UTF-8 JSON."""

    payload = report.to_dict(include_body=include_body)
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
