# job-radar

Scans company career boards for the roles I actually want, remembers what I've already
applied to, and publishes the new matches as a page I can open from anywhere.

Built because the job boards are the wrong shape for this: they show me the same postings
every visit with no memory of which ones I've already dealt with, and they bury silicon
roles under a pile of unrelated engineering titles.

## How it works

1. **Fetch** — hits each company's ATS API directly (Greenhouse, Lever, Ashby,
   SmartRecruiters, Workday) rather than scraping careers pages. That's where the
   postings actually live, it returns clean JSON, and it doesn't break every time
   someone reskins a website.
2. **Match** — scores each title against the role profiles in `config/roles.yaml`
   and filters by location.
3. **Remember** — anything already in `data/seen.json` isn't "new"; anything in
   `data/applied.json` is marked as applied and can be hidden. Both are committed
   to the repo, so the history of the search is diffable and survives a host change.
4. **Publish** — writes a self-contained `site/index.html`, deployed to GitHub Pages.

## Usage

```bash
pip install -r requirements.txt

./jobradar.py check           # verify every configured board still resolves
./jobradar.py scan            # fetch, match, write site/index.html
./jobradar.py scan --print-new --new-only

./jobradar.py applied a1b2c3d4e5f6      # mark as applied (id or full job URL)
./jobradar.py applied <url> --note "referred by X"
./jobradar.py log                        # everything applied, newest first
./jobradar.py unapplied a1b2c3d4e5f6     # undo
```

The report page has an "Applied ✓" button on each card that builds the
`./jobradar.py applied ...` command for you to paste — the committed JSON stays the
source of truth, so nothing depends on browser storage.

## Running it on demand

GitHub Actions, free: **Actions → scan → Run workflow**. It also runs Mon/Thu at 06:00 UTC.
Each run commits the updated seen log and redeploys the Pages site.

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
  sources/        one adapter per ATS, self-registering
  matcher.py      role scoring + location filter
  store.py        seen / applied logs (atomic JSON writes)
  report.py       fills template.html
  cli.py
config/           roles.yaml, companies.yaml
data/             seen.json, applied.json  (committed)
```

Adding an ATS is one file in `jobradar/sources/` with a `@register("name")` decorator
and an import line in that package's `__init__.py`.
