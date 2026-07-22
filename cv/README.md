# CVs

Drop your per-role CVs here (PDF or DOCX). **Everything in this folder except this README
is gitignored** — your CVs never reach the public repo or the published page.

The tool only tells you *which* CV to send for each job; it does not store, read, or
attach the file. Map each file to the roles it covers in [`../config/cvs.yaml`](../config/cvs.yaml).

Suggested filenames (match what's in `config/cvs.yaml`):

- `verification.pdf`
- `chip-design.pdf`
- `linux.pdf`
- `ai-research.pdf`

Check the mapping and that the files are found with:

```bash
./jobradar.py cv list
```

The files are optional for the tool to work — the mapping alone drives the "send: X"
label. `cv list` just warns when a mapped file is missing so you notice a typo.
