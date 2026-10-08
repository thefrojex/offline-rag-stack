"""Measure retrieval hit rate and answer latency against a running stack.

Retrieval hit: the expected file is among the returned sources AND one of those
chunks contains the evidence phrase. Answer match is a crude keyword check and
is reported separately; it is not a correctness judgement.

Usage: uv run python scripts/eval.py [--base-url URL] [--no-ingest]
"""

import argparse
import json
import platform
import re
import statistics
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = ROOT / "eval" / "docs"
QUESTIONS = ROOT / "eval" / "questions.json"
RESULTS = ROOT / "eval" / "results" / "latest.json"
CITATION = re.compile(r"\[\d+\]")


def _sysctl(key: str) -> str | None:
    try:
        return subprocess.run(
            ["sysctl", "-n", key], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def hardware() -> dict[str, str]:
    memory = _sysctl("hw.memsize")
    return {
        "machine": platform.machine(),
        "system": f"{platform.system()} {platform.release()}",
        "cpu": _sysctl("machdep.cpu.brand_string") or platform.processor() or "unknown",
        "memory_gb": f"{int(memory) / 1024**3:.0f}" if memory else "unknown",
        "note": "Docker runs Ollama on CPU only (no Metal passthrough on macOS)",
    }


def ingest_docs(client: httpx.Client) -> dict[str, Any]:
    files = [
        ("files", (path.name, path.read_bytes(), "application/octet-stream"))
        for path in sorted(DOCS_DIR.iterdir())
        if path.is_file()
    ]
    started = time.perf_counter()
    response = client.post("/ingest", files=files, timeout=900)
    response.raise_for_status()
    elapsed = time.perf_counter() - started
    results: list[dict[str, Any]] = response.json()["results"]
    skipped = [r for r in results if r["status"] != "ingested"]
    if skipped:
        raise SystemExit(f"ingest skipped files: {skipped}")
    return {
        "seconds": round(elapsed, 1),
        "files": len(results),
        "chunks": sum(r["chunks"] for r in results),
    }


def ask(client: httpx.Client, question: str) -> tuple[dict[str, Any], float]:
    started = time.perf_counter()
    response = client.post("/query", json={"question": question, "stream": False}, timeout=600)
    elapsed = time.perf_counter() - started
    response.raise_for_status()
    body: dict[str, Any] = response.json()
    return body, elapsed


def time_to_first_token(client: httpx.Client, question: str) -> float:
    started = time.perf_counter()
    with client.stream(
        "POST", "/query", json={"question": question, "stream": True}, timeout=600
    ) as response:
        response.raise_for_status()
        event = ""
        for line in response.iter_lines():
            if line.startswith("event: "):
                event = line.removeprefix("event: ")
            elif line.startswith("data: ") and event == "token":
                return time.perf_counter() - started
    return float("nan")


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(fraction * (len(ordered) - 1)))]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--no-ingest", action="store_true")
    args = parser.parse_args()

    questions: list[dict[str, Any]] = json.loads(QUESTIONS.read_text())
    with httpx.Client(base_url=args.base_url) as client:
        health = client.get("/health", timeout=30)
        if health.status_code != 200:
            raise SystemExit(f"stack not healthy: {health.text}")
        info: dict[str, Any] = client.get("/info").json()

        ingest = None if args.no_ingest else ingest_docs(client)
        print(f"ingest: {ingest}")

        _, warmup_s = ask(client, "Warm-up: what is this document collection about?")
        print(f"warm-up query (not counted): {warmup_s:.1f}s")

        rows: list[dict[str, Any]] = []
        for item in questions:
            body, seconds = ask(client, item["question"])
            sources = body["sources"]
            hit = any(
                s["filename"] == item["expected_file"]
                and item["evidence"].lower() in s["text"].lower()
                for s in sources
            )
            answer: str = body["answer"]
            rows.append(
                {
                    "question": item["question"],
                    "retrieval_hit": hit,
                    "top_source": f"{sources[0]['filename']}#{sources[0]['chunk_index']}"
                    if sources
                    else None,
                    "answer_match": any(
                        k.lower() in answer.lower() for k in item["answer_keywords"]
                    ),
                    "has_citation": bool(CITATION.search(answer)),
                    "seconds": round(seconds, 2),
                    "answer": answer.strip(),
                }
            )
            print(f"{'HIT ' if hit else 'MISS'} {seconds:6.1f}s  {item['question']}")

        ttft = time_to_first_token(client, questions[0]["question"])

    latencies = [r["seconds"] for r in rows]
    summary = {
        "questions": len(rows),
        "retrieval_hit_rate": round(sum(r["retrieval_hit"] for r in rows) / len(rows), 2),
        "answer_keyword_match_rate": round(sum(r["answer_match"] for r in rows) / len(rows), 2),
        "citation_rate": round(sum(r["has_citation"] for r in rows) / len(rows), 2),
        "latency_s": {
            "mean": round(statistics.mean(latencies), 1),
            "median": round(statistics.median(latencies), 1),
            "p95": round(percentile(latencies, 0.95), 1),
            "max": round(max(latencies), 1),
        },
        "time_to_first_token_s": round(ttft, 1),
        "warmup_query_s": round(warmup_s, 1),
    }
    report = {
        "measured_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "stack": info,
        "hardware": hardware(),
        "ingest": ingest,
        "summary": summary,
        "results": rows,
    }
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    print(f"wrote {RESULTS.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
