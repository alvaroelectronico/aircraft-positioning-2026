---
description: Destila un paper de literature_review/papers/ en un digest estructurado para el método `theory_assisted`. Uso: `/digest-paper <pdf_path> [foco opcional]`. Despacha al subagente `theory-paper-digest`.
arguments: pdf_path focus
context: fork
agent: theory-paper-digest
---

Digest the external paper at: **$pdf_path**

Optional focus from the user: **$focus**

Follow the workflow and template described in your agent system prompt:

1. Read `problems/jobs/problem_statement.md` first.
2. Read the PDF in chunks (start pages 1–5).
3. Skim `literature_review/report_consensus.txt` for context.
4. Check existing digests under
   `methods/theory_assisted/jobs/notes/literature_digest/` to
   cross-reference and avoid repetition.
5. Write the digest to
   `methods/theory_assisted/jobs/notes/literature_digest/<slug>.md`,
   where `<slug>` is the PDF basename without `.pdf`.
6. Return a short summary to the main conversation: title, verdict
   (High/Medium/Low), and the single most transferable idea.

Respect the theory_assisted isolation contract: do not read
`methods/manual/`, `methods/autoresearch/`, or `papers/`.  If the
optional focus is empty, do a general digest; if it mentions a specific
angle (e.g. "GRASP construction", "Mode-A scheduling", "blocking
constraints"), bias the **What transfers** section toward that angle.
