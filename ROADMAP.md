# Roadmap

Things worth building next, with the design problems already scouted so the work
doesn't start cold.

---

## Multi-CV: pick the best CV per job

**Idea.** Keep several tailored CVs — verification, chip design, Linux, AI research —
and have each matched job say which one to send.

**Why it isn't trivial.** The obvious version (one CV per role profile, chosen by
`job.role`) takes about ten lines and is already 80% right, because the role profiles
are the same axis the CVs would be tailored along. Build that first and see whether the
remaining 20% actually bothers you before going further.

The interesting version picks per *job* rather than per *role* — a "Verification
Engineer" posting that leans heavily on Python and CI infrastructure might be better
served by the Linux CV. That needs signal the tool doesn't currently collect.

### Blocker: matching is title-only

Nothing downstream of the fetch layer has job descriptions, and picking a CV from a
title alone is barely better than picking from the role. Descriptions cost an extra
request per job on some ATSes:

| ATS | How to get the description | Cost |
|---|---|---|
| Greenhouse | `/jobs?content=true` on the existing list call | free, one call |
| Ashby | `descriptionHtml` already in the list response | free |
| Lever | `descriptionPlain` already in the list response | free |
| SmartRecruiters | per-posting `GET /postings/{id}` | 1 request/job |
| Workday | per-posting `GET /wday/cxs/.../job/{path}` | 1 request/job |

So three of five are free or nearly so. Suggested approach: add an opt-in
`--deep` flag that fetches descriptions only for jobs that already matched, which keeps
it to tens of requests rather than thousands. Cache them on disk keyed by job id — they
don't change.

### Then: how to choose

Two options, worth trying in this order.

1. **Keyword overlap.** Extract the skill vocabulary from each CV once, score it against
   the job description, pick the best. Deterministic, free, debuggable, no network. Likely
   good enough, and it produces an explanation for free ("matched: UVM, SystemVerilog,
   formal") which is the part you'd actually act on.
2. **Ask a model.** Send description + CV summaries to the Claude API and have it pick
   with a one-line justification. Better at the fuzzy cases, but adds an API key, a cost
   per scan, and non-determinism. Only worth it if (1) demonstrably misfires.

Keep whichever choice explainable — a bare "use CV #2" with no reason is not actionable
when you're deciding what to actually send.

### Watch out: CVs are personal data

A CV has your address, phone number and full work history. **It must not land in a public
repo.** The applied-log problem, again — and the fix already exists:

- store CVs under `cv/`, gitignored, encrypted via the existing `jobradar vault`
  machinery (`jobradar/vault.py` is agnostic about what it encrypts),
- never let a CV filename or content reach `site/index.html`; the page is world-readable.
  A neutral label like "CV: verification" is fine, the file itself is not.

### Also worth having

- `jobradar.py cv list` / `cv add <path> --label verification`
- CV recommendation as a column in the report and in the markdown digest
- Track *which* CV you sent in the applied log, so you can tell later which version
  actually got replies — that's the data that makes the whole feature worth having.

---

## Smaller things

- **Description-based matching generally.** The `--deep` fetch above also improves plain
  matching, not just CV choice — a posting whose title says "Systems Engineer" but whose
  body is all UVM currently scores 0.
- **More ATS adapters.** The big misses are documented at the bottom of
  `config/companies.yaml`: Eightfold (Qualcomm), Avature (Synopsys), iCIMS (AMD, Arm),
  Comeet (Hailo, NextSilicon, Ceva). Comeet needs a per-company API token that isn't in
  the page HTML; the others look scrapeable.
- **Dedup across sources.** The same job from LinkedIn and from the company's ATS has
  different titles and location spellings (one Hebrew, one English), so the fingerprint
  differs and it shows up twice.
- **Alerting.** A zero-row LinkedIn result means "blocked", not "no jobs" — worth
  surfacing distinctly rather than as a quiet failure line.
