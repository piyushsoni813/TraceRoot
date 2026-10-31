# Minimal-context baseline: Flask #5160

Status: frozen protocol; not yet run.

This experiment measures whether one LLM can propose an applyable source repair
from only a bug report and a stack trace. It does not give the model repository
source, Git history, test output, tools, the faulty revision, or the reference
repair.

The sole model inputs are the files in `input/`. `reference/` material from the
case is evaluator-only and must never be copied into this experiment directory.
