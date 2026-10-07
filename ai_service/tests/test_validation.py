import json
from pathlib import Path
from ai_service.validation import static_errors


def test_real_failed_checklists_report_the_duplicate_target():
    report = json.loads(
        (Path(__file__).parents[2] / "evidence/graph-live.json").read_text(
            encoding="utf-8"
        )
    )
    failed = [r for r in report["results"] if r["caseId"] == "G-02"]
    assert len(failed) == 2
    for run in failed:
        contract = {
            "requiredTexts": run["requiredTexts"],
            "checkInteraction": True,
            "steps": run["steps"],
        }
        for attempt in run["attempts"]:
            errors = static_errors(attempt["html"], contract)
            assert any(
                "Target selection-item must match exactly one element; found 4." in e
                for e in errors
            )


def test_static_check_allows_js_created_targets_but_rejects_duplicate_assertions():
    html = '<!DOCTYPE html><title>x</title><meta name="viewport"><h1>x</h1><button data-testid="primary-action">Go</button><p data-testid="result">0</p>'
    contract = {
        "requiredTexts": [],
        "checkInteraction": True,
        "steps": [
            {"target": "dynamic-checkbox", "action": "check"},
            {"target": "primary-action", "action": "click"},
            {"target": "result", "action": "assert_text", "value": "1"},
        ],
    }
    assert static_errors(html, contract) == []
    errors = static_errors(html + '<p data-testid="result">1</p>', contract)
    assert any(
        "Target result must match exactly one element; found 2." in e for e in errors
    )
