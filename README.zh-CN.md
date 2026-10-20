# thesis-formatting-skill

一个用于统一格式化 DOCX 学位论文的可复用技能，并通过虚构大学示例演示工作流程。

> **Apple University（苹果大学）以及演示中的所有人物、文档和数据均为虚构，与任何真实机构、人物或源项目无关。**

生成的演示产物将放在 `examples/` 目录下。

仓库提交的演示包含 `before.docx`、`after.docx`、对应的本地 PDF 渲染、
`examples/reports/` 下的审计与内容保真报告，以及
`examples/screenshots/` 下七个语义目标的成对截图。这些 PDF 和渲染清单使用
`THESIS_RENDER_MODE=local` 生成，仅用于演示工作流，不属于规范发布产物。

虚构研究包含完整的18条观测记录、等效尺度输入和计算函数，可复算估计值、变异系数、偏差及敏感性包络。生成图像时必须提供经验证的中文字体：可传入 `font_path`、设置 `THESIS_FIGURE_FONT`，或在标准系统路径安装 Noto Sans CJK。

## 渲染器身份

规范镜像由源码提交
`9e29b0eb77a4749e330fac4902be10597330ce92` 构建：

```bash
docker run --rm \
  -e THESIS_RENDER_IMAGE_DIGEST=sha256:5866364e94961d3e8f33402985f4b2e900febb07a7503e83b8c957216c1c9d79 \
  -v "$PWD/render-environment.json:/app/render-environment.json:ro" \
  ghcr.io/jiegaosunny/thesis-formatting-skill-render@sha256:5866364e94961d3e8f33402985f4b2e900febb07a7503e83b8c957216c1c9d79 ...
```

规范模式会校验固定且由 root 拥有的
`/usr/local/share/thesis-format/canonical-container.json` 标记，确认源码提交、
构建输入、精确固定的镜像摘要以及运行时 LibreOffice/字体观测全部一致。仅在本地
伪造 `THESIS_RENDER_IMAGE_DIGEST` 不能产生规范渲染。
`render-environment.json` 仍被排除在 Docker 构建上下文之外，避免镜像摘要成为
自身构建输入。

本地开发必须通过 `THESIS_RENDER_MODE=local` 或渲染环境中的
`"render_mode": "local"` 显式启用。本地清单会在
`renderer.image_digest` 中记录确定性渲染器指纹，并将
`environment.canonical` 标记为 `false`；规范验收会拒绝此类清单。

English version: [README.md](README.md).
