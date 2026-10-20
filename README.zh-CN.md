# thesis-formatting-skill

一个用于统一格式化 DOCX 学位论文的可复用技能，并通过虚构大学示例演示工作流程。

> **Apple University（苹果大学）以及演示中的所有人物、文档和数据均为虚构，与任何真实机构、人物或源项目无关。**

生成的演示产物将放在 `examples/` 目录下。

虚构研究包含完整的18条观测记录、等效尺度输入和计算函数，可复算估计值、变异系数、偏差及敏感性包络。生成图像时必须提供经验证的中文字体：可传入 `font_path`、设置 `THESIS_FIGURE_FONT`，或在标准系统路径安装 Noto Sans CJK。

## 渲染器身份

规范容器导出必须在运行时传入不可变镜像摘要：

```bash
docker run --rm \
  -e THESIS_RENDER_IMAGE_DIGEST=sha256:<64位小写十六进制> \
  -v "$PWD/render-environment.json:/app/render-environment.json:ro" \
  thesis-formatting-render ...
```

`render-environment.json` 只记录仓库、Debian 快照、区域设置和字体输入，并被明确排除在 Docker 构建上下文之外，避免镜像摘要成为自身构建输入。

本地开发必须通过 `THESIS_RENDER_MODE=local` 或渲染环境中的
`"render_mode": "local"` 显式启用。本地清单会在
`renderer.image_digest` 中记录确定性渲染器指纹，并将
`environment.canonical` 标记为 `false`；规范验收会拒绝此类清单。

English version: [README.md](README.md).
