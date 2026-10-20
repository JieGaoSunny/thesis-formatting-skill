# thesis-formatting-skill

A reusable skill for formatting DOCX theses consistently and demonstrating the workflow with a fictional university example.

> **Apple University and every person, document, and data item used in demonstrations are entirely fictional. They do not represent any real institution, person, or source project.**

Generated demonstration artifacts will appear under `examples/`.

The fictional study ships all 18 observation rows, scale inputs, and calculation
helpers needed to reproduce its estimates, CVs, biases, and sensitivity envelope.
Figure generation requires a verified CJK font: pass `font_path`, set
`THESIS_FIGURE_FONT`, or install Noto Sans CJK at a standard system path.

## Renderer identity

Canonical publication is pending an image rebuild. The checked-in environment
uses `canonical_source_commit: "PENDING_REBUILD"`, so canonical mode
intentionally fails until the workflow-built image commit and digest are
repinned together. The previous invocation was:

```bash
docker run --rm \
  -e THESIS_RENDER_IMAGE_DIGEST=sha256:43d9adaf655699e6f5975ff355077319467b549aace7d2d0353003d1b66d3eba \
  -v "$PWD/render-environment.json:/app/render-environment.json:ro" \
  ghcr.io/jiegaosunny/thesis-formatting-skill-render@sha256:43d9adaf655699e6f5975ff355077319467b549aace7d2d0353003d1b66d3eba ...
```

Canonical mode verifies the fixed, root-owned
`/usr/local/share/thesis-format/canonical-container.json` marker against the
configured source commit and build inputs, the exact pinned image digest, and
runtime LibreOffice/font observations. Supplying only
`THESIS_RENDER_IMAGE_DIGEST` outside that image cannot make a local render
canonical. `render-environment.json` remains excluded from the Docker build
context so an image digest can never become an input to its own image build.

Local development must be explicitly enabled with
`THESIS_RENDER_MODE=local` or `"render_mode": "local"` in a supplied render
environment. Local manifests record a deterministic renderer fingerprint in
`renderer.image_digest` and set `environment.canonical` to `false`; canonical
acceptance rejects those manifests.

中文说明见 [README.zh-CN.md](README.zh-CN.md)。
