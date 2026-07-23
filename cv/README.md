# CVs

Drop your per-role CVs here (PDF, DOCX, TXT or MD). **Everything in this folder except
this README is gitignored** — your CVs never reach the public repo or the published page.

Map each file to the roles it covers in [`../config/cvs.yaml`](../config/cvs.yaml).

Suggested filenames (match what's in `config/cvs.yaml`):

- `verification.pdf`
- `chip-design.pdf`
- `linux.pdf`
- `ai-research.pdf`

Check the mapping and that the files are found with:

```bash
./jobradar.py cv list
```

## What the files are actually used for

Two different things, and only the second reads the file:

- **A plain scan** (`./jobradar.py scan`) just labels each job with the CV mapped to its
  role. The files aren't opened — the mapping alone drives the `send: X` label.
- **A deep scan** (`./jobradar.py scan --deep`) reads the *text* of these files and each
  job's *description*, then picks the best-fitting CV per job and tells you why
  ("uvm, sva assertions, functional coverage"). That's when having the files here pays
  off, and it's the only mode that opens them.

The text is read into memory, matched, and discarded — it's never written anywhere,
published, or sent over the network. Deep matching runs locally only, because these files
deliberately don't exist on the cloud runner.

Scanned/image-only PDFs extract no text (there's no OCR); `--deep` will say so and fall
back to the role mapping for that CV.
