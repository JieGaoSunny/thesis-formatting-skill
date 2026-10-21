# Limitations and manual-review checklist

The formatter is evidence-driven automation, not an approval authority. A clean
report means that implemented checks passed for the selected profile and
environment; it does not prove that a thesis is academically or administratively
acceptable.

## Known limitations

- Ambiguous semantic roles are reported and left unchanged.
- Text patterns cannot reliably replace intentional Word styles and fields.
- Citation accuracy, bibliography completeness, argument quality, and factual
  correctness are outside scope.
- Complex drawing objects, third-party extensions, macros, embedded packages,
  and uncommon OOXML may require application-specific inspection.
- Word, LibreOffice, operating systems, and installed fonts can paginate the
  same DOCX differently.
- Field displays may remain stale until refreshed by a compatible editor.
- Automated screenshots cannot judge clipping, visual balance, legibility, or
  whether a page break is editorially appropriate.
- Privacy scanning detects configured literals and generic patterns, but no
  automated scanner can guarantee that all sensitive context has been found.
- A noncanonical render is useful for development only and cannot establish
  publication reproducibility.

## Required manual review

1. Confirm that the profile matches the currently approved handbook.
2. Review every audit warning, ambiguity, skipped repair, and exception.
3. Open the new DOCX without replacing the original; refresh fields and inspect
   navigation, numbering, cross-references, notes, and equations.
4. Compare cover, front matter, contents, representative body pages, figures,
   tables, references, and appendices in both DOCX and PDF.
5. Inspect page breaks, blank pages, headers, footers, page-number transitions,
   table splits, caption placement, and image resolution.
6. Review the content-difference report and explain every allowed structural
   movement.
7. Run the release check over the entire publication set, including reports,
   previews, filenames, and PDF metadata.
8. Have an authorized human perform the final policy and privacy approval.

## When to stop

Do not claim compliance or publish when the renderer is unavailable, a report
is missing or invalid, content equivalence fails, privacy scanning is incomplete,
an unresolved error/violation remains, or manual review has not occurred.
