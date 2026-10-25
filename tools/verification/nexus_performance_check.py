"""NEXUS 只读性能检查：延迟、并发、响应大小和采集指标。"""
import argparse
import concurrent.futures
import json
import statistics
import time

import requests


def percentile(values, fraction):
    values = sorted(values)
    return values[min(len(values) - 1, round((len(values) - 1) * fraction))]


def timed_get(url):
    started = time.perf_counter()
    response = requests.get(url, timeout=20)
    elapsed = (time.perf_counter() - started) * 1000
    return response.status_code, elapsed, len(response.content), response.content


def summarize(rows):
    times = [row[1] for row in rows]
    return {
        "requests": len(rows),
        "status_ok": all(row[0] == 200 for row in rows),
        "mean_ms": round(statistics.mean(times), 2),
        "median_ms": round(statistics.median(times), 2),
        "p95_ms": round(percentile(times, 0.95), 2),
        "max_ms": round(max(times), 2),
        "payload_bytes": max(row[2] for row in rows),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://192.168.110.54:3002")
    parser.add_argument("--sequential", type=int, default=30)
    parser.add_argument("--concurrent", type=int, default=24)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--label", default="baseline")
    args = parser.parse_args()
    url = args.base.rstrip("/") + "/api/events"
    sequential = [timed_get(url) for _ in range(args.sequential)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        concurrent_rows = list(pool.map(lambda _: timed_get(url), range(args.concurrent)))
    payload = json.loads(sequential[-1][3])
    result = {
        "label": args.label,
        "sequential": summarize(sequential),
        "concurrent": summarize(concurrent_rows),
        "roam_events": payload["roam"]["count"],
        "anomalies": payload["anomalies"]["total"],
        "ap_stats": len(payload["roam"].get("apStats", [])),
    }
    metrics = requests.get("http://192.168.110.54:9108/metrics", timeout=10).text
    for line in metrics.splitlines():
        if line.startswith(("reyee_exporter_collect_success ", "reyee_exporter_collect_duration_seconds ", "reyee_exporter_last_collect_timestamp_seconds ")):
            result[line.split()[0]] = float(line.split()[1])
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
