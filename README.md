# job-radar

Scans company career boards for the roles I actually want, remembers what I've already
applied to, and publishes the new matches as a page I can open from anywhere.

Built because the job boards are the wrong shape for this: they show me the same postings
every visit with no memory of which ones I've already dealt with, and they bury silicon
roles under a pile of unrelated engineering titles.

## How it works

1. **Fetch** — hits each company's ATS API directly (Greenhouse, Lever, Ashby,
   SmartRecruiters, Workday, Comeet) rather than scraping careers pages. That's where the
   postings actually live, it returns clean JSON, and it doesn't break every time
   someone reskins a website. Comeet in particular is where most of the Israeli chip
   scene hosts (Nuvoton, Ceva, NextSilicon, Quantum Machines, proteanTecs, …). Several
   big-tech employers that run their own careers site are read the same way, through
   their public search APIs: **Amazon** (Annapurna Labs silicon), **Google**,
   **Microsoft**, **Qualcomm**, and **Texas Instruments** (Oracle) — all location-filtered
   to Israel server-side. A few more (Vayyar via Workable, AMD, and Arm/Synopsys via small
   HTML parsers) are wired up but quiet for now — they'll surface automatically when those
   companies post Israel roles.
2. **Match** — scores each title against the role profiles in `config/roles.yaml`
   and filters by location. `scan --deep` also reads job *descriptions*, so a posting
   whose title hides the role — a "VLSI Engineer" or "Systems Engineer" that's really
   verification or chip design — still gets caught.
3. **Recommend a CV** — tags each match with the CV to send. By default that's the CV
   mapped to the job's role (`config/cvs.yaml`). With `scan --deep` it reads each job's
   *description* and the *text of your CVs* and picks the best fit per job, with the
   reason ("uvm, sva assertions, functional coverage") — catching the crossovers a title
   alone hides. Local only; the file itself never leaves your machine.
4. **Publish** — writes a self-contained `site/index.html`, deployed to GitHub Pages.
   The scan is **stateless**: it renders the current matches and nothing personal.
5. **Remember, privately** — "new since last visit" and "hide the ones I applied to"
   are tracked in your **browser**, per device. The `applied` CLI log
   (`data/applied.json`) is a local, gitignored record — what you applied to, when,
   which CV. Nothing personal is ever committed or published.

## Usage

```bash
pip install -r requirements.txt

./jobradar.py check           # verify every configured board still resolves
./jobradar.py scan            # fetch, match, write site/index.html
./jobradar.py scan --print    # ...and print the matches
./jobradar.py scan --deep     # read job descriptions + your CVs, pick a CV per job

./jobradar.py cv list                   # which CV maps to which role; are the files there
./jobradar.py applied a1b2c3d4e5f6 --cv Verification   # mark applied (id or job URL)
./jobradar.py applied <url> --note "referred by X"
./jobradar.py log                        # everything applied, newest first
./jobradar.py unapplied a1b2c3d4e5f6     # undo
```

The report page has an "Applied ✓" button on each card that builds the
`./jobradar.py applied ...` command (with the right `--cv`) for you to paste, so your
local log stays in sync with what you mark on the page.

## Running it on demand

GitHub Actions, free: **Actions → scan → Run workflow**. It also runs Mon/Thu at 06:00 UTC.
The run is stateless — it just deploys the page; it commits nothing.

First-time setup, once: **Settings → Pages → Source: GitHub Actions**.

## Configuration

`config/roles.yaml` — what counts as a match.

Scoring is title-only and deliberately simple: 3 points per `match_any` keyword found in
the title, 1 per `boost` keyword, and `min_score` (default 3) to make the cut — so a
posting needs at least one primary keyword in its title. ATS list endpoints don't return
descriptions, and fetching thousands of them per scan to grep the body text isn't worth
it; a keyword in the title is the stronger signal anyway.

`config/companies.yaml` — where to look. Every board shipped here was verified live.
Board tokens do change, so run `./jobradar.py check` after editing; it's the difference
between a loud failure and a board quietly contributing zero jobs forever.

Adding a company means finding its ATS: look at where its "Apply" button goes.
The header comment in `companies.yaml` maps each ATS's public URL to the config it needs.

## LinkedIn / Indeed

The `jobspy` source type (via [JobSpy](https://github.com/speedyapply/JobSpy)) covers the
companies with no reachable ATS — Qualcomm, Google, AMD, Synopsys, Apple all post there
and nowhere this tool can otherwise read. Installed by default.

These entries are `ci: false`: LinkedIn blocks datacenter IPs, so the sweeps run from your
machine, not from Actions. CI installs `requirements-core.txt` accordingly.

## Layout

```
jobradar/
  sources/        one adapter per ATS, self-registering (+ description fetchers)
  matcher.py      role scoring + location filter
  cvs.py          role -> CV mapping
  cvtext.py       CV text extraction (PDF/DOCX/TXT)
  cvmatch.py      per-job CV pick from description + CV text (--deep)
  store.py        the local applied log (id -> metadata via the last scan)
  report.py       fills template.html
  cli.py
config/           roles.yaml, companies.yaml, cvs.yaml
cv/               your CVs (gitignored; only the README is tracked)
data/             applied.json + latest.json — local only, gitignored
```

Adding an ATS is one file in `jobradar/sources/` with a `@register("name")` decorator
and an import line in that package's `__init__.py`.
