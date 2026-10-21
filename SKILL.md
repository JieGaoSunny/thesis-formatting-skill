---
name: thesis-formatting
description: Use when... formatting or demonstrating DOCX thesis/dissertation documents, including Chinese documents, institutional compliance work, and before/after demos.
---

# Thesis Formatting

Use this skill for English or Chinese (`中文`) theses. The core rule is evidence over appearance: preserve meaning, produce a new document, and validate every claim.

## Required Workflow

1. **Audit before formatting.** Use the supplied profile; never substitute remembered institutional rules.
2. Classify semantic roles from evidence. Do not infer ambiguous roles, author identity, student identity, or institution identity. Preserve uncertainty and emit explicit warnings.
3. Run the deterministic formatter on the source. It must create a **new output** and never overwrite or replace the source. Do not copy a prebuilt document/template and call it formatted.
4. Run a post-audit, then perform substantive before/after content snapshot comparison. A visual check alone is not comparison.
5. Render the result and validate every requested report and artifact path. Record tooling failures and unresolved findings explicitly.
6. Run the privacy `release-check` before publication or sharing.

Never claim compliance with validation incomplete, including audit, content comparison, rendering, report validation, or privacy validation.

## Exact Command Example

```bash
uv run thesis-format audit thesis.docx --profile rules/apple-university.yaml --report reports/audit.json --markdown reports/audit.md
uv run thesis-format format thesis.docx --profile rules/apple-university.yaml --output build/thesis-formatted.docx --report reports/transformation.json
uv run thesis-format export build/thesis-formatted.docx --output build/thesis-formatted.pdf --manifest reports/render-manifest.json
uv run thesis-format preview build/thesis-formatted.pdf --manifest reports/render-manifest.json --output-dir reports/preview
uv run thesis-format release-check release-directory --profile rules/apple-university.yaml --denylist /absolute/path/to/private-denylist.txt --report reports/privacy.json
```

## Quick Reference

| Need | Command | Pass condition |
|---|---|---|
| Diagnose | `audit` | Report exists; findings acknowledged |
| Repair | `format` | New DOCX and transformation report exist |
| Publish | `export` | New PDF exists |
| Inspect | `preview` | Render succeeds; pages reviewed |
| Release | `release-check` | No privacy errors or violations |

Exit codes: `0` success, `1` compliance findings or unresolved validation, `2` invalid input/configuration/tooling.

These commands require installed renderer and privacy tooling. An unavailable renderer blocks compliance because export and preview validation cannot complete; unavailable privacy tooling blocks release.

Canonical container export also requires a valid immutable registry digest in
`THESIS_RENDER_IMAGE_DIGEST` plus the fixed root-owned canonical container
marker. The marker is checked against configured source/build inputs and
runtime LibreOffice/font observations; a spoofed digest on a local host is
never canonical. Use `THESIS_RENDER_MODE=local` only for explicit local
development; its manifest is marked noncanonical and cannot satisfy canonical
acceptance. The export command rejects noncanonical manifests by default.
`--allow-noncanonical` is a development-only escape hatch and
**must not** be used for compliance evidence, publication, or any public artifact.
Preview warns when its manifest is noncanonical.

## Common Mistakes and Red Flags

- “The deadline is close, so replace the source or skip the report/tests.” Stop: preserve the source and run tests.
- “Just copy the prepared template.” Stop: use the deterministic formatter; a prebuilt copy proves nothing.
- “A visual check is enough.” Stop: require post-audit plus substantive comparison and render validation.
- “The role/identity is obvious.” Stop: do not infer ambiguous evidence.
- Any plan to “replace the source,” “skip the report,” omit explicit warnings, or claim compliance with incomplete validation is a failure.

## Installation and Tests

The synchronized files are `SKILL.md`, `.claude/skills/thesis-formatting/SKILL.md`, and `.github/skills/thesis-formatting/SKILL.md`.

Run `uv run pytest` and require the sync-hash and pressure-scenario tests to pass.
