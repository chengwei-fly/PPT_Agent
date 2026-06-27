#!/usr/bin/env python
"""Monthly availability report generator (T116 / FR-024 / SC-012).

Queries Prometheus for the past month's availability, P95 latency, MTTR,
and error rate, then generates a markdown report suitable for PR to docs/.

Usage:
    python scripts/availability_report.py [--month 2026-05] [--output docs/reports/]
    python scripts/availability_report.py --prometheus-url http://localhost:9090
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Default Prometheus endpoint (local infra)
DEFAULT_PROMETHEUS_URL = "http://localhost:9090"


def _query_prometheus(base_url: str, query: str, ts: float | None = None) -> dict:
    """Query Prometheus instant query API."""
    import urllib.request
    import urllib.parse

    params = {"query": query}
    if ts:
        params["time"] = str(ts)
    url = f"{base_url}/api/v1/query?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"[warn] Prometheus query failed: {e}", file=sys.stderr)
        return {"status": "error", "error": str(e)}


def _query_range(base_url: str, query: str, start: float, end: float, step: str = "1h") -> dict:
    """Query Prometheus range query API."""
    import urllib.request
    import urllib.parse

    params = {
        "query": query,
        "start": str(start),
        "end": str(end),
        "step": step,
    }
    url = f"{base_url}/api/v1/query_range?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"[warn] Prometheus range query failed: {e}", file=sys.stderr)
        return {"status": "error", "error": str(e)}


def _extract_scalar(result: dict) -> float | None:
    """Extract scalar value from Prometheus response."""
    if result.get("status") != "success":
        return None
    data = result.get("data", {})
    if data.get("resultType") == "vector" and data.get("result"):
        return float(data["result"][0]["value"][1])
    return None


def generate_report(
    month: str | None = None,
    prometheus_url: str = DEFAULT_PROMETHEUS_URL,
    output_dir: str = "docs/reports",
) -> str:
    """Generate monthly availability report markdown."""
    now = datetime.utcnow()
    if month:
        report_month = datetime.strptime(month, "%Y-%m")
    else:
        # Default to previous month
        first_of_this = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        report_month = first_of_this - timedelta(days=1)
        report_month = report_month.replace(day=1)

    month_start = report_month.replace(hour=0, minute=0, second=0, microsecond=0)
    if month_start.month == 12:
        month_end = month_start.replace(year=month_start.year + 1, month=1)
    else:
        month_end = month_end = month_start.replace(month=month_start.month + 1)

    start_ts = month_start.timestamp()
    end_ts = month_end.timestamp()

    month_label = report_month.strftime("%Y-%m")

    # Query metrics
    availability_result = _query_prometheus(
        prometheus_url,
        f'avg_over_time(up{{job="pptagent"}}[30d])',
        end_ts,
    )
    p95_latency_result = _query_prometheus(
        prometheus_url,
        'histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[30d]))',
        end_ts,
    )
    error_rate_result = _query_prometheus(
        prometheus_url,
        'rate(http_requests_total{status=~"5.."}[30d]) / rate(http_requests_total[30d])',
        end_ts,
    )
    queue_length_result = _query_prometheus(
        prometheus_url,
        "queue_length",
        end_ts,
    )

    availability = _extract_scalar(availability_result)
    p95_latency = _extract_scalar(p95_latency_result)
    error_rate = _extract_scalar(error_rate_result)
    queue_length = _extract_scalar(queue_length_result)

    # Build report
    lines = [
        f"# Availability Report — {month_label}",
        "",
        f"**Generated**: {now.strftime('%Y-%m-%d %H:%M UTC')}",
        f"**Period**: {month_start.strftime('%Y-%m-%d')} — {month_end.strftime('%Y-%m-%d')}",
        f"**Prometheus**: {prometheus_url}",
        "",
        "## Summary",
        "",
        "| Metric | Value | Target | Status |",
        "|--------|-------|--------|--------|",
    ]

    def _status(val: float | None, target: float, op: str = ">=") -> str:
        if val is None:
            return "N/A"
        if op == ">=":
            return "PASS" if val >= target else "FAIL"
        if op == "<=":
            return "PASS" if val <= target else "FAIL"
        return "N/A"

    av_pct = f"{availability * 100:.3f}%" if availability is not None else "N/A"
    p95_ms = f"{p95_latency * 1000:.0f}ms" if p95_latency is not None else "N/A"
    err_pct = f"{error_rate * 100:.3f}%" if error_rate is not None else "N/A"
    q_len = f"{queue_length:.0f}" if queue_length is not None else "N/A"

    lines.extend([
        f"| Availability (uptime) | {av_pct} | >= 99.9% | {_status(availability, 0.999)} |",
        f"| P95 Latency | {p95_ms} | <= 5000ms | {_status(p95_latency, 5.0, '<=')} |",
        f"| Error Rate (5xx) | {err_pct} | <= 0.1% | {_status(error_rate, 0.001, '<=')} |",
        f"| Queue Length (snapshot) | {q_len} | <= 10 | {_status(queue_length, 10, '<=')} |",
        "",
        "## SLA Compliance",
        "",
    ])

    # SC-012: Monthly availability >= 99.9%
    if availability is not None:
        if availability >= 0.999:
            lines.append("- SC-012: **PASS** — Availability >= 99.9%")
        else:
            lines.append(f"- SC-012: **FAIL** — Availability {av_pct} < 99.9%")
    else:
        lines.append("- SC-012: **N/A** — No availability data")

    lines.extend([
        "",
        "## Recommendations",
        "",
    ])

    if availability is not None and availability < 0.999:
        lines.append("- Investigate uptime incidents; target 99.9% availability")
    if p95_latency is not None and p95_latency > 5.0:
        lines.append("- P95 latency exceeds 5s target; profile slow endpoints")
    if error_rate is not None and error_rate > 0.001:
        lines.append("- Error rate exceeds 0.1%; review 5xx logs for root causes")
    if not any([
        availability is not None and availability < 0.999,
        p95_latency is not None and p95_latency > 5.0,
        error_rate is not None and error_rate > 0.001,
    ]):
        lines.append("- All metrics within target. No action required.")

    lines.append("")
    report = "\n".join(lines)

    # Write to file
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    report_file = out_path / f"availability-{month_label}.md"
    report_file.write_text(report, encoding="utf-8")
    print(f"[report] Written to {report_file}")

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate monthly availability report")
    parser.add_argument("--month", help="Report month (YYYY-MM format)")
    parser.add_argument("--prometheus-url", default=DEFAULT_PROMETHEUS_URL)
    parser.add_argument("--output", default="docs/reports")
    args = parser.parse_args()

    report = generate_report(
        month=args.month,
        prometheus_url=args.prometheus_url,
        output_dir=args.output,
    )
    print(report)


if __name__ == "__main__":
    main()
