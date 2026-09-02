# agent-workflows

可复用的 AI agent 工作流，以及 Codex 本地配置维护工具。

公开技能位于 `skills/`，可通过 [Vercel Skills CLI](https://github.com/vercel-labs/skills) 按需安装，本仓库无需额外索引或另行发布 npm 包。先阅读[技能目录与前置条件](skills/README.md)，再选择适合自己环境的工作流。

## 安装技能

以下示例为当前用户的 Codex 安装一个技能，以仓库已发布为公开的 `nervouna/agent-workflows` 为前提：

```sh
npx skills add nervouna/agent-workflows --skill app-icon-design -a codex -g
```

完整选项、环境前提、项目与全局安装路径、同名覆盖提醒，以及内部技能的发现边界，统一见[技能目录与安装说明](skills/README.md)。

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

## 许可证

整个仓库采用 [MIT 许可证](LICENSE)，每个公开技能也附带相同的许可文本。
