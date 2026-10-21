# Generic thesis format rules

This guide is intentionally anonymous. It describes how to translate an
approved thesis handbook into a machine-readable profile; it is not an
institutional specification. Record every value from the handbook and have a
human reviewer approve the profile before formatting a document.

## Rule hierarchy

1. Preserve the author's substantive content.
2. Never overwrite the input DOCX.
3. Prefer explicit Word styles, fields, numbering, and section properties over
   visual inference.
4. Treat conflicting or insufficient semantic evidence as ambiguous.
5. Make only repairs declared by the selected profile.
6. Require post-format audit, content comparison, rendering, and privacy checks.

## Profile checklist

| Area | Values to declare |
|---|---|
| Page | Paper width/height, orientation, margins, gutter, section starts |
| Typography | Latin/CJK fonts, font size, weight, color, language |
| Paragraphs | Alignment, line spacing, before/after spacing, indentation |
| Front matter | Required parts, order, headings, header visibility |
| Headings | Semantic levels, aliases, numbering pattern, page-break policy |
| TOC | Required field, included levels, formatting |
| Body | Default style, first-line indent, pagination, header source |
| Figures | Maximum width, alignment, caption position and numbering |
| Tables | Width/alignment, three-line borders, repeated header, row splitting |
| Equations | Alignment, numbering, cross-reference expectations |
| References | Heading role, hanging indent, spacing, entry detection |
| Appendices | Heading hierarchy, numbering restart/prefix, page policy |
| Headers/footers | Per-region text, linking, page-number format and restart |

## Semantic evidence

Use anchored style mappings, outline levels, numbering definitions, fields,
bookmarks, and constrained text patterns. Document-position heuristics should
only be used where the profile explicitly permits them. A match must not invent
an identity or silently resolve conflicting signals.

## Safe repair behavior

- Create a new output path and a transformation report.
- Preserve unsupported OOXML parts and relationships.
- Bind moved captions to a unique figure or table occurrence.
- Reuse compatible numbering and field structures; do not rewrite ordinary
  lists as headings.
- Keep headers and footers isolated by section and story type.
- Compare normalized semantic snapshots before and after formatting.
- Report skipped and unresolved repairs instead of guessing.

## Acceptance evidence

A formatting run is complete only when the output DOCX opens, schemas validate,
the post-audit has no unaccepted errors or violations, content comparison is
equivalent, the PDF/render manifest validates, requested previews are reviewed,
and the privacy release check passes.
