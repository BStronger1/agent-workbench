"""Explicit LangGraph: plan -> approval -> code -> browser -> review -> repair."""

import hashlib, json, sqlite3, time
from datetime import datetime, timezone
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import interrupt, Command
from .models import Contract, Plan, Code, Review
from .journal import BudgetExceeded, AmbiguousCall


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


def build(checkpointer, model, validator):
    def plan(s):
        contract = dict(s["contract"])
        if s["workflow"] == "graph_multi":
            p = model.call(
                "planner",
                "You are the requirements planner. Produce a concise implementation plan and executable browser steps. Use data-testid targets. Preserve every supplied step exactly. Text assertions require exact trimmed text equality. Include input/check prerequisites when the user task needs them, a primary-action click and a result assertion. Never weaken required texts.",
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
        reply = model.call(
            f"coder-{n}",
            "You are the coding agent. Build a complete self-contained HTML app with inline CSS/JS, doctype, title, h1 and viewport. No external URLs, network calls, iframe, form, imports or downloads. Implement every frozen test step using matching data-testid attributes. Do not change the contract. Return only the complete HTML document.",
            data,
            Code,
        )
        return {
            "html": reply["html"],
            "events": event(
                s, "generate" if n == 0 else "repair", f"编码角色第 {n + 1} 次生成"
            ),
        }

    def validate(s):
        if fingerprint(s["contract"]) != s["contractHash"]:
            raise ValueError("Contract changed")
        attempts = s.get("attempts", [])
        a = validator(s["runId"], len(attempts), s["html"], s["contract"])
        return {
            "attempts": attempts + [a],
            "events": event(s, "validate", a["browserStatus"]),
        }

    def review(s):
        a = s["attempts"][-1]
        result = model.call(
            f"reviewer-{len(s['attempts']) - 1}",
            "You are an independent code reviewer. Inspect requirement coverage and browser failure evidence. Give up to 8 concrete repair suggestions. You cannot alter acceptance steps or override browser results. Empty issues when none. Never request extra tools or network.",
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
        ("finish", finish),
    ]:
        g.add_node(name, fn)
    g.add_edge(START, "plan")
    g.add_edge("plan", "approval")
    g.add_edge("approval", "code")
    g.add_edge("code", "validate")
    g.add_conditional_edges("validate", after_validate)
    g.add_conditional_edges("review", after_review)
    g.add_edge("finish", END)
    return g.compile(checkpointer=checkpointer)


def execute(request, data, model, validator, journal):
    started = time.monotonic()
    thread = hashlib.sha256(
        f"{request.owner}/{request.projectId}/{request.runId}".encode()
    ).hexdigest()
    config = {"configurable": {"thread_id": thread}, "recursion_limit": 40}
    with sqlite3.connect(data / "checkpoints.sqlite", check_same_thread=False) as conn:
        graph = build(SqliteSaver(conn), model, validator)
        snapshot = graph.get_state(config)
        if request.resume:
            if not snapshot.values:
                raise ValueError("No checkpoint for this owner and project")
            if (
                snapshot.values["model"] != request.credentials.model
                or snapshot.values["baseUrl"] != request.credentials.baseUrl
            ):
                raise ValueError("Resume requires original model and provider")
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
        # Credentials were captured in request-local node closures, never serialized.
        return {
            **s,
            **journal.usage(request.runId),
            "resumable": bool(snapshot.next)
            and journal.usage(request.runId)["usageKnown"],
        }
