import json, uuid
import pytest
from ai_service.models import RunInput, Contract, Step, Credentials, KnowledgeInput
from ai_service.graph import execute
from ai_service.journal import Journal, BudgetExceeded, AmbiguousCall
from ai_service.llm import parse_json, validate_provider
from ai_service.retrieval import chunks, fuse


class FakeModel:
    def __init__(self, journal, run):
        self.journal = journal
        self.run = run
        self.calls = []

    def call(self, role, system, data, schema, max_tokens=4096):
        self.calls.append(role)
        result = (
            {"summary": "plan", "steps": data.get("contract", {}).get("steps", [])}
            if role == "planner"
            else {"issues": ["fix button"]}
            if role.startswith("reviewer")
            else {"html": "<!doctype html><h1>test</h1>"}
        )
        r = self.journal.invoke(
            self.run,
            role,
            50000,
            100,
            lambda: {
                "content": json.dumps(result),
                "inputTokens": 10,
                "outputTokens": 20,
                "usageKnown": True,
            },
        )
        return parse_json(r["content"], schema)


def request(**kw):
    d = dict(
        owner="a" * 64,
        projectId=str(uuid.uuid4()),
        runId=str(uuid.uuid4()),
        prompt="build app",
        workflow="graph_multi",
        contract={
            "requiredTexts": ["test"],
            "steps": [
                {"action": "click", "target": "primary-action"},
                {"action": "assert_changed", "target": "result"},
            ],
        },
        credentials={
            "baseUrl": "https://www.dmxapi.cn/v1",
            "model": "test",
            "apiKey": "test-key-secret",
        },
    )
    d.update(kw)
    return RunInput(**d)


def validation(fail_first=False, infrastructure=False):
    def fn(run, n, html, contract):
        failed = infrastructure or (fail_first and n == 0)
        return {
            "number": n,
            "html": html,
            "errors": ["broken"] if failed else [],
            "browserStatus": "ERROR"
            if infrastructure
            else "FAILED"
            if failed
            else "PASSED",
            "screenshot": None,
            "durationMs": 1,
        }

    return fn


def test_resume_after_restart_does_not_repeat_planner_or_save_key(tmp_path):
    r = request(pauseAfterPlan=True)
    j = Journal(tmp_path / "calls.db")
    m = FakeModel(j, r.runId)
    first = execute(r, tmp_path, m, validation(), j)
    assert first["status"] == "AWAITING_APPROVAL" and first["calls"] == 1
    # Rebuild graph and checkpoint connection to simulate service restart.
    r.resume = True
    m2 = FakeModel(j, r.runId)
    final = execute(r, tmp_path, m2, validation(), j)
    assert final["status"] == "PASSED" and final["calls"] == 3
    assert "planner" not in m2.calls and final["contractHash"] == first["contractHash"]
    for path in tmp_path.iterdir():
        assert b"test-key-secret" not in path.read_bytes()


def test_bounded_repair_keeps_contract_and_browser_authority(tmp_path):
    r = request(maxRepairs=1)
    j = Journal(tmp_path / "calls.db")
    result = execute(r, tmp_path, FakeModel(j, r.runId), validation(True), j)
    assert result["status"] == "PASSED" and len(result["attempts"]) == 2
    assert (
        result["calls"] == 5
        and result["contract"]["steps"] == r.contract.model_dump()["steps"]
    )


def test_infrastructure_failure_never_repairs(tmp_path):
    r = request()
    j = Journal(tmp_path / "calls.db")
    result = execute(
        r, tmp_path, FakeModel(j, r.runId), validation(infrastructure=True), j
    )
    assert result["status"] == "FAILED" and result["calls"] == 2


def test_single_role_only_calls_coder(tmp_path):
    r = request(workflow="graph_single")
    j = Journal(tmp_path / "calls.db")
    result = execute(r, tmp_path, FakeModel(j, r.runId), validation(), j)
    assert result["status"] == "PASSED" and result["roles"] == ["coder-0"]


def test_resume_cannot_cross_owner_or_change_provider(tmp_path):
    r = request(pauseAfterPlan=True)
    j = Journal(tmp_path / "calls.db")
    m = FakeModel(j, r.runId)
    execute(r, tmp_path, m, validation(), j)
    r.resume = True
    r.owner = "b" * 64
    with pytest.raises(ValueError):
        execute(r, tmp_path, m, validation(), j)
    r.owner = "a" * 64
    r.credentials.model = "different"
    with pytest.raises(ValueError):
        execute(r, tmp_path, m, validation(), j)


def test_journal_cache_budget_and_ambiguous_request(tmp_path):
    j = Journal(tmp_path / "calls.db")
    calls = []

    def reply():
        calls.append(1)
        return {
            "content": "{}",
            "inputTokens": 10,
            "outputTokens": 20,
            "usageKnown": True,
        }

    j.invoke("run", "coder", 100, 40, reply)
    j.invoke("run", "coder", 100, 40, reply)
    assert len(calls) == 1
    with pytest.raises(BudgetExceeded):
        j.invoke("run", "next", 100, 80, reply)

    def crash():
        raise ConnectionError()

    with pytest.raises(ConnectionError):
        j.invoke("run", "uncertain", 100, 10, crash)
    with pytest.raises(AmbiguousCall):
        j.invoke("run", "uncertain", 100, 10, reply)
    assert not j.usage("run")["usageKnown"] and len(calls) == 1


def test_contract_rejects_unsafe_targets_and_empty_assertions():
    with pytest.raises(ValueError):
        Step(action="click", target='x"] script')
    with pytest.raises(ValueError):
        Contract(steps=[Step(action="click", target="primary-action")])
    with pytest.raises(ValueError):
        Contract(
            steps=[
                Step(action="click", target="primary-action"),
                Step(action="assert_text", target="result", value=""),
            ]
        )


def test_provider_rejects_internal_and_credential_urls():
    for base in [
        "http://127.0.0.1/v1",
        "https://www.dmxapi.cn.evil.example/v1",
        "https://a:b@www.dmxapi.cn/v1",
    ]:
        with pytest.raises(ValueError):
            validate_provider(
                Credentials(baseUrl=base, model="m", apiKey="test-only-key")
            )


def test_chunking_excludes_superseded_memory_and_preserves_sources():
    r = KnowledgeInput(
        owner="a" * 64,
        projectId=str(uuid.uuid4()),
        query="budget",
        memories=[
            {"id": "old", "active": False, "key": "budget", "value": "100"},
            {"id": "new", "active": True, "key": "budget", "value": "200"},
        ],
        documents=[{"id": "doc", "title": "plan", "content": "实验准备。" * 200}],
    )
    rows = chunks(r)
    assert rows[0]["id"] == "new" and all(x["id"] != "old" for x in rows)
    assert len(rows) > 2 and all(
        len(x["excerpt"]) <= 650 for x in rows if x["id"].startswith("doc:")
    )


def test_rrf_combines_lexical_and_semantic_and_can_abstain():
    rows = [
        {"id": "a", "title": "schedule", "excerpt": "next week"},
        {"id": "b", "title": "experiment", "excerpt": "materials"},
    ]
    assert fuse("schedule", rows, {"a": 0.8, "b": 0.7})[0]["id"] == "a"
    assert fuse("unknown", rows, {"a": 0.1, "b": 0.2}) == []
