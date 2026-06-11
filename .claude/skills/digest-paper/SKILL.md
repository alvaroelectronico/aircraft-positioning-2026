---
description: Destila un archivo de `methods/theory_assisted/inspiration/` en un digest estructurado dentro de `methods/theory_assisted/digest/`. Uso: `/digest-paper <path> [foco opcional]`. Despacha al subagente `theory-paper-digest`.
arguments: source_path focus
context: fork
agent: theory-paper-digest
---

Digest the source at: **$source_path**

Optional focus from the user: **$focus**

Follow the workflow and template described in your agent system prompt:

1. Read `problems/jobs/problem_statement.md` first.
2. Read the source (chunk PDFs by pages: start with pages 1–5).
3. Check existing digests under `methods/theory_assisted/digest/` to
   cross-reference and avoid repetition.
4. Write the digest to `methods/theory_assisted/digest/<slug>.md`,
   where `<slug>` is the source basename without its extension.
5. Return a short summary to the main conversation: title, verdict
   (High/Medium/Low), and the single most transferable idea.

Respect the theory_assisted isolation contract: read only
`methods/theory_assisted/inspiration/`, `problems/jobs/`, and existing
digests.  Do NOT read `literature_review/`, `methods/manual/`,
`methods/autoresearch/`, or `papers/`.  If the optional focus is empty,
do a general digest; if it mentions a specific angle (e.g. "GRASP
construction", "Mode-A scheduling", "blocking constraints"), bias the
**What transfers** section toward that angle.
