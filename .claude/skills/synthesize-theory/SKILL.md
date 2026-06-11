---
description: Sintetiza todos los digests de `methods/theory_assisted/digest/` en `methods/theory_assisted/jobs/notes/synthesis.md`, con temas convergentes, ángulos diferenciados y 2–4 candidatos algorítmicos concretos para paper #2. Uso: `/synthesize-theory [foco opcional]`. Despacha al subagente `theory-synthesize`.
arguments: focus
context: fork
agent: theory-synthesize
---

Produce the theory synthesis for the `theory_assisted` method.

Optional focus from the user: **$focus**

Follow the workflow in your agent system prompt:

1. Glob and Read every file under `methods/theory_assisted/digest/*.md`.
2. Read `problems/jobs/problem_statement.md`.
3. Honour the isolation contract: do NOT read
   `methods/theory_assisted/inspiration/` (the PDFs are already
   digested), `literature_review/`, `methods/manual/`,
   `methods/autoresearch/`, or `papers/`.
4. Write the synthesis to
   `methods/theory_assisted/jobs/notes/synthesis.md` using the template
   in the agent prompt.  Sort the "Digests considered" table by
   verdict (High → Medium → Low).
5. Return a short summary: the 2–4 candidate names with one-line each,
   and your single highest-confidence recommendation.

If a focus argument is given (e.g. "GRASP-heavy", "matheuristic",
"hyper-heuristic angle"), bias which candidate approaches you put
forward — but still list any high-verdict transfers you'd be cutting
out under "Open questions" so the human can override.
