"""Replay frozen real-model edit replies with the current deterministic tool.

No provider call is made. Historical usage is attributed to its original run.
"""

import json
import os
from pathlib import Path
import shutil

from .llm import parse_json
from .models import CodeEdits
from .patching import apply_edits, html_hash, PatchError
from .skill_eval import ROOT, load_cases, sha, write
from .validation import Validator


def main():
    if not os.getenv("QA_COMMAND"):
        raise SystemExit("Configure the existing Playwright worker")
    paid_path = ROOT / "evidence/skill-edits-evaluation.json"
    paid = json.loads(paid_path.read_text(encoding="utf-8"))
    assert paid["status"] == "COMPLETE"
    replies_path = ROOT / "evidence/skill-edit-replies.json"
    if not replies_path.exists():
        import sqlite3
        from contextlib import closing

        journal_path = ROOT / ".tools/skill-eval-data/calls.sqlite"
        if not journal_path.is_file():
            raise FileNotFoundError(
                "Local model call journal or saved replies required"
            )
        records = []
        with closing(sqlite3.connect(journal_path)) as connection:
            for row in paid["results"]:
                if row.get("reusedFrom"):
                    continue
                state, payload = connection.execute(
                    "SELECT state,payload FROM calls WHERE run=? AND call=?",
                    (row["runId"], "coder-1"),
                ).fetchone()
                if state != "complete":
                    raise ValueError("Cannot replay an uncertain provider request")
                value = json.loads(payload)
                records.append(
                    {
                        "runId": row["runId"],
                        "content": value["content"],
                        "inputTokens": value["inputTokens"],
                        "outputTokens": value["outputTokens"],
                    }
                )
        write(replies_path, records)
    replies = {
        r["runId"]: r for r in json.loads(replies_path.read_text(encoding="utf-8"))
    }
    cases = {c["id"]: c for c in load_cases()}
    data = ROOT / ".tools/skill-replay-data"
    rows = []
    validator = Validator(data)
    for original in paid["results"]:
        case = cases[original["caseId"]]
        assert case["contractHash"] == original["contractHash"]
        html = original["attempts"][-1]["html"]
        ignored = 0
        error = None
        if original["skillsEnabled"]:
            source = replies[original["runId"]]
            assert (source["inputTokens"], source["outputTokens"]) == (
                original["inputTokens"],
                original["outputTokens"],
            )
            try:
                parsed = parse_json(source["content"], CodeEdits)
                ignored = sum(e["old"] == e["new"] for e in parsed["edits"])
                html = apply_edits(case["seedHtml"], parsed)
            except (ValueError, PatchError) as problem:
                error = (
                    str(problem)
                    if isinstance(problem, PatchError)
                    else "Invalid edit response schema"
                )
                html = case["seedHtml"]
        if error:
            outcome = {
                "errors": ["Patch rejected: " + error],
                "browserStatus": "NOT_RUN",
            }
        else:
            outcome = validator(original["runId"], 0, html, case["contract"])
        status = (
            "PASSED"
            if outcome["browserStatus"] == "PASSED" and not outcome["errors"]
            else "FAILED"
        )
        artifact = ROOT / "evidence/skill-replay-artifacts" / original["runId"]
        artifact.mkdir(parents=True, exist_ok=True)
        (artifact / "index.html").write_bytes(html.encode("utf-8"))
        if outcome.get("screenshot"):
            shutil.copyfile(
                data / "qa" / outcome["screenshot"], artifact / "screenshot.png"
            )
        rows.append(
            {
                "runId": original["runId"],
                "caseId": original["caseId"],
                "repeat": original["repeat"],
                "skillsEnabled": original["skillsEnabled"],
                "originalStatus": original["status"],
                "status": status,
                "errors": outcome["errors"],
                "browserStatus": outcome["browserStatus"],
                "contractHash": case["contractHash"],
                "htmlHash": html_hash(html),
                "ignoredNeutralEdits": ignored,
                "artifact": (artifact / "index.html").relative_to(ROOT).as_posix(),
                "originalInputTokens": original["inputTokens"],
                "originalOutputTokens": original["outputTokens"],
            }
        )
        print(
            f"Replay {original['caseId']} repeat={original['repeat']} skills={original['skillsEnabled']} {status}",
            flush=True,
        )
    result = {
        "mode": "offline replay of frozen real-model outputs; zero new model calls",
        "paidReport": paid_path.relative_to(ROOT).as_posix(),
        "paidReportSha256": sha(paid_path),
        "repliesSha256": sha(replies_path),
        "patchToolSha256": sha(ROOT / "ai_service/patching.py"),
        "validatorSha256": sha(ROOT / "ai_service/validation.py"),
        "contractWorkerSha256": sha(ROOT / "qa/contract.mjs"),
        "results": rows,
        "summary": {},
    }
    for enabled in (False, True):
        selected = [r for r in rows if r["skillsEnabled"] is enabled]
        result["summary"]["skill" if enabled else "baseline"] = {
            "trials": len(selected),
            "passed": sum(r["status"] == "PASSED" for r in selected),
            "originalInputTokens": sum(r["originalInputTokens"] for r in selected),
            "originalOutputTokens": sum(r["originalOutputTokens"] for r in selected),
        }
    write(ROOT / "evidence/skill-edit-replay.json", result)


if __name__ == "__main__":
    main()
