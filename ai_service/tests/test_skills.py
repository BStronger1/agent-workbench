import copy
import shutil

import pytest

from ai_service.graph import execute
from ai_service.journal import Journal
from ai_service.skills import ROOT, REPAIR, SkillRegistry
from ai_service.tests.test_workflow import FakeModel, request, validation


def attempt(errors=None, status="FAILED"):
    return {"number": 0, "errors": errors or [], "browserStatus": status}


@pytest.mark.parametrize(
    "error,reference",
    [
        ("Target item must match exactly one element; found 2.", "targets"),
        ("Step check target item is <div>, not a checkbox/radio.", "targets"),
        ("Action fill on unique target entry could not be completed.", "targets"),
        ("Assertion result failed: expected exact text; got other.", "state"),
        ("Result not visible: result", "state"),
        ("JavaScript error: value is not defined", "state"),
    ],
)
def test_selects_only_relevant_reference(error, reference):
    registry = SkillRegistry()
    selected, trace = registry.select(attempt([error]), request().contract.model_dump())
    assert selected["name"] == REPAIR
    assert trace["references"] == [f"references/{reference}.md"]
    unused = "state" if reference == "targets" else "targets"
    assert (
        registry.entries[REPAIR]["references"][f"references/{unused}.md"]
        not in selected["context"]
    )
    assert trace["hash"] == registry.manifest()[0]["hash"]


@pytest.mark.parametrize(
    "errors,status,enabled,can_repair",
    [
        ([], "PASSED", True, True),
        (["Browser infrastructure unavailable; no model repair"], "ERROR", True, True),
        (["Missing title"], "NOT_RUN", True, True),
        (["External or embedded resources forbidden"], "NOT_RUN", True, True),
        (["Assertion result failed"], "NOT_CONFIGURED", True, True),
        (["Assertion result failed"], "FAILED", False, True),
        (["Assertion result failed"], "FAILED", True, False),
    ],
)
def test_non_applicable_work_does_not_load_context(errors, status, enabled, can_repair):
    selected, trace = SkillRegistry().select(
        attempt(errors, status), request().contract.model_dump(), enabled, can_repair
    )
    assert selected is None and trace["contextChars"] == 0


class CaptureModel(FakeModel):
    def __init__(self, *args):
        super().__init__(*args)
        self.prompts = {}

    def call(self, role, system, data, schema, max_tokens=4096):
        self.prompts[role] = (system, copy.deepcopy(data))
        return super().call(role, system, data, schema, max_tokens)


def fail_then_pass(run, n, html, contract):
    value = validation(fail_first=True)(run, n, html, contract)
    value["errors"] = ["Assertion result failed: expected 1; got 0."] if n == 0 else []
    return value


@pytest.mark.parametrize("enabled", [True, False])
def test_graph_injects_skill_only_after_failure_and_keeps_contract(tmp_path, enabled):
    r = request(skillsEnabled=enabled)
    j = Journal(tmp_path / "calls.db")
    model = CaptureModel(j, r.runId)
    result = execute(r, tmp_path, model, fail_then_pass, j)
    assert result["status"] == "PASSED" and result["calls"] == 5
    assert "Trusted repair skill" not in model.prompts["coder-0"][0]
    assert ("Trusted repair skill" in model.prompts["coder-1"][0]) is enabled
    assert ("Trusted repair skill" in model.prompts["reviewer-0"][0]) is enabled
    assert "Trusted repair skill" not in model.prompts["reviewer-1"][0]
    assert result["contract"] == r.contract.model_dump()
    assert all(
        t["contractHash"] == result["contractHash"] for t in result["skillTrace"]
    )
    assert "activeSkill" not in result
    assert (result["skillTrace"][0]["name"] == REPAIR) is enabled


def test_resume_preserves_original_skill_mode_and_rejects_bundle_drift(tmp_path):
    bundle = tmp_path / "skills"
    shutil.copytree(ROOT, bundle)
    registry = SkillRegistry(bundle)
    r = request(pauseAfterPlan=True)
    j = Journal(tmp_path / "calls.db")
    execute(r, tmp_path, CaptureModel(j, r.runId), fail_then_pass, j, registry)
    r.resume = True
    r.skillsEnabled = False
    reference = bundle / REPAIR / "references/state.md"
    original = reference.read_text()
    reference.write_text(original + "\nChanged rules.")
    with pytest.raises(ValueError, match="Skill version changed"):
        execute(
            r,
            tmp_path,
            CaptureModel(j, r.runId),
            fail_then_pass,
            j,
            SkillRegistry(bundle),
        )
    assert j.usage(r.runId)["calls"] == 1
    reference.write_text(original)
    model = CaptureModel(j, r.runId)
    result = execute(r, tmp_path, model, fail_then_pass, j, SkillRegistry(bundle))
    assert result["skillsEnabled"] is True
    assert "Trusted repair skill" in model.prompts["coder-1"][0]


def test_escaping_reference_and_invalid_metadata_are_rejected(tmp_path):
    bundle = tmp_path / "skills"
    shutil.copytree(ROOT, bundle)
    skill = bundle / REPAIR / "SKILL.md"
    original = skill.read_text()
    (tmp_path / "outside.md").write_text("private")
    skill.write_text(original + "\n[bad](references/../../../outside.md)")
    with pytest.raises(ValueError, match="escapes"):
        SkillRegistry(bundle)
    skill.write_text(original.replace('version: "1.0.0"', "version: 1"))
    with pytest.raises(ValueError, match="metadata"):
        SkillRegistry(bundle)


def test_skill_does_not_override_budget_or_repair_limit(tmp_path):
    from ai_service.journal import BudgetExceeded

    class Limited(CaptureModel):
        def call(self, role, *args):
            if role == "coder-1":
                raise BudgetExceeded()
            return super().call(role, *args)

    r = request(workflow="graph_single")
    j = Journal(tmp_path / "calls.db")
    result = execute(r, tmp_path, Limited(j, r.runId), fail_then_pass, j)
    assert result["status"] == "BUDGET_EXCEEDED" and len(result["attempts"]) == 1
    assert result["skillTrace"][0]["name"] == REPAIR
    r2 = request(maxRepairs=0, workflow="graph_single")
    result2 = execute(r2, tmp_path, CaptureModel(j, r2.runId), fail_then_pass, j)
    assert result2["status"] == "FAILED" and result2["calls"] == 1
    assert not any(t["name"] for t in result2["skillTrace"])
