"""The tailoring agent as a LangGraph StateGraph.

Nodes are exactly the functions in app/agent/pipeline.py, so outputs and progress
events match `run_pipeline`. `ask_user` interrupts the graph; the checkpoint (SQLite,
keyed by thread_id = run_id) lets the next `run()` for the same run resume from it.
"""

import logging
import sqlite3
from collections.abc import Callable
from typing import Any, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from app.agent import pipeline as p
from app.agent.tailor import AgentInput, AgentResult

log = logging.getLogger(__name__)


class GState(TypedDict, total=False):
    answers: list
    context: list
    ranked: list
    plan_out: dict
    examples: list
    questions: list
    attempt: int
    drafts: list
    violations: list
    draft: dict
    note: str | None
    retry: bool


def open_checkpointer(path: str) -> SqliteSaver:
    conn = sqlite3.connect(path, check_same_thread=False)
    return SqliteSaver(conn)


def build_graph(ctx: p.Ctx, checkpointer):
    g = StateGraph(GState)
    for name, fn in (
        ("load_context", p.load_context),
        ("rank_items", p.rank_items),
        ("plan", p.plan),
        ("write_draft", p.write_draft),
        ("fact_check", p.fact_check_node),
        ("coverage_and_render", p.coverage_and_render),
    ):
        g.add_node(name, lambda s, fn=fn: fn(ctx, s))

    def ask_user(state: GState) -> dict[str, Any]:
        given = interrupt({"questions": state["questions"]})
        merged = {a[0].lower(): list(a) for a in state["answers"]}
        merged |= {a[0].lower(): list(a) for a in given}
        return {"answers": list(merged.values()), "questions": []}

    g.add_node("ask_user", ask_user)
    g.add_edge(START, "load_context")
    g.add_edge("load_context", "rank_items")
    g.add_edge("rank_items", "plan")
    g.add_conditional_edges(
        "plan",
        p.route_after_plan,
        {"ask_user": "ask_user", "write_draft": "write_draft"},
    )
    g.add_edge("ask_user", "load_context")  # re-plan with the new answers
    g.add_edge("write_draft", "fact_check")
    g.add_edge("fact_check", "coverage_and_render")
    g.add_conditional_edges(
        "coverage_and_render",
        p.route_after_render,
        {"write_draft": "write_draft", "end": END},
    )
    return g.compile(checkpointer=checkpointer)


class GraphTailorAgent:
    """Implements the TailorAgent protocol on top of the graph."""

    def __init__(self, deps: p.Deps, checkpointer=None, path: str | None = None):
        self.deps = deps
        self._saver = checkpointer
        self._path = path

    @property
    def saver(self):
        if self._saver is None:
            self._saver = open_checkpointer(self._path or ":memory:")
        return self._saver

    def run(self, inp: AgentInput, should_stop: Callable[[], bool]) -> AgentResult:
        ctx = p.Ctx(inp, self.deps, should_stop)
        graph = build_graph(ctx, self.saver)
        cfg = {"configurable": {"thread_id": inp.run_id}}
        before = self.deps.llm.cost_usd
        if graph.get_state(cfg).next:  # paused at ask_user: resume from the checkpoint
            arg: Any = Command(resume=[list(a) for a in inp.answers])
            log.info("tailor graph resume run=%s", inp.run_id)
        else:
            self.saver.delete_thread(inp.run_id)  # a finished earlier pass is stale
            arg = p.initial_state(inp)
        try:
            graph.invoke(arg, cfg)
        except p.Stopped:
            return AgentResult()
        snap = graph.get_state(cfg)
        result = p.build_result(ctx, dict(snap.values), before)
        if not snap.next:
            self.saver.delete_thread(inp.run_id)  # finished: nothing to resume
        return result
