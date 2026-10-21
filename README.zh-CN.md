# thesis-formatting-skill

[English](README.md)

这是一个可复用的 Claude Code 与 GitHub Copilot 技能，用于审计、修复、渲染
DOCX 学位论文并执行隐私发布检查。工具绝不覆盖源文档，而是依据声明式格式配置，
生成可复现的 DOCX、PDF、审计、转换、预览与发布证据。

> [!IMPORTANT]
> **Apple University（苹果大学）完全虚构。本仓库出现的所有人物、论文、参考文献、
> 观测记录、计算结果、标识符及其他数据均为合成内容，不代表任何真实机构、人物、
> 出版物、学生记录或源项目。**

## 安装 / Installation

需要 Python 3.12+、[`uv`](https://docs.astral.sh/uv/)；本地渲染还需要
LibreOffice 与 Poppler。

```bash
git clone https://github.com/JieGaoSunny/thesis-formatting-skill.git
cd thesis-formatting-skill
uv sync --frozen --all-extras
```

### Claude Code

将 [`.claude/skills/thesis-formatting/`](.claude/skills/thesis-formatting/)
复制或链接到项目中的同一路径；如需用户级安装，则放入
`~/.claude/skills/thesis-formatting/`。权威说明位于
[`.claude/skills/thesis-formatting/SKILL.md`](.claude/skills/thesis-formatting/SKILL.md)。

### GitHub Copilot

将 [`.github/skills/thesis-formatting/`](.github/skills/thesis-formatting/)
复制到目标仓库。Copilot 会发现
[`.github/skills/thesis-formatting/SKILL.md`](.github/skills/thesis-formatting/SKILL.md)。
根目录 [`SKILL.md`](SKILL.md) 与两个面向代理的副本逐字节一致。

## 工作流程 / Workflow

按顺序运行以下命令。处理其他文档时，必须使用经过人工确认的对应配置；不能把本仓库
的虚构配置当成通用规范。

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

`audit` 诊断问题；`format` 生成新 DOCX 与内容比较证据；`export` 生成 PDF 和渲染
清单；`preview` 生成审阅图片；`release-check` 扫描发布集合。退出码 `0` 表示成功，
`1` 表示存在发现项或验证未完成，`2` 表示输入、配置或工具无效。
由于输入文档有意包含缺陷，首次审计会返回 `1`；审计报告仍会正常写入，并作为
生成发布目录中的证据。

仅在本地开发时设置 `THESIS_RENDER_MODE=local`，并向 `export` 传入
`--allow-noncanonical`。此类输出明确属于非规范渲染，不得用作出版或合规证据。

## 示例 / Examples

仓库分别提供可下载的演示产物：

- 修复前：[DOCX](examples/before.docx) · [PDF](examples/before.pdf) ·
  [审计报告](examples/reports/before-audit.md)
- 修复后：[DOCX](examples/after.docx) · [PDF](examples/after.pdf) ·
  [审计报告](examples/reports/after-audit.md) ·
  [转换报告](examples/reports/after-transformation.json)
- 内容保真证据：[内容比较](examples/reports/content-diff.md)

这些 PDF 与截图由本地模式生成，只用于演示，不是规范发布产物。

### 配对前后截图 / Matched screenshots

| 位置 | 修复前 | 修复后 |
|---|---|---|
| 封面 / cover | ![修复前封面](examples/screenshots/before/demo_cover-page-001.png) | ![修复后封面](examples/screenshots/after/demo_cover-page-001.png) |
| 目录 / toc | ![修复前目录](examples/screenshots/before/demo_toc-page-002.png) | ![修复后目录](examples/screenshots/after/demo_toc-page-002.png) |
| 正文 / body | ![修复前正文](examples/screenshots/before/demo_body-page-004.png) | ![修复后正文](examples/screenshots/after/demo_body-page-004.png) |
| 图 / figure | ![修复前图](examples/screenshots/before/demo_figure-page-007.png) | ![修复后图](examples/screenshots/after/demo_figure-page-007.png) |
| 表 / table | ![修复前表](examples/screenshots/before/demo_table-page-007.png) | ![修复后表](examples/screenshots/after/demo_table-page-007.png) |
| 参考文献 / references | ![修复前参考文献](examples/screenshots/before/demo_references-page-015.png) | ![修复后参考文献](examples/screenshots/after/demo_references-page-013.png) |
| 附录 / appendix | ![修复前附录](examples/screenshots/before/demo_appendix-page-016.png) | ![修复后附录](examples/screenshots/after/demo_appendix-page-014.png) |

## 已修复缺陷 / Repaired defects

虚构的“修复前”文档有意包含以下问题：

| 范围 | 演示缺陷 | 确定性修复 |
|---|---|---|
| 页面 | 纸张、页边距、分节起始方式错误 | 应用配置中的页面与分节规则 |
| 样式 | 样式定义、角色映射和直接格式错误 | 解析语义角色并应用声明样式 |
| 标题与目录 | 手工章节编号、缺少目录域 | 恢复自动编号与域结构 |
| 页眉页脚 | 来源、链接和页码域错误 | 按分节重建且保留已有内容 |
| 图 | 图片过宽，题注位于对象下方或与对象分离 | 限制宽度并移动唯一匹配题注 |
| 表 | 非三线表、表头不重复、跨页断行 | 应用边框、重复表头和禁止断行规则 |
| 参考文献 | 缩进与间距不一致 | 统一参考文献段落格式 |

匿名通用规则见 [`docs/format-rules.md`](docs/format-rules.md)。

## 架构 / Architecture

```text
格式配置 ──> 语义 OOXML 清单 ──> 审计发现
                  │
源 DOCX ──────────┴──> 确定性格式化器 ──> 新 DOCX
   │                                  │
   └────────── 内容快照比较 ───────────┘
新 DOCX ──> 固定渲染器 ──> PDF + 清单 ──> 配对预览
发布集合 ──> 失败关闭的隐私扫描器 ──> JSON/Markdown 发布报告
```

语义层记录段落、域、书签、表格、图片、分节、页眉、页脚、注释与公式；证据不足时
保持歧义。格式化器使用页面、样式、编号、域、对象、页眉页脚等独立修复模块。
所有公开报告均由 JSON Schema 校验。

## 测试与可复现性 / Tests and reproducibility

```bash
uv sync --frozen --all-extras
uv run --frozen pytest -m "not integration"
uv run --frozen pytest
```

安装 LibreOffice 与 Poppler 后，完整测试会包含外部渲染集成测试。CI 严格依据
[`uv.lock`](uv.lock) 安装依赖，检查文档链接，在容器外运行单元测试，并在规范镜像
中运行渲染测试和端到端演示测试。

规范渲染镜像（精确且不可变的摘要）：

```text
ghcr.io/jiegaosunny/thesis-formatting-skill-render@sha256:5866364e94961d3e8f33402985f4b2e900febb07a7503e83b8c957216c1c9d79
```

精确拉取：

```bash
docker pull ghcr.io/jiegaosunny/thesis-formatting-skill-render@sha256:5866364e94961d3e8f33402985f4b2e900febb07a7503e83b8c957216c1c9d79
docker run --rm \
  -e THESIS_RENDER_IMAGE_DIGEST=sha256:5866364e94961d3e8f33402985f4b2e900febb07a7503e83b8c957216c1c9d79 \
  ghcr.io/jiegaosunny/thesis-formatting-skill-render@sha256:5866364e94961d3e8f33402985f4b2e900febb07a7503e83b8c957216c1c9d79 \
  --version
```

规范模式会校验 root 所有的容器标记、源码与构建输入、镜像摘要、LibreOffice 版本、
字体、区域设置和 PDF 哈希。仅在其他主机设置 `THESIS_RENDER_IMAGE_DIGEST` 不能
把渲染结果变成规范产物。

## 限制与人工审阅 / Limitations and manual review

自动化不能替人判断歧义文本是否为标题，不能验证引用的学术正确性、评价视觉质量或
批准论文。必须在 Word 和 PDF 中审阅每条警告、跳过的修复、分页、域结果、公式、
图片、表格、参考文献与附录。平台字体替换可能改变分页。完整清单见
[`docs/limitations.md`](docs/limitations.md)。

## 隐私 / Privacy

发布检查会扫描 DOCX 的可见及隐藏文本、OOXML 属性、关系、文档属性、嵌入文件名，
以及 PDF 文本和元数据、路径、类似身份信息的值、未解析占位符和可选的字面量
denylist。报告和命令输出会对发现内容脱敏；无法读取或格式损坏的范围会失败关闭。

### 可复现演示发布检查

公开演示会扫描**整个** [`examples/`](examples/) 发布目录，包括 DOCX、PDF、报告、
截图、文件名和元数据。它只使用仓库内的合成测试文件，不需要任何私有数据：

```bash
uv run thesis-format release-check examples --profile rules/apple-university.yaml --denylist tests/fixtures/privacy/synthetic-denylist.txt --report build/examples-privacy.json --markdown build/examples-privacy.md
```

### 真实发布检查

在仓库外创建包含项目专用敏感字面量的 denylist，设置以下路径；不得提交该 denylist
或其中的值：

```bash
RELEASE_DIR=/absolute/path/to/release-directory
APPROVED_PROFILE=/absolute/path/to/approved-profile.yaml
PRIVATE_DENYLIST=/absolute/path/to/private-denylist.txt
uv run thesis-format release-check "$RELEASE_DIR" --profile "$APPROVED_PROFILE" --denylist "$PRIVATE_DENYLIST" --report build/private-release-privacy.json --markdown build/private-release-privacy.md
```
