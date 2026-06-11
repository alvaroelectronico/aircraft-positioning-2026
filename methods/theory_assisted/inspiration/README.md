# `inspiration/` — curated theory input for the `theory_assisted` method

Drop here the external material (PDFs, notes, links) that you want this
method to consume.  Anything in this folder is fair game for the
`theory-paper-digest` subagent (via `/digest-paper <path>`).

**This folder is the ONLY external-literature source `theory_assisted`
is allowed to read.**  The repo-wide `literature_review/` is explicitly
*not* on this method's read path — by design, so each method can curate
its own diet of inputs without contamination.

Convention:

- One PDF per paper, named `<author><year>.pdf` (e.g. `qin2019.pdf`).
- Other supporting material (notes you took yourself, links text
  files, slides) is fine here too; just keep the filenames descriptive.
- Cross-link to corresponding digest files in
  `methods/theory_assisted/digest/<slug>.md` (which is where the
  `theory-paper-digest` subagent writes its structured digests).

If you decide a paper that lives in `literature_review/` is relevant,
**copy** it (or symlink) into this folder explicitly — don't reach
across.  That deliberate gesture is the boundary.
