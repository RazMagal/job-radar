# HOW TO

Practical recipes. For what the project *is*, see [README.md](README.md).

- [First-time setup](#first-time-setup)
- [The daily loop](#the-daily-loop)
- [Which CV to send (`--deep`)](#which-cv-to-send---deep)
- [How privacy works](#how-privacy-works-nothing-personal-leaves-your-machine)
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
./jobradar.py scan --print         # fetch everything, print the matches
```

Open `site/index.html`, or the hosted page. Jobs new since your last visit on this device
are badged; use **New only** and **Hide applied** to focus. Then for each job you apply to:

```bash
./jobradar.py applied <id> --cv Verification         # id from the page or --print
./jobradar.py applied <full-job-url>                 # URL works too
./jobradar.py applied <id> --note "referred by Y"
```

The report page has an **Applied ✓** button on every card that assembles the exact
commands for you — click the ones you applied to (the page fills in the right `--cv`), hit
Copy, and paste into a terminal to persist them to your local log.

```bash
./jobradar.py log                  # everything you've applied to, newest first
./jobradar.py unapplied <id>       # undo a misclick
```

Marking a job applied dims it on the page (browser-side) and records it in
`data/applied.json` once you run the command.

---

## Which CV to send (`--deep`)

Every match carries a `send: X` label. By default that's just the CV mapped to the job's
role in `config/cvs.yaml` — which mostly restates the role and isn't worth much.

`--deep` makes it mean something:

```bash
./jobradar.py scan --deep --print
```

It fetches each matched job's **description**, reads the **text of your actual CVs** in
`cv/`, and picks the best fit per job — with the reason:

```
  [ 7] Mobileye: Experienced SoC Verification Engineer — Haifa  [Verification]
       why: verification, coverage, uvm, axi, simulation, soc
```

How it decides: terms are weighted by TF-IDF across your own CVs, so something that
appears in *every* CV barely counts while a term distinctive to one — `uvm`, `pytorch`,
`device driver` — carries the signal. Two-word terms ("design verification") count double.
No LLM, no API key, no network beyond the job boards; the same input always gives the
same answer, and every pick shows its evidence.

**It only overrules the role default when it's decisive** (30% better). A Linux SRE role
at an AI company is thick with GPU and accelerator terms, but you'd still send the Linux
CV — so a modest lead isn't enough. A "Systems Engineer" posting whose body is all UVM
*is* decisive, and gets flipped to the verification CV. That crossover is the whole point.

Notes:

- **Local only.** Your CVs are gitignored, so the cloud runner has no access to them. The
  cloud page keeps the plain role mapping; run `--deep` on your laptop, which is where you
  apply from anyway.
- **Slower.** Workday needs one extra request per matched job (its list carries no
  description); Greenhouse, Ashby and Lever hand theirs over in the call already made.
  Under `--deep`, LinkedIn/Indeed also fetch descriptions, which is the slow part.
- **Needs the CV files.** Without readable files in `cv/` it says so and keeps the role
  mapping. Scanned/image-only PDFs extract nothing — there's no OCR.
- Descriptions are used in memory and thrown away. They're never written to disk or
  published.

---

## How privacy works (nothing personal leaves your machine)

The repo is public, but nothing personal is ever committed or published — by design, not
by encryption. Three things stay local, all gitignored:

- **`data/applied.json`** — your applied log (what, when, which CV).
- **`data/latest.json`** — the last scan's catalog, used to resolve job ids.
- **`cv/`** — your actual CV files (only the README is tracked).

The cloud scan is **stateless**: it fetches public job postings, matches them, and deploys
the page. It never sees your applied log or CVs, so there is nothing to leak.

### "New" and "hide applied" live in your browser

Because the cloud keeps no memory of you, the page itself remembers — in your browser's
localStorage, per device:

- **New** — the page records which jobs it showed last time and badges the newcomers, so
  "new since last visit" works on your phone with no server-side history. It's per-device:
  your phone and laptop track "new" separately (fine for a personal glance).
- **Applied** — clicking **Applied ✓** marks a job in localStorage (dims it; **Hide
  applied** filters it) and builds the `./jobradar.py applied <id> --cv <label>` command,
  one line per marked job, to paste on your laptop so the durable log stays in sync.

No key, no secret, nothing to back up. If you wipe browser storage the only loss is the
per-device "new"/"applied" highlighting; the durable log on your laptop is untouched.

### Moving to a new machine

Copy `data/applied.json` and your `cv/` files across — they're not in git. That's it;
there's no key or encrypted state to migrate.

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
| `comeet.com/jobs/acme/12.345` | `comeet` | `uid: "12.345"`, `token: "<harvested>"` |

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

### Comeet specifically

Most of the Israeli chip scene (Nuvoton, Ceva, NextSilicon, Quantum Machines,
proteanTecs, …) is on Comeet, and it needs **two** values — a per-company `uid` and a
`token`, both baked into the Comeet-hosted page. Harvest them once (they're stable):

```bash
curl -sL https://www.comeet.com/jobs/<slug>/<uid> | grep -oiE '"(uid|token)": *"[^"]+"'
```

The `<uid>` is the one in the URL; the `token` is the company one printed near the top.
**Quote both in YAML** — `uid: "76.005"` unquoted is read as a float and breaks. A `400`
from `check` means a wrong/rotated token or a deactivated account (Pliops is one).

Comeet serves no job description, so its jobs are matched on **title only** — the same as
Workday without a describer. That's why `roles.yaml` keeps a rich `match_any` vocabulary
(vlsi, dft, physical design, …) rather than just exact job titles.

### Big-tech career APIs

Some employers run their own careers site but expose a public JSON search — read the same
way as an ATS, each with a fixed `type` (no token to harvest):

| `type:` | who | notes |
|---|---|---|
| `amazon` | Amazon (Annapurna Labs silicon, AWS) | `location`/`country` overridable |
| `qualcomm`, `microsoft` | Qualcomm, Microsoft | shared Eightfold "PCSX" API (`eightfold.py`) |
| `google` | Google | careers-page `batchexecute` RPC — **fragile**: a Google deploy can rotate the RPC id (`check` catches it; re-harvest `RPC` in `google.py`) |
| `oracle` | Texas Instruments | Oracle Recruiting Cloud; needs `host`, `site`, `location_id`, `job_url` |
| `workable` | Vayyar | `board` = the Workable account slug |
| `amd` | AMD | no country filter — pages the whole board and keeps `country_code == IL` (heavy; `ci: false`) |
| `arm`, `avature` | Arm, Synopsys | **HTML scrapers** (no JSON feed) — narrow and isolated, `ci: false` |

To point the `oracle` type at another Oracle-Recruiting employer, load their careers page,
watch the `hcmRestApi/...recruitingCEJobRequisitions` XHR, and copy the `host`, `siteNumber`
and the Israel `selectedLocationsFacet` id into config. The `avature` type likewise takes a
`host` + a `filter` query string pinning the country facet (read it off the site's location
filter).

The last four are wired up but currently **empty/thin** for Israel (Vayyar, AMD and
Synopsys have 0 IL right now; Arm has ~2) — `check` shows them EMPTY until they post, which
is expected, not a failure. The two HTML scrapers (`arm`, `avature`) are the only non-JSON
sources here and are deliberately narrow; if a page layout changes they fail that one board
loudly.

If one of these fails **only in CI** (a datacenter-IP block — most likely `google`), mark
that entry `ci: false` so it runs locally only, like the LinkedIn/Indeed sweeps.

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
./jobradar.py scan --print
```

The scan keeps no server-side state, so you can iterate on config freely and re-run as
often as you like. Temporarily emptying `locations_any` tells you fast whether location or
keywords are to blame.

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

Each run scans and redeploys the page. It's stateless — commits nothing, needs no secret,
touches no personal data.

Change the schedule in `.github/workflows/scan.yml`:

```yaml
- cron: "0 6 * * 1,4"    # Mon + Thu 06:00 UTC
```

The run's summary page shows a markdown digest of the matches grouped by role, so you can
triage from the Actions tab (or the GitHub mobile app) without opening the site.

---

## When something breaks

**`check` says a board FAILed** — the token changed. Open the company's careers page and
re-derive it per [Adding a company](#adding-a-company).

**`check` says EMPTY** — the board resolves but has zero postings. Usually genuine;
occasionally means the company migrated ATS and left an empty shell behind.

**The page shows everything as new (or nothing new)** — "new" is per-device browser state.
A fresh browser or device has no history, so the first visit badges nothing and later
visits badge what changed. Clearing site data resets it. Expected, not a bug.

**Jobs you applied to aren't dimmed here** — applied state is per-device too. If you marked
them on another device, re-mark here (or check `./jobradar.py log` for the durable record).

**The whole run fails in CI but works locally** — most likely an IP block. Anything
`ci: false` is excluded from cloud runs for exactly this reason.
