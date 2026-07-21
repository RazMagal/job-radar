# HOW TO

Practical recipes. For what the project *is*, see [README.md](README.md).

- [First-time setup](#first-time-setup)
- [The daily loop](#the-daily-loop)
- [Keeping the applied log private](#keeping-the-applied-log-private)
- [Adding a company](#adding-a-company)
- [Tuning what matches](#tuning-what-matches)
- [LinkedIn and Indeed](#linkedin-and-indeed)
- [Running it in the cloud](#running-it-in-the-cloud)
- [When something breaks](#when-something-breaks)

---

## First-time setup

```bash
cd ~/job-radar
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt        # ~300 MB, mostly pandas via jobspy
.venv/bin/python jobradar.py check               # all boards should say OK
```

If you want the lean install (ATS boards only, ~19 MB, no LinkedIn/Indeed), use
`requirements-core.txt` instead. The jobspy entries will then fail loudly in `check`,
which is the intended behaviour — a missing source should never look like an empty one.

Everything below uses `./jobradar.py`; substitute `.venv/bin/python jobradar.py` if the
venv isn't on your PATH.

One-time on GitHub, if you want the hosted page: **Settings → Pages → Source: GitHub Actions**.
(Already done for this repo.)

---

## The daily loop

```bash
./jobradar.py scan --print-new     # fetch everything, print what's new
```

Open `site/index.html`, or the hosted page. Then for each job you actually apply to:

```bash
./jobradar.py applied <id>                          # id from the page or --print-new
./jobradar.py applied <full-job-url>                # URL works too
./jobradar.py applied <id> --note "referred by Y"
```

The report page has an **Applied ✓** button on every card that assembles the exact
command for you — click the ones you applied to, hit Copy, paste into a terminal.
The committed JSON is the source of truth; the browser only stages the command, so
nothing is lost if you clear site data.

```bash
./jobradar.py log                  # everything you've applied to, newest first
./jobradar.py unapplied <id>       # undo a misclick
```

Once a job is in the applied log it never counts as "new" again, and the page dims it.

---

## Keeping the applied log private

This repo is public, so by default anyone could read `data/applied.json` and see exactly
where you applied. Encryption fixes that:

```bash
./jobradar.py vault init
```

That generates a key at `~/.config/job-radar/key` (mode 0600), encrypts your existing log
to `data/applied.json.enc`, and deletes the plaintext. From then on the log only ever
exists as ciphertext on disk — `applied`, `log`, and `unapplied` decrypt in memory.

**Back that key up somewhere you won't lose it.** There is no recovery path; lose the key
and the log is gone. A password manager entry is fine.

To let the cloud runs know what you've applied to:

```bash
gh secret set JOBRADAR_KEY --body "$(cat ~/.config/job-radar/key)"
```

Check the state at any time:

```bash
./jobradar.py vault status
```

### Why the page hides applied jobs rather than dimming them

Encrypting the log isn't enough on its own. The published page embeds an `applied` flag
per job, so a public site would leak the same information the encrypted file is hiding.
The workflow therefore runs `scan --redact-applied`, which drops applied jobs from the
published page entirely instead of marking them — from the outside they're
indistinguishable from a closed posting.

Locally, `scan` without that flag still dims them, which is what you want on your own
machine.

### Moving to a new machine

Copy the key to `~/.config/job-radar/key` (or export `JOBRADAR_KEY`), clone the repo, and
the log decrypts as-is.

---

## Adding a company

Find where the company's "Apply" button actually goes — that reveals the ATS:

| The URL looks like | `type:` | config |
|---|---|---|
| `boards.greenhouse.io/acme` | `greenhouse` | `board: acme` |
| `jobs.lever.co/acme` | `lever` | `board: acme` |
| `jobs.ashbyhq.com/acme` | `ashby` | `board: acme` |
| `jobs.smartrecruiters.com/Acme` | `smartrecruiters` | `board: Acme` |
| `acme.wd1.myworkdayjobs.com/Careers` | `workday` | `tenant: acme`, `wd: wd1`, `site: Careers` |

Add it to `config/companies.yaml`, then **always**:

```bash
./jobradar.py check
```

A wrong token is the failure mode that costs you jobs, because it looks identical to
"this company has no openings". `check` is what turns that into a loud error.

### Workday specifically

Workday is the fiddly one. Read the status code — they are the opposite way round from
what you'd guess, which is verified behaviour, not a typo:

- **404** — `tenant` and `wd` are right, **`site` is wrong**. Read the site off the
  careers page URL.
- **422** — **no public Workday tenant** by that name on that `wdN`. Wrong tenant name,
  wrong `wd` number (try `wd1`, `wd3`, `wd5`), or the company isn't on Workday at all.
- **401** — internal-only board; skip it.

Tenant names are often not the company name: Applied Materials is `amat`, not
`appliedmaterials`.

Plenty of big chip companies aren't on any ATS this tool speaks — Qualcomm is on
Eightfold, Synopsys on Avature, AMD and Arm on iCIMS. The bottom of `companies.yaml`
lists these with the ATS each one actually uses, so you don't waste an evening
rediscovering it. The LinkedIn/Indeed sweeps are the practical workaround.

### Lever regions

Lever has a separate EU data region. An EU-hosted board 404s on the US endpoint, which
looks exactly like a wrong token. If a board you're sure about 404s, add `region: eu`
(Mobileye is one).

The `site` is the path segment right after the hostname on the company's careers page.
If the company uses a vanity domain (`careers.acme.com`), follow the redirect or open
devtools and look for the `myworkdayjobs.com` request.

`search_text: Israel` on a Workday entry narrows server-side, which matters — some of
these tenants have tens of thousands of postings worldwide.

---

## Tuning what matches

`config/roles.yaml`. Scoring is title-only: **3** points per `match_any` keyword,
**1** per `boost`, and `min_score` (default 3) to appear at all.

**Too much noise** — raise `min_score` to 4–6, so a title needs a primary keyword *plus*
supporting signal. Or add the offending words to a profile's `exclude`.

**Missing jobs you know exist** — usually the location filter. Run:

```bash
./jobradar.py scan --dry-run --print-new
```

`--dry-run` doesn't touch the seen log, so you can iterate on config without burning the
"new" status of real postings. Temporarily emptying `locations_any` tells you fast whether
location or keywords are to blame.

**A note on `locations_any`**: it's a plain substring match, which is why `remote` was
removed — postings like `Remote-Friendly (Travel-Required) | San Francisco, CA` contain
it but are US roles. Both English and Hebrew place names are listed, because Indeed
returns Hebrew (`תל אביב -יפו, TA, IL`) and the ATS APIs return English.

---

## LinkedIn and Indeed

Installed by default with `requirements.txt`. These sweeps are what cover the companies
with no reachable ATS — Qualcomm, Google, AMD, Synopsys, Apple. Nothing else in the tool
can see those postings.

The `jobspy` entries in `config/companies.yaml` are keyword *searches*, not board dumps:
LinkedIn and Indeed have no "list everything at this company" endpoint, so each role you
care about needs its own entry with its own `search_term`. Verified working for Israel on
2026-07-20.

Three things to know:

- **They're `ci: false` on purpose.** LinkedIn blocks datacenter IPs. These work from your
  home connection and will likely return nothing from GitHub Actions. That's also why CI
  installs `requirements-core.txt` — no point pulling 120 MB of pandas into a run that
  can't use it.
- **Glassdoor is unsupported.** jobspy has no Glassdoor domain for Israel and *raises*
  rather than skipping, which would take out the whole batch. The adapter rejects it.
- **[python-jobspy](https://github.com/speedyapply/JobSpy) is effectively unmaintained**
  (last publish mid-2025). It will break eventually. The adapter calls each site
  separately and treats an empty result as a failure, so when it rots you'll see it in
  `check` rather than silently getting fewer jobs.

---

## Running it in the cloud

**Actions → scan → Run workflow.** Also fires automatically Mon/Thu at 06:00 UTC.

Each run scans, commits the updated seen log as `github-actions[bot]`, and redeploys the
page. Bot identity is deliberate — automated data churn shouldn't inflate your
contribution graph.

Change the schedule in `.github/workflows/scan.yml`:

```yaml
- cron: "0 6 * * 1,4"    # Mon + Thu 06:00 UTC
```

The run's summary page shows a markdown digest of new matches, so you can triage from the
Actions tab without opening the site.

---

## When something breaks

**`check` says a board FAILed** — the token changed. Open the company's careers page and
re-derive it per [Adding a company](#adding-a-company).

**`check` says EMPTY** — the board resolves but has zero postings. Usually genuine;
occasionally means the company migrated ATS and left an empty shell behind.

**A scan shows 0 new forever** — expected once you've seen everything. Confirm with
`./jobradar.py scan --dry-run` and check the total. If the total dropped sharply, a board
is failing.

**Jobs you already applied to came back as new** — the posting's title or location changed,
which changes its fingerprint. Re-mark it; the old entry is harmless.

**`cannot decrypt the applied log — wrong key`** — `JOBRADAR_KEY` in your environment
doesn't match the key the file was encrypted with. Fix the key; don't delete the file.

**The whole run fails in CI but works locally** — most likely an IP block. Anything
`ci: false` is excluded from cloud runs for exactly this reason.
