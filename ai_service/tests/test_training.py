from ai_service.training_export import candidates


def test_candidates_exclude_failures_and_group_same_task():
    base = {
        "id": "one",
        "caseId": "A",
        "mode": "live",
        "model": "test",
        "status": "PASSED",
        "prompt": "same task",
        "attempts": [{"html": "safe sample"}],
    }
    rows = list(
        candidates(
            {
                "results": [
                    base,
                    {**base, "id": "two", "caseId": "B"},
                    {**base, "status": "FAILED"},
                    {**base, "mode": "demo"},
                ]
            }
        )
    )
    assert len(rows) == 2 and rows[0]["group"] == rows[1]["group"]
    assert all(x["reviewStatus"] == "pending_human_review" for x in rows)
