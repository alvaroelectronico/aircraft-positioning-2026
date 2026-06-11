# Literature digest folder

One file per external paper, written by the `theory-paper-digest`
subagent (invoked via the `/digest-paper` skill).  Each digest follows
the template in `.claude/agents/theory-paper-digest.md`:

- Problem solved by the paper
- Technique used
- What transfers to paper #2 (the heart of the digest)
- What does NOT transfer
- Verdict (High / Medium / Low priority for theory_assisted)
- Cross-references to other digests

Filename convention: `<author><year>.md`, matching the PDF basename
under `literature_review/papers/`.

Workflow:

1. Pick a paper from `literature_review/papers/` (skim
   `literature_review/report_consensus.txt` for which ones look most
   applicable).
2. Run `/digest-paper literature_review/papers/<file>.pdf [focus]`.
3. The subagent writes its digest here and returns a short summary
   (title, verdict, single most transferable idea).
4. Over time, write a `../design.md` that synthesises across digests
   into the actual implementation plan.
