"""Draw the TraceRoot architecture / workflow diagram to docs/architecture.png.

usage: python draw_architecture.py   (needs matplotlib; the project venv does not include it)
"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "docs", "architecture.png")
W, H = 100, 80
fig, ax = plt.subplots(figsize=(20, 16), dpi=130)
ax.set_xlim(0, W)
ax.set_ylim(0, H)
ax.axis("off")
fig.patch.set_facecolor("white")

C = {  # fill, edge
    "input": ("#eef2f7", "#5b6b82"), "hidden": ("#fdecec", "#c0392b"), "sandbox": ("#fff1e0", "#d4801c"),
    "agent": ("#efe9fb", "#6a4fb3"), "client": ("#f5f0ff", "#8a74c9"), "tools": ("#e8f6ee", "#2e8b57"),
    "gate": ("#fff8dc", "#b8962e"), "out": ("#fffbe6", "#b59a2a"), "eval": ("#e6f6f6", "#1f8a8a"), "human": ("#f2f2f2", "#555555"),
}
RED = "#c0392b"
GREY = "#444444"


def box(x, y, w, h, title, lines, kind, dashed=False, body=10):
    fill, edge = C[kind]
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.25,rounding_size=0.8", fc=fill, ec=edge,
                                lw=2.0, ls=(0, (5, 3)) if dashed else "-", zorder=2))
    ax.text(x + 0.8, y + h - 0.9, title, fontsize=12.5, fontweight="bold", va="top", ha="left", color="#1d1d1d", zorder=3)
    ax.text(x + 0.8, y + h - 3.1, "\n".join(lines), fontsize=body, va="top", ha="left", color="#2b2b2b",
            linespacing=1.42, zorder=3)


def arrow(p, q, label="", color=GREY, dashed=False, rad=0.0, lx=0.0, ly=0.0):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle="-|>", mutation_scale=18, lw=1.8, color=color,
                                 ls=(0, (5, 3)) if dashed else "-", connectionstyle=f"arc3,rad={rad}", zorder=4))
    if label:
        ax.text((p[0] + q[0]) / 2 + lx, (p[1] + q[1]) / 2 + ly, label, fontsize=9.5, color=color, ha="center", va="center",
                bbox=dict(fc="white", ec="none", pad=0.6), zorder=5)


ax.text(1, 79.3, "TraceRoot: investigate, find the root cause, repair and verify a Python regression",
        fontsize=17, fontweight="bold", va="top")
ax.text(1, 76.9, "Every run: one Docker sandbox, one model, a saved transcript and an independent score. "
        "Nothing is merged or deployed.", fontsize=11, va="top", color="#444")

# ---- row 1 (y 60-73): inputs, sandbox builder, docker
box(1, 60, 26, 13.5, "Case inputs   cases/<id>/", [
    "Given to the agent:",
    "  report.md        bug report",
    "  stacktrace.txt   failing trace",
    "Five admitted cases: flask, attrs,",
    "packaging, filelock, click"], "input")
box(30, 60, 30, 13.5, "1  Sandbox builder   build_sandbox_repo.py", [
    "fresh clone at the faulty revision",
    "delete remote, tags, other branches, reflogs",
    "prune objects, write generated shim files",
    "self-check: fix commit is NOT reachable",
    "and NOT in the object store"], "sandbox")
box(63, 60, 36, 13.5, "2  Docker sandbox   traceroot-sandbox:1", [
    "Python 3.13.7 + pinned test deps + git",
    "--network none, 2 CPU, 2 GB, pid limit",
    "workspace mounted at /work (throwaway copy)",
    "one container per run, removed afterwards",
    "no API keys inside (.env stays on the host)"], "sandbox")
arrow((27.3, 66.5), (29.7, 66.5))
arrow((60.3, 66.5), (62.7, 66.5))

# ---- row 2 (y 34-57): hidden, clients, loop, tools
box(1, 37, 26, 20, "Hidden from the agent", [
    "reference/reproduce.py  (evaluator)",
    "fixed revision and its tests",
    "breaking commit (metadata.json)",
    "upstream history after the bug",
    "",
    "Used only by the scorer,",
    "after the run has ended."], "hidden", dashed=True)
box(30, 34, 22, 23, "Model clients", [
    "GeminiClient (REST)",
    "  model chain: switch on daily quota",
    "  pacing: requests/min and tokens/min",
    "  HTTP 503: back off ~12 min",
    "LiveClient (WebSocket)",
    "  audio-only Live models,",
    "  tool calls only, session resume",
    "LocalClient (llama-server)",
    "  free dry runs of the harness",
    "Keys: .env (gitignored)"], "client", body=9.6)
box(54, 34, 21, 23, "3  Agent loop   agent.py", [
    "frozen system prompt",
    "budget per run:",
    "  40 tool calls",
    "  15 min active time",
    "  (rate-limit waits excluded)",
    "  200k context tokens",
    "budget line after each result",
    "independent calls batched",
    "nudge if no tool call (max 3)"], "agent", body=9.6)
box(77, 34, 22, 23, "4  Tools   tools.py  (docker exec)", [
    "Investigate",
    "  list_dir  read_file  search",
    "  git_log  git_show  git_blame",
    "Diagnose",
    "  run_python  run_tests",
    "Hypotheses",
    "  record_hypothesis",
    "  update_hypothesis (cite calls)",
    "Repair:  apply_edit (src/ only)",
    "End:     submit(report)"], "tools", body=9.6)
arrow((52.3, 49), (53.7, 49))
arrow((53.7, 43), (52.3, 43))
ax.text(53, 46, "request\n/ reply", fontsize=8.5, ha="center", va="center", color=GREY)
arrow((75.3, 49), (76.7, 49))
arrow((76.7, 43), (75.3, 43))
ax.text(76, 46, "call\n/ result", fontsize=8.5, ha="center", va="center", color=GREY)
arrow((88, 59.7), (88, 57.3), "runs inside", lx=6)
arrow((20, 59.7), (62, 57.3), "report + trace become the first prompt", lx=4, ly=1.3)

# ---- row 3 (y 17-32): run directory and submit gates
box(6, 17, 46, 14.5, "Run directory   experiments/<case>-agent-<model>-<attempt>/", [
    "transcript.jsonl   every model reply and tool result, unedited",
    "run.json           prompt, tools and code hashes, limits, key NAME only",
    "submission.json    edits, hypotheses, report, decision",
    "workspace.patch    the diff the agent left",
    "result.json        outcome, calls, requests, tokens, active / waited time",
    "Existing run folders are never overwritten."], "out", body=9.6)
box(54, 22, 45, 9.5, "submit is refused unless", [
    "2+ hypotheses, none open, 1+ supported (evidence = earlier call numbers)    |    1+ apply_edit",
    "run_tests after the last edit    |    workspace == HEAD + recorded edits (no hidden changes)"], "gate", body=9.6)
arrow((88, 33.7), (88, 31.8), "submit", lx=4)
arrow((60, 33.7), (45, 31.8), "the loop writes", rad=0.12, lx=3, ly=1.0)

# ---- row 4 (y 1-12.5): post-run pipeline
box(1, 1, 22, 11.5, "5  Report   report.py", [
    "report.json + report.md",
    "checked against",
    "report.schema.json",
    "decision: ready for human review"], "eval", body=9.6)
box(26, 1, 23, 11.5, "6  Evidence check", [
    "evidence_check.py",
    "each claim vs the transcript:",
    "verified / unverifiable /",
    "contradicted"], "eval", body=9.6)
box(52, 1, 25, 11.5, "7  Scoring   score.py", [
    "replay edits on a FRESH checkout",
    "reproducer exits 0 + held-out tests",
    "root cause vs real fix:",
    "match / likely / partial / miss"], "eval", body=9.6)
box(80, 1, 19, 11.5, "8  Results + review", [
    "evaluation.json per run",
    "README table (generated)",
    "a person reviews likely /",
    "partial root causes"], "human", body=9.6)
arrow((14, 16.7), (14, 12.8))
arrow((23.3, 6.5), (25.7, 6.5))
arrow((49.3, 6.5), (51.7, 6.5))
arrow((77.3, 6.5), (79.7, 6.5))

# hidden inputs -> scorer, routed down the left margin and along the corridor at y 14.6
ax.plot([3, 3, 66], [36.7, 14.6, 14.6], color=RED, lw=1.8, ls=(0, (5, 3)), zorder=4)
arrow((66, 14.6), (66, 12.8), color=RED, dashed=True)
ax.text(44, 14.6, "hidden inputs reach only the scorer", fontsize=9.5, color=RED, ha="center", va="center",
        bbox=dict(fc="white", ec="none", pad=0.5), zorder=5)

fig.savefig(OUT, dpi=130, bbox_inches="tight", facecolor="white")
print("saved")
