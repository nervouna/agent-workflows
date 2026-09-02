# agent-workflows

可复用的 AI agent 工作流，以及 Codex 本地配置维护工具。

公开技能位于 `skills/`，可通过 [Vercel Skills CLI](https://github.com/vercel-labs/skills) 按需安装，本仓库无需额外索引或另行发布 npm 包。先阅读[技能目录与前置条件](skills/README.md)，再选择适合自己环境的工作流。

## 安装技能

需要 Node.js、npm（包含 `npx`）和 Git，并满足所用 `skills` 版本的 Node 要求。以下远端命令以仓库已发布为公开的 `nervouna/agent-workflows` 为前提：

```sh
# 查看可安装技能
npx skills add nervouna/agent-workflows --list

# 为当前用户的 Codex 安装一个技能
npx skills add nervouna/agent-workflows --skill app-icon-design -a codex -g

# 安装全部公开技能
npx skills add nervouna/agent-workflows --skill '*' -a codex -g
```

全局安装的 Codex 技能位于 `~/.agents/skills/`；去掉 `-g`，则安装到执行命令所在项目的 `.agents/skills/`。安装前检查同名技能，避免覆盖自己的修改。

技能提供操作指引，不会自动安装 Xcode、Python、mise、MCP 服务或其他工具，也不会为 agent 增加子代理、图片生成或 GUI 操作能力。安装本仓库的技能不需要安装 Python 维护工具及其开发依赖。

## Codex 维护工具

仓库还提供只读审计命令，检查 `~/.codex` 的基础安全边界，默认不读取或输出 secrets、sessions、history 等运行数据。它不替代 `~/.codex`，也不保存 Codex 的运行状态。

Python 包名、模块名和 CLI 保持为 `codex-maintenance`、`codex_maintenance` 和 `codex-maintenance`，不随仓库名称改变。维护工具需要 Python 3.12 或更新版本及 `uv`：

```sh
uv run python -m codex_maintenance audit
```

更多内容见[审计手册](docs/runbooks/codex-home-audit.md)和[技能安装与公开验证手册](docs/runbooks/skill-distribution.md)。仓库开发检查：

```sh
uv run pytest
uv run ruff format --check .
uv run ruff check .
```

## 许可证与公开边界

整个仓库采用 [MIT 许可证](LICENSE)，每个公开技能也附带相同的许可文本。

`.agents/skills/maintain-codex-agents` 是仓库自身的维护技能，使用 `metadata.internal: true` 从默认技能列表中过滤。这不是访问控制：源码随仓库公开，显式请求或开启内部技能发现仍可能安装它。
