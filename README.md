# thesis-formatting-skill

A reusable skill for formatting DOCX theses consistently and demonstrating the workflow with a fictional university example.

> **Apple University and every person, document, and data item used in demonstrations are entirely fictional. They do not represent any real institution, person, or source project.**

Generated demonstration artifacts will appear under `examples/`.

The fictional study ships all 18 observation rows, scale inputs, and calculation
helpers needed to reproduce its estimates, CVs, biases, and sensitivity envelope.
Figure generation requires a verified CJK font: pass `font_path`, set
`THESIS_FIGURE_FONT`, or install Noto Sans CJK at a standard system path.

## Renderer identity

Canonical container exports require the immutable registry digest at runtime:

```bash
docker run --rm \
  -e THESIS_RENDER_IMAGE_DIGEST=sha256:<64-lowercase-hex> \
  -v "$PWD/render-environment.json:/app/render-environment.json:ro" \
  thesis-formatting-render ...
```

`render-environment.json` records repository, Debian snapshot, locale, and font
inputs. It is deliberately excluded from the Docker build context so an image
digest can never become an input to its own image build.

Local development must be explicitly enabled with
`THESIS_RENDER_MODE=local` or `"render_mode": "local"` in a supplied render
environment. Local manifests record a deterministic renderer fingerprint in
`renderer.image_digest` and set `environment.canonical` to `false`; canonical
acceptance rejects those manifests.

中文说明见 [README.zh-CN.md](README.zh-CN.md)。
