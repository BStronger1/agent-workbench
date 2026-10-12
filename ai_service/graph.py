"""Explicit LangGraph: plan -> approval -> code -> browser -> review -> repair."""

import hashlib, json, sqlite3, time
from datetime import datetime, timezone
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import interrupt, Command
from .models import Contract, Plan, Code, CodeEdits, Review
from .patching import apply_edits, html_hash, PatchError
from .journal import BudgetExceeded, AmbiguousCall
from .skills import SkillRegistry, skill_instruction


class State(TypedDict, total=False):
    owner: str
    projectId: str
    runId: str
    prompt: str
    workflow: str
    contract: dict
    contractHash: str
    plan: dict
    sources: list
    maxRepairs: int
    pauseAfterPlan: bool
    attempts: list
    events: list
    feedback: list
    html: str
    status: str
    error: str
    model: str
    baseUrl: str
    tokenBudget: int
    durationMs: int
    skillsEnabled: bool
    skillManifest: list
    skillTrace: list
    activeSkill: dict | None
    generationErrors: list
    patchTrace: list


def fingerprint(contract):
    return hashlib.sha256(
        json.dumps(contract, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def event(state, stage, message):
    return state.get("events", []) + [
        {
            "at": datetime.now(timezone.utc).isoformat(),
            "stage": stage,
            "message": message,
        }
    ]


def default_steps():
    return [
        {"action": "click", "target": "primary-action", "value": ""},
        {"action": "assert_changed", "target": "result", "value": ""},
    ]


def build(checkpointer, model, validator, registry=None):
    registry = registry or SkillRegistry()

    def plan(s):
        contract = dict(s["contract"])
        if s["workflow"] == "graph_multi":
            p = model.call(
                "planner",
                "You are the requirements planner. Produce a concise implementation plan and executable browser steps. Each data-testid target must identify exactly one DOM element, never a group. Use a distinct target for an individual checkbox or input. Preserve every supplied step exactly. Text assertions require exact trimmed text equality. Include input/check prerequisites when the user task needs them, a primary-action click and a result assertion. Never weaken required texts.",
                {"request": s["prompt"], "sources": s["sources"], "contract": contract},
                Plan,
                1000,
            )
            if not contract["steps"]:
                contract["steps"] = p["steps"] if contract["checkInteraction"] else []
        else:
            p = {"summary": s["prompt"], "steps": contract["steps"]}
        if contract["checkInteraction"] and not contract["steps"]:
            contract["steps"] = default_steps()
        contract = Contract.model_validate(contract).model_dump()
        if contract["checkInteraction"] and not any(
            x["action"] == "click" and x["target"] == "primary-action"
            for x in contract["steps"]
        ):
            raise ValueError("Plan must exercise primary-action")
        p["steps"] = contract["steps"]
        return {
            "plan": p,
            "contract": contract,
            "contractHash": fingerprint(contract),
            "events": event(s, "plan", "验收步骤已固定；生成和修复不能更改"),
        }

    def approval(s):
        if s["pauseAfterPlan"]:
            if interrupt({"plan": s["plan"], "contract": s["contract"]}) is not True:
                raise ValueError("Plan not approved")
        return {"events": event(s, "approval", "验收契约已确认")}

    def code(s):
        if fingerprint(s["contract"]) != s["contractHash"]:
            raise ValueError("Contract changed")
        n = len(s.get("attempts", []))
        data = {
            "request": s["prompt"],
            "sources": s["sources"],
            "plan": s["plan"],
            "frozenContract": s["contract"],
        }
        if n:
            data.update(
                previousHtml=s["html"],
                browserErrors=s["attempts"][-1]["errors"],
                reviewFeedback=s.get("feedback", []),
            )
        system = "You are the coding agent. Build a complete self-contained HTML app with inline CSS/JS, doctype, title, h1 and viewport. No external URLs, network calls, iframe, form, imports or downloads. Implement every frozen test step using matching data-testid attributes. Every target referenced in the contract must match exactly ONE DOM element. For a list, assign the contract target only to the intended item (the first item when requested); give other items distinct IDs, never repeat the target across the list. Use classes for group selection/counting. For every check step put data-testid directly on a visible native input type=checkbox or radio, not its surrounding div/card. For fill steps put it on the actual editable input or textarea. Render every requiredTexts entry visibly, including after a repair. Do not change the contract. Return only the complete HTML document."
        patch_trace = s.get("patchTrace", [])
        errors = []
        if n and s.get("activeSkill"):
            system = system.replace(
                "Return only the complete HTML document.",
                "For this repair return JSON edits with exact old/new substring anchors; preserve untouched HTML.",
            )
            record = {"attempt": n, "beforeHash": html_hash(s["html"])}
            try:
                reply = model.call(
                    f"coder-{n}", system + skill_instruction(s), data, CodeEdits
                )
                html = apply_edits(s["html"], reply)
                record.update(
                    status="APPLIED", edits=reply["edits"], afterHash=html_hash(html)
                )
            except (PatchError, ValueError) as error:
                reason = (
                    str(error)
                    if isinstance(error, PatchError)
                    else "Invalid edit response schema"
                )
                errors = ["Patch rejected: " + reason]
                html = s["html"]
                record.update(
                    status="REJECTED", reason=reason, afterHash=html_hash(html)
                )
            patch_trace = patch_trace + [record]
        else:
            reply = model.call(f"coder-{n}", system, data, Code)
            html = reply["html"]
        return {
            "html": html,
            "generationErrors": errors,
            "patchTrace": patch_trace,
            "events": event(
                s, "generate" if n == 0 else "repair", f"编码角色第 {n + 1} 次生成"
            ),
        }

    def validate(s):
        if fingerprint(s["contract"]) != s["contractHash"]:
            raise ValueError("Contract changed")
        attempts = s.get("attempts", [])
        if s.get("generationErrors"):
            a = {
                "number": len(attempts),
                "html": s["html"],
                "errors": s["generationErrors"],
                "browserStatus": "NOT_RUN",
                "screenshot": None,
                "durationMs": 0,
            }
        else:
            a = validator(s["runId"], len(attempts), s["html"], s["contract"])
        return {
            "attempts": attempts + [a],
            "events": event(s, "validate", a["browserStatus"]),
        }

    def review(s):
        a = s["attempts"][-1]
        result = model.call(
            f"reviewer-{len(s['attempts']) - 1}",
            "You are an independent code reviewer. Inspect requirement coverage, static validation errors and browser failure evidence. Verify that each contract target identifies exactly one element; repeated data-testid values on a list must be fixed, and every required text must remain visible. A check target must be the checkbox/radio control itself, not a wrapper containing it. Give up to 8 concrete repair suggestions. You cannot alter acceptance steps or override browser results. Empty issues when none. Never request extra tools or network."
            + skill_instruction(s),
            {
                "request": s["prompt"],
                "contract": s["contract"],
                "html": s["html"],
                "browserErrors": a["errors"],
            },
            Review,
            700,
        )
        return {
            "feedback": result["issues"],
            "events": event(s, "review", json.dumps(result, ensure_ascii=False)),
        }

    def select_skill(s):
        selected, trace = registry.select(
            s["attempts"][-1],
            s["contract"],
            enabled=s.get("skillsEnabled", False),
            can_repair=len(s["attempts"]) <= s["maxRepairs"],
        )
        trace["contractHash"] = s["contractHash"]
        return {
            "activeSkill": selected,
            "skillTrace": s.get("skillTrace", []) + [trace],
            "events": event(
                s,
                "skill",
                (
                    "交互修复技能已加载："
                    + selected["name"]
                    + "@"
                    + selected["version"]
                    if selected
                    else "修复技能未加载：" + trace["reason"]
                ),
            ),
        }

    def after_validate(s):
        if s["attempts"][-1]["browserStatus"] == "ERROR":
            return "finish"
        return "review" if s["workflow"] == "graph_multi" else after_review(s)

    def after_review(s):
        a = s["attempts"][-1]
        return (
            "code"
            if a["errors"]
            and a["browserStatus"] != "ERROR"
            and len(s["attempts"]) <= s["maxRepairs"]
            else "finish"
        )

    def finish(s):
        a = s["attempts"][-1]
        status = (
            "FAILED"
            if a["errors"]
            else "PASSED"
            if a["browserStatus"] == "PASSED"
            else "STATIC_VALIDATED"
        )
        return {
            "status": status,
            "error": "验收未通过，保留全部尝试记录" if status == "FAILED" else "",
            "events": event(s, "complete", status),
        }

    g = StateGraph(State)
    for name, fn in [
        ("plan", plan),
        ("approval", approval),
        ("code", code),
        ("validate", validate),
        ("review", review),
        ("select_skill", select_skill),
        ("finish", finish),
    ]:
        g.add_node(name, fn)
    g.add_edge(START, "plan")
    g.add_edge("plan", "approval")
    g.add_edge("approval", "code")
    g.add_edge("code", "validate")
    g.add_edge("validate", "select_skill")
    g.add_conditional_edges("select_skill", after_validate)
    g.add_conditional_edges("review", after_review)
    g.add_edge("finish", END)
    return g.compile(checkpointer=checkpointer)


def execute(request, data, model, validator, journal, registry=None):
    registry = registry or SkillRegistry()
    started = time.monotonic()
    thread = hashlib.sha256(
        f"{request.owner}/{request.projectId}/{request.runId}".encode()
    ).hexdigest()
    config = {"configurable": {"thread_id": thread}, "recursion_limit": 40}
    with sqlite3.connect(data / "checkpoints.sqlite", check_same_thread=False) as conn:
        graph = build(SqliteSaver(conn), model, validator, registry)
        snapshot = graph.get_state(config)
        if request.resume:
            if not snapshot.values:
                raise ValueError("No checkpoint for this owner and project")
            if (
                snapshot.values["model"] != request.credentials.model
                or snapshot.values["baseUrl"] != request.credentials.baseUrl
            ):
                raise ValueError("Resume requires original model and provider")
            if snapshot.values.get("skillsEnabled", False) and (
                snapshot.values.get("skillManifest") != registry.manifest()
            ):
                raise ValueError(
                    "Skill version changed; restore original bundle or start a new run"
                )
            payload = Command(resume=True) if snapshot.interrupts else None
        else:
            if snapshot.values:
                raise ValueError("Run already exists; use resume")
            payload = {
                "owner": request.owner,
                "projectId": request.projectId,
                "runId": request.runId,
                "prompt": request.prompt,
                "workflow": request.workflow,
                "contract": request.contract.model_dump(),
                "sources": [x.model_dump() for x in request.sources],
                "maxRepairs": request.maxRepairs,
                "pauseAfterPlan": request.pauseAfterPlan,
                "attempts": [],
                "events": [],
                "model": request.credentials.model,
                "baseUrl": request.credentials.baseUrl,
                "tokenBudget": request.tokenBudget,
                "durationMs": 0,
                "skillsEnabled": request.skillsEnabled,
                "skillManifest": registry.manifest() if request.skillsEnabled else [],
                "skillTrace": [],
                "activeSkill": None,
                "generationErrors": [],
                "patchTrace": [],
            }
        status = None
        error = ""
        try:
            graph.invoke(payload, config, durability="sync")
        except BudgetExceeded:
            status = "BUDGET_EXCEEDED"
            error = "保守预算检查停止了后续模型调用"
        except AmbiguousCall:
            status = "INTERRUPTED"
            error = "上次模型请求结果不明，已阻止重复收费调用。请新建任务。"
        except Exception:
            status = "INTERRUPTED"
            error = "模型输出、服务调用或执行异常；保留检查点与调用用量，可检查后恢复"
        snapshot = graph.get_state(config)
        s = dict(snapshot.values)
        s["status"] = status or (
            "AWAITING_APPROVAL"
            if snapshot.interrupts
            else s.get("status", "INTERRUPTED")
        )
        s["error"] = error or s.get("error", "")
        s["durationMs"] = journal.add_duration(
            request.runId, round((time.monotonic() - started) * 1000)
        )
        s.pop("activeSkill", None)
        # Credentials were captured in request-local node closures, never serialized.
        return {
            **s,
            **journal.usage(request.runId),
            "resumable": bool(snapshot.next)
            and journal.usage(request.runId)["usageKnown"],
        }
