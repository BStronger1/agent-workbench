"""Frozen paired repair evaluation. No model calls without --live.

Both arms execute the production graph/validator with the same seeded failed HTML.
coder-0 is supplied by the fixture adapter (no LLM call); coder-1 is the one paid
repair. This measures repair on known failures, not end-to-end generation.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import uuid

from .graph import execute, fingerprint
from .journal import Journal
from .llm import Model
from .models import Credentials, RunInput
from .skills import SkillRegistry
from .validation import Validator

ROOT = Path(__file__).resolve().parent.parent
CASES = ROOT / "qa/skill-cases/cases.json"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def load_cases():
    from .models import Contract

    cases = json.loads(CASES.read_text(encoding="utf-8"))
    for case in cases:
        case["contract"] = Contract.model_validate(case["contract"]).model_dump()
        path = (ROOT / case["html"]).resolve()
        if not path.is_relative_to(ROOT / "qa/skill-cases"):
            raise ValueError("Fixture escapes case directory")
        case["seedHtml"] = path.read_text(encoding="utf-8")
        case["htmlHash"] = sha(path)
        case["contractHash"] = fingerprint(case["contract"])
    return cases


def summary(results):
    output = {}
    for enabled in (False, True):
        rows = [r for r in results if r["skillsEnabled"] is enabled]
        known = all(r["usageKnown"] for r in rows)
        passed = sum(r["status"] == "PASSED" for r in rows)
        output["skill" if enabled else "baseline"] = {
            "trials": len(rows),
            "passed": passed,
            "passRate": passed / len(rows) if rows else None,
            "calls": sum(r["calls"] for r in rows),
            "usageKnown": known,
            "totalTokens": sum(r["inputTokens"] + r["outputTokens"] for r in rows)
            if known
            else None,
            "meanDurationMs": round(sum(r["durationMs"] for r in rows) / len(rows))
            if rows
            else None,
        }
    pairs = {}
    for row in results:
        pairs.setdefault((row["caseId"], row["repeat"]), {})[row["skillsEnabled"]] = (
            row["status"] == "PASSED"
        )
    complete = [p for p in pairs.values() if len(p) == 2]
    output["paired"] = {
        "complete": len(complete),
        "skillOnlyPass": sum(p[True] and not p[False] for p in complete),
        "baselineOnlyPass": sum(p[False] and not p[True] for p in complete),
        "bothPass": sum(p[False] and p[True] for p in complete),
        "bothFail": sum(not p[False] and not p[True] for p in complete),
    }
    return output


class SeededModel:
    def __init__(self, real, seed):
        self.real, self.seed = real, seed
        self.repair_context_chars = 0

    def call(self, role, system, data, schema, max_tokens=4096):
        if role == "coder-0":
            return {"html": self.seed}
        if role != "coder-1":
            raise ValueError("Evaluation allows exactly one real repair call")
        self.repair_context_chars = len(system) + len(
            json.dumps(data, ensure_ascii=False)
        )
        return self.real.call(role, system, data, schema, max_tokens)


def preflight(cases, data, registry):
    validator = Validator(data)
    rows = []
    for case in cases:
        outcome = validator("seed-" + case["id"], 0, case["seedHtml"], case["contract"])
        selected, trace = registry.select(outcome, case["contract"])
        rows.append(
            {
                "caseId": case["id"],
                "htmlHash": case["htmlHash"],
                "contractHash": case["contractHash"],
                "browserStatus": outcome["browserStatus"],
                "errors": outcome["errors"],
                "skill": trace,
            }
        )
        if (
            not outcome["errors"]
            or outcome["browserStatus"] in ("ERROR", "NOT_CONFIGURED")
            or not selected
        ):
            raise ValueError(
                "Preflight requires an actual, routable fixture failure: " + case["id"]
            )
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument(
        "--baseline-report",
        help="Reuse every baseline trial from a complete frozen paired run",
    )
    parser.add_argument("--repeats", type=int, choices=(1, 2), default=2)
    parser.add_argument("--output", default="evidence/skill-ablation.json")
    args = parser.parse_args()
    if not os.getenv("QA_COMMAND"):
        raise SystemExit("QA_COMMAND must name the existing Playwright worker")
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    cases, registry = load_cases(), SkillRegistry()
    data = ROOT / ".tools/skill-eval-data"
    data.mkdir(parents=True, exist_ok=True)
    checks = preflight(cases, data, registry)
    write(
        ROOT / "evidence/skill-preflight.json",
        {"mode": "no-model-calls", "cases": checks},
    )
    print(
        "Preflight: 8/8 original artifacts fail unchanged contracts; skill routing available.",
        flush=True,
    )
    if not args.live:
        return
    output = (ROOT / args.output).resolve()
    if not output.is_relative_to(ROOT / "evidence") or output.exists():
        raise SystemExit(
            "Use a new report inside evidence; existing paid results are never overwritten"
        )
    # Credentials arrive via stdin, never command arguments, files, or report fields.
    if sys.stdin.isatty():
        import getpass

        credentials = Credentials(
            baseUrl=os.getenv("EVAL_BASE_URL", "https://www.dmxapi.cn/v1"),
            model=os.getenv("EVAL_MODEL", "DMXAPI-deepseek-v4-flash"),
            apiKey=getpass.getpass("API key (hidden): "),
        )
    else:
        credentials = Credentials.model_validate(json.load(sys.stdin))
    inputs = {
        c["id"]: {
            "html": c["htmlHash"],
            "contract": c["contractHash"],
            "origin": c["origin"],
        }
        for c in cases
    }
    report = {
        "startedAt": datetime.now(timezone.utc).isoformat(),
        "status": "RUNNING",
        "scope": "paired repair-only development evaluation; 2 historical and 6 developer-authored cases, not an independent benchmark",
        "model": credentials.model,
        "baseUrl": credentials.baseUrl,
        "temperature": 0.2,
        "workflow": "graph_single",
        "maxRepairs": 1,
        "tokenBudgetPerRun": 50000,
        "totalTokenStop": 180000,
        "repeats": args.repeats,
        "plannedCalls": len(cases) * 2 * args.repeats,
        "skillManifest": registry.manifest(),
        "fixtures": inputs,
        "sourceHashes": {
            name: sha(ROOT / name)
            for name in [
                "ai_service/graph.py",
                "ai_service/llm.py",
                "ai_service/skills.py",
                "ai_service/validation.py",
                "qa/worker.mjs",
                "qa/contract.mjs",
                "ai_service/skill_eval.py",
                "qa/skill-cases/cases.json",
            ]
        },
        "order": "case order S01..S08; baseline-first and skill-first alternate by case and repeat",
        "results": [],
    }
    if args.baseline_report:
        baseline_path = (ROOT / args.baseline_report).resolve()
        if not baseline_path.is_relative_to(ROOT / "evidence"):
            raise ValueError("Baseline must be a retained evidence report")
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        if baseline["status"] != "COMPLETE" or baseline["fixtures"] != inputs:
            raise ValueError("Baseline incomplete or fixtures changed")
        for key in (
            "model",
            "baseUrl",
            "temperature",
            "maxRepairs",
            "tokenBudgetPerRun",
            "repeats",
        ):
            if baseline[key] != report[key]:
                raise ValueError("Baseline evaluation conditions differ: " + key)
        rows = [row for row in baseline["results"] if row["skillsEnabled"] is False]
        if len(rows) != len(cases) * args.repeats:
            raise ValueError("Baseline must include all trials, including failures")
        report["results"] = [
            {**row, "reusedFrom": args.baseline_report} for row in rows
        ]
        report["baselineSource"] = {
            "path": args.baseline_report,
            "sha256": sha(baseline_path),
        }
        report["plannedCalls"] = len(cases) * args.repeats
        report["order"] = (
            "all baseline trials reused from complete prior run; new skill trials S01..S08, two repeats"
        )
        report["scope"] += (
            "; non-contemporaneous development comparison, including skill-guided literal edit tool"
        )
    report["sourceHashes"]["ai_service/patching.py"] = sha(
        ROOT / "ai_service/patching.py"
    )
    report["sourceHashes"]["ai_service/models.py"] = sha(ROOT / "ai_service/models.py")
    write(output, report)
    journal = Journal(data / "calls.sqlite")
    try:
        for repeat in range(1, args.repeats + 1):
            for index, case in enumerate(cases):
                order = (False, True) if (index + repeat) % 2 else (True, False)
                if args.baseline_report:
                    order = (True,)
                for enabled in order:
                    spent = sum(
                        r["inputTokens"] + r["outputTokens"]
                        for r in report["results"]
                        if not r.get("reusedFrom")
                    )
                    if spent + 50000 > report["totalTokenStop"]:
                        raise RuntimeError("Aggregate conservative budget reached")
                    request = RunInput(
                        owner="e" * 64,
                        projectId=str(uuid.uuid4()),
                        runId=str(uuid.uuid4()),
                        prompt=case["prompt"],
                        workflow="graph_single",
                        contract=case["contract"],
                        maxRepairs=1,
                        tokenBudget=50000,
                        skillsEnabled=enabled,
                        credentials=credentials,
                    )
                    model = SeededModel(
                        Model(credentials, journal, request.runId, request.tokenBudget),
                        case["seedHtml"],
                    )
                    outcome = execute(
                        request, data, model, Validator(data), journal, registry
                    )
                    assert outcome["contractHash"] == case["contractHash"]
                    for trace in outcome["skillTrace"]:
                        assert trace["contractHash"] == case["contractHash"]
                    public = {
                        k: outcome[k]
                        for k in [
                            "runId",
                            "status",
                            "error",
                            "skillsEnabled",
                            "contractHash",
                            "skillTrace",
                            "attempts",
                            "events",
                            "inputTokens",
                            "outputTokens",
                            "usageKnown",
                            "calls",
                            "roles",
                            "durationMs",
                        ]
                    }
                    public["patchTrace"] = outcome.get("patchTrace", [])
                    public.update(
                        caseId=case["id"],
                        repeat=repeat,
                        repairPromptChars=model.repair_context_chars,
                    )
                    for a in public["attempts"]:
                        screenshot = a.get("screenshot")
                        if screenshot and (data / "qa" / screenshot).is_file():
                            target = ROOT / "evidence/skill-artifacts" / screenshot
                            target.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copyfile(data / "qa" / screenshot, target)
                            a["screenshot"] = target.relative_to(ROOT).as_posix()
                    report["results"].append(public)
                    report["summary"] = summary(report["results"])
                    write(output, report)
                    print(
                        f"{case['id']} repeat={repeat} skills={enabled} {outcome['status']} calls={outcome['calls']} tokens={outcome['inputTokens'] + outcome['outputTokens']}",
                        flush=True,
                    )
                    if not outcome["usageKnown"]:
                        raise RuntimeError(
                            "Provider result uncertain; evaluation stopped without retry"
                        )
        report["status"] = "COMPLETE"
    except Exception as error:
        report["status"] = "STOPPED"
        report["stopReason"] = (
            str(error) if isinstance(error, RuntimeError) else type(error).__name__
        )
        raise
    finally:
        report["newCalls"] = sum(
            r["calls"] for r in report["results"] if not r.get("reusedFrom")
        )
        report["newTokens"] = sum(
            r["inputTokens"] + r["outputTokens"]
            for r in report["results"]
            if not r.get("reusedFrom")
        )
        report["finishedAt"] = datetime.now(timezone.utc).isoformat()
        report["summary"] = summary(report["results"])
        write(output, report)


if __name__ == "__main__":
    main()
