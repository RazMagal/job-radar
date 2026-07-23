# Roadmap

Things worth building next, with the design problems already scouted so the work
doesn't start cold.

---

## Multi-CV: pick the best CV per job — SHIPPED

Both stages are built. Stage 1 maps each role to a CV; Stage 2 (`scan --deep`) reads job
descriptions and the text of the CVs and picks per job, with the reason.

**How descriptions are fetched** (all verified live):

| ATS | How | Cost |
|---|---|---|
| Greenhouse | `?content=true` on the existing list call | free, one call |
| Ashby | `descriptionPlain` already in the list response | free |
| Lever | assemble `descriptionPlain` + `lists[]` + `additionalPlain` | free |
| Workday | per-job `GET /wday/cxs/{tenant}/{site}{externalPath}` | 1 request per *matched* job |
| SmartRecruiters | not implemented — falls back to the role mapping | — |

Only matched jobs get the per-job fetch, so it's tens of requests, not thousands.

**How it chooses.** TF-IDF across your own CV corpus: a term in every CV carries no
signal, a term distinctive to one carries it all; bigrams count double. Deterministic,
offline, and every pick reports the terms that drove it. A description-based pick must
beat the role default by 30% to overrule it — otherwise a Linux SRE role at an AI company
gets yanked to the AI CV by ambient GPU vocabulary.

**Not done: the LLM variant.** Sending the description plus CV summaries to the Claude API
would handle the fuzzy cases better, at the cost of an API key, per-scan spend, and
non-determinism. Worth revisiting only if the deterministic matcher demonstrably misfires
on real postings — so far it hasn't.

**Possible refinements**
- Cache fetched descriptions on disk keyed by job id (they don't change) to make repeat
  `--deep` runs cheap.
- A SmartRecruiters describer, if a board that uses it ever gets added.
- Tune `MIN_CV_SCORE` / `OVERRIDE_MARGIN` in `cli.py` once there's a feel for real
  false positives.

### CVs are personal data (handled)

A CV has your address, phone number and full work history, so it must not land in a public
repo. The `cv/` folder is gitignored (only its README is tracked) and only the CV *label*
and the matched *terms* ever reach the page — never the filename or the content. `--deep`
reads the files into memory, matches, and discards; nothing is written or transmitted, and
it runs locally only because the cloud runner has no copy of them.

### Also worth having

- `jobradar.py cv add <path> --label verification` (right now you drop files in `cv/` and
  edit `config/cvs.yaml` by hand).
- Once you have replies, correlate them with the `cv` field in the applied log to see
  which CV actually lands interviews — the payoff that makes the whole feature worth it.

---

## Smaller things

- **Description-based *role* matching.** `--deep` already fetches descriptions, but
  `matcher.py` still scores role fit on the title alone — so a posting titled "Systems
  Engineer" with an all-UVM body never enters the results at all, and the CV matcher
  never sees it. Feeding the description into role scoring under `--deep` would widen the
  net, at the cost of more noise; worth trying with a higher `min_score`.
- **More ATS adapters.** The big misses are documented at the bottom of
  `config/companies.yaml`: Eightfold (Qualcomm), Avature (Synopsys), iCIMS (AMD, Arm),
  Comeet (Hailo, NextSilicon, Ceva). Comeet needs a per-company API token that isn't in
  the page HTML; the others look scrapeable.
- **Dedup across sources.** The same job from LinkedIn and from the company's ATS has
  different titles and location spellings (one Hebrew, one English), so the fingerprint
  differs and it shows up twice.
- **Alerting.** A zero-row LinkedIn result means "blocked", not "no jobs" — worth
  surfacing distinctly rather than as a quiet failure line.
