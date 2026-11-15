"""Diagnose RAGAS factual-correctness zeros without altering saved results.

Runs two independent checks for each ID:
 - identity: identical normalized text is both response and reference (judge sanity check)
 - contextualized: original question + unchanged short reference expressed as a sentence

Both checks are DIAGNOSTIC metrics, not replacement scores and not a
modification to the original ground-truth dataset.

Example:
 python -m evaluation.diagnose_ragas_factual --ids Q01 --delay 65
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from evaluation.ragas_eval import _init_judge
from evaluation.judge_preprocessing import clean_for_judge, contextual_reference

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "evaluation" / "results_after_fix_rescored" / "results.json"
DEFAULT_OUTPUT = ROOT / "evaluation" / "results_after_fix_rescored" / "ragas_diagnostic"
def make_checks(row: dict, names: list[str]) -> list[dict]:
    answer = clean_for_judge(row.get("answer", ""))
    if not answer:
        raise ValueError(f"{row.get('id')} has no generated answer")
    reference = contextual_reference(row.get("question", ""), row.get("reference", ""))
    options = {
        "identity": {"response": answer, "reference": answer},
        "contextualized": {"response": answer, "reference": reference},
    }
    return [{"check": name, **options[name]} for name in names]


def persist(data: list[dict], directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "diagnostics.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


async def run(input_path: Path, output_dir: Path, ids: list[str], checks: list[str],
              delay: float, model: str, api_key: str, base_url: str,
              dry_run: bool = False) -> list[dict]:
    rows = json.loads(input_path.read_text(encoding="utf-8"))
    by_id = {row["id"]: row for row in rows}
    missing = [item for item in ids if item not in by_id]
    if missing:
        raise ValueError(f"Unknown question IDs: {', '.join(missing)}")
    data = []
    scorer = None
    if not dry_run:
        from ragas.metrics.collections import FactualCorrectness
        scorer = FactualCorrectness(llm=_init_judge(model, api_key, base_url))
    for qid in ids:
        row = by_id[qid]
        for values in make_checks(row, checks):
            record = {
                "id": qid,
                "check": values["check"],
                "judge_model": model,
                "response_supplied": values["response"],
                "reference_supplied": values["reference"],
                "score": None,
                "error": None,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            }
            if not dry_run:
                try:
                    result = await scorer.ascore(response=values["response"], reference=values["reference"])
                    record["score"] = float(result.value)
                except Exception as exc:
                    record["error"] = f"{type(exc).__name__}: {exc}"[:400]
            data.append(record)
            persist(data, output_dir)
            print(f"{qid} {record['check']}: score={record['score']} error={record['error']}", flush=True)
            if not dry_run and delay:
                await asyncio.sleep(delay)
    print("Saved:", output_dir / "diagnostics.json")
    return data


def main() -> None:
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="Diagnose two RAGAS factual-correctness zeros")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--ids", default="Q01", help="Comma-separated IDs; first try Q01")
    parser.add_argument("--checks", default="identity,contextualized")
    parser.add_argument("--delay", type=float, default=65)
    parser.add_argument("--dry-run", action="store_true", help="Preview inputs without Groq requests")
    parser.add_argument("--model", default=os.getenv("RAGAS_EVAL_MODEL", "openai/gpt-oss-20b"))
    parser.add_argument("--base-url", default=os.getenv("RAGAS_EVAL_BASE_URL", "https://api.groq.com/openai/v1"))
    args = parser.parse_args()
    checks = [v.strip() for v in args.checks.split(",") if v.strip()]
    if not checks or any(v not in {"identity", "contextualized"} for v in checks):
        parser.error("--checks must contain identity and/or contextualized")
    ids = [v.strip() for v in args.ids.split(",") if v.strip()]
    if not ids:
        parser.error("--ids must not be empty")
    api_key = os.getenv("RAGAS_EVAL_API_KEY") or os.getenv("GROQ_API_KEY", "")
    if not args.dry_run and not api_key:
        parser.error("GROQ_API_KEY or RAGAS_EVAL_API_KEY is required")
    asyncio.run(run(args.input, args.output_dir, ids, checks, args.delay,
                    args.model, api_key or "", args.base_url, args.dry_run))


if __name__ == "__main__":
    main()
