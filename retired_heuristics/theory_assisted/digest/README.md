# `digest/` — structured digests of inspiration material

One file per source from `methods/theory_assisted/inspiration/`, written
by the `theory-paper-digest` subagent (invoked via the `/digest-paper`
skill).  Each digest follows the template in
`.claude/agents/theory-paper-digest.md`:

- Problem solved by the paper
- Technique used
- What transfers to paper #2 (the heart of the digest)
- What does NOT transfer
- Verdict (High / Medium / Low priority for theory_assisted)
- Cross-references to other digests

Filename convention: `<author><year>.md`, matching the source basename
under `methods/theory_assisted/inspiration/` (e.g.
`inspiration/qin2019.pdf` → `digest/qin2019.md`).

Workflow:

1. Curate `methods/theory_assisted/inspiration/` with the PDFs (and
   any other material) you want this method to consume.
2. Run `/digest-paper methods/theory_assisted/inspiration/<file>.pdf [focus]`.
3. The subagent writes its digest here and returns a short summary
   (title, verdict, single most transferable idea) to the main
   conversation.
4. Over time, synthesise across digests into
   `methods/theory_assisted/jobs/notes/design.md` (the
   implementation plan).
