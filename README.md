# thesis-formatting-skill

[中文](README.zh-CN.md)

A reusable Claude Code and GitHub Copilot skill for auditing, repairing,
rendering, and privacy-checking DOCX theses without overwriting the source
document. It turns a declarative formatting profile into reproducible DOCX,
PDF, audit, transformation, preview, and release evidence.

> [!IMPORTANT]
> **Apple University is entirely fictional. Every named person, thesis, reference,
> observation, calculation, identifier, and other data item in this repository
> is synthetic. Nothing represents a real institution, person, publication,
> student record, or source project.**

## Installation

Requires Python 3.12+, [`uv`](https://docs.astral.sh/uv/), and, for local
rendering, LibreOffice plus Poppler.

```bash
git clone https://github.com/JieGaoSunny/thesis-formatting-skill.git
cd thesis-formatting-skill
uv sync --frozen --all-extras
```

### Claude Code

Copy or symlink [`.claude/skills/thesis-formatting/`](.claude/skills/thesis-formatting/)
into the same path in a project, or into
`~/.claude/skills/thesis-formatting/` for user-wide use. The authoritative
instructions are in
[`.claude/skills/thesis-formatting/SKILL.md`](.claude/skills/thesis-formatting/SKILL.md).

### GitHub Copilot

Copy [`.github/skills/thesis-formatting/`](.github/skills/thesis-formatting/)
into the target repository. Copilot discovers
[`.github/skills/thesis-formatting/SKILL.md`](.github/skills/thesis-formatting/SKILL.md).
The root [`SKILL.md`](SKILL.md) is byte-identical to both agent-specific copies.

## Workflow

Run the following commands in order. Replace the example profile with a
reviewed profile for the document being processed; never treat the fictional
profile as universal policy.

```bash
rm -rf build/release
mkdir -p build/release
export THESIS_RENDER_MODE=local
uv run thesis-format audit examples/before.docx --profile rules/apple-university.yaml --report build/release/before-audit.json --markdown build/release/before-audit.md
uv run thesis-format format examples/before.docx --profile rules/apple-university.yaml --output build/release/after.docx --report build/release/transformation.json
uv run thesis-format export build/release/after.docx --output build/release/after.pdf --manifest build/release/render-manifest.json --allow-noncanonical
uv run thesis-format preview build/release/after.pdf --manifest build/release/render-manifest.json --output-dir build/release/previews
uv run thesis-format release-check build/release --profile rules/apple-university.yaml --denylist tests/fixtures/privacy/synthetic-denylist.txt --report build/privacy.json --markdown build/privacy.md
```

`audit` diagnoses; `format` writes a new DOCX and content-comparison evidence;
`export` creates a PDF and render manifest; `preview` creates review images;
`release-check` scans the release set. Exit codes are `0` for success, `1` for
findings or incomplete validation, and `2` for invalid input or tooling.
The deliberately defective input makes the first audit return `1`; its reports
are still written and are part of the generated release evidence.

For local development only, set `THESIS_RENDER_MODE=local` and pass
`--allow-noncanonical` to `export`. Such output is explicitly noncanonical and
must not be used as publication or compliance evidence.

## Examples

The committed demonstration provides separate downloadable artifacts:

- Before: [DOCX](examples/before.docx) · [PDF](examples/before.pdf) ·
  [audit](examples/reports/before-audit.md)
- After: [DOCX](examples/after.docx) · [PDF](examples/after.pdf) ·
  [audit](examples/reports/after-audit.md) ·
  [transformation report](examples/reports/after-transformation.json)
- Preservation evidence:
  [content comparison](examples/reports/content-diff.md)

The PDFs and screenshots are local-mode demonstrations, not canonical release
artifacts.

### Matched before/after screenshots

| Destination | Before | After |
|---|---|---|
| Cover | ![Before cover](examples/screenshots/before/demo_cover-page-001.png) | ![After cover](examples/screenshots/after/demo_cover-page-001.png) |
| Table of contents | ![Before table of contents](examples/screenshots/before/demo_toc-page-002.png) | ![After table of contents](examples/screenshots/after/demo_toc-page-002.png) |
| Body | ![Before body](examples/screenshots/before/demo_body-page-004.png) | ![After body](examples/screenshots/after/demo_body-page-004.png) |
| Figure | ![Before figure](examples/screenshots/before/demo_figure-page-007.png) | ![After figure](examples/screenshots/after/demo_figure-page-007.png) |
| Table | ![Before table](examples/screenshots/before/demo_table-page-007.png) | ![After table](examples/screenshots/after/demo_table-page-007.png) |
| References | ![Before references](examples/screenshots/before/demo_references-page-015.png) | ![After references](examples/screenshots/after/demo_references-page-013.png) |
| Appendix | ![Before appendix](examples/screenshots/before/demo_appendix-page-016.png) | ![After appendix](examples/screenshots/after/demo_appendix-page-014.png) |

## Repaired defects

The synthetic “before” document deliberately exercises these repairs:

| Area | Demonstrated defect | Deterministic repair |
|---|---|---|
| Page layout | Wrong paper, margins, and section start | Apply profile geometry and section policy |
| Styles | Incorrect definitions, mappings, and direct formatting | Resolve semantic roles and apply declared styles |
| Headings/TOC | Manual chapter numbering and missing TOC field | Restore automatic numbering and field structure |
| Headers/footers | Wrong source, links, and page-number fields | Rebuild section-aware stories without dropping content |
| Figures | Oversized figure and caption below/away from object | Constrain width and bind/move the unique caption |
| Tables | Non-three-line borders, no repeated header, split rows | Apply border, repeat, and row-splitting rules |
| References | Inconsistent indentation and spacing | Normalize reference paragraph formatting |

See the anonymous rule guide in [`docs/format-rules.md`](docs/format-rules.md).

## Architecture

```text
format profile ──> semantic OOXML inventory ──> audit findings
                         │
source DOCX ─────────────┴──> deterministic formatter ──> new DOCX
       │                                      │
       └──────── content snapshot comparison ─┘
new DOCX ──> pinned renderer ──> PDF + manifest ──> matched previews
release set ──> fail-closed privacy scanner ──> JSON/Markdown release report
```

The semantic layer records paragraphs, fields, bookmarks, tables, figures,
sections, headers, footers, notes, and equations. Ambiguous evidence remains
ambiguous. The formatter uses focused repair modules for geometry, styles,
numbering, fields, objects, and headers/footers. JSON schemas validate every
public report contract.

## Tests and reproducibility

```bash
uv sync --frozen --all-extras
uv run --frozen pytest -m "not integration"
uv run --frozen pytest
```

The full suite includes external-renderer integration tests when LibreOffice
and Poppler are available. CI installs exactly from [`uv.lock`](uv.lock), checks
documentation links, runs unit tests outside the container, then runs render
and end-to-end demo tests inside the canonical image.

The canonical launcher reads the exact immutable pin from
[`render-environment.json`](render-environment.json). A source change sets
`canonical_container_status` to `pending-rebuild` and removes
`canonical_image_reference` and `canonical_image_digest`; canonical rendering
remains blocked until the rebuilt image is published and repinned.

```bash
CANONICAL_IMAGE="$(python -c 'import json; print(json.load(open("render-environment.json"))["canonical_image_reference"])')"
CANONICAL_DIGEST="$(python -c 'import json; print(json.load(open("render-environment.json"))["canonical_image_digest"])')"
docker pull "$CANONICAL_IMAGE"
docker run --rm \
  -e "THESIS_RENDER_IMAGE_DIGEST=$CANONICAL_DIGEST" \
  -v "$PWD:/workspace" \
  "$CANONICAL_IMAGE" \
  --version
```

Canonical mode verifies the root-owned container marker, source/build inputs,
image digest, LibreOffice version, fonts, locale, and PDF hash. Merely setting
`THESIS_RENDER_IMAGE_DIGEST` on another host cannot make a render canonical.
When `/app/render-environment.json` is absent, the image synthesizes its runtime
environment from the root-owned marker. A local checkout without either its
external configuration or the trusted marker fails closed.

## Limitations and manual review

Automation does not decide whether ambiguous text is a heading, verify the
scholarly correctness of citations, judge visual quality, or approve a thesis.
Review every warning, skipped repair, page break, field result, formula, figure,
table, reference, and appendix in Word and in the rendered PDF. Platform font
substitution can change pagination. See
[`docs/limitations.md`](docs/limitations.md) for the complete checklist.

## Privacy

The release check scans visible and hidden DOCX text, OOXML attributes,
relationships, properties, embedded filenames, PDF text/metadata, paths,
identity-shaped values, unresolved placeholders, and optional literal denylist
entries. Findings are redacted in reports and command output. Unreadable or
malformed in-scope content fails closed.
Every symbolic link found anywhere in a release tree is rejected as
`PRIVACY.UNSUPPORTED`, including safe relative links; targets are never followed.

### Reproducible demonstration release check

The public demo scans the **entire** [`examples/`](examples/) release directory,
including DOCX, PDF, reports, screenshots, filenames, and metadata. It uses only
the committed synthetic fixture and requires no private data:

```bash
uv run thesis-format release-check examples --profile rules/apple-university.yaml --denylist tests/fixtures/privacy/synthetic-denylist.txt --report build/examples-privacy.json --markdown build/examples-privacy.md
```

### Real publishing release check

Create a denylist outside the repository containing project-specific private
literals, set the paths below, and never commit the denylist or its values:

```bash
RELEASE_DIR=/absolute/path/to/release-directory
APPROVED_PROFILE=/absolute/path/to/approved-profile.yaml
PRIVATE_DENYLIST=/absolute/path/to/private-denylist.txt
uv run thesis-format release-check "$RELEASE_DIR" --profile "$APPROVED_PROFILE" --denylist "$PRIVATE_DENYLIST" --report build/private-release-privacy.json --markdown build/private-release-privacy.md
```
