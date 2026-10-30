# agent-workflows

[English](README.md) | 简体中文

可复用的 AI agent 工作流，以及 Codex 本地配置维护工具。

## 状态

这是个人项目：作者在 Codex 中使用的工作流，公开出来供他人按需安装。部分技能以作者的环境为前提（macOS、mise、uv、Xcode），各技能的前提条件见[技能目录](skills/README.md)。安装技能需要 Node.js、npm（包含 `npx`）、Git 和支持技能的 agent；审计工具需要 Python 3.12 或更新版本及 `uv`。安装本仓库的任何内容都不需要 API key 或账号。文档有中文和英文两个版本，技能本身用英文编写。

发布版本只含源码。技能直接从仓库 `main` 分支安装，审计工具从本地克隆运行。

## 构建方式

仓库的 `AGENTS.md` 是编码 agent 在这里遵循的规则：把 `~/.codex` 当作外部目标，默认只读检查；不输出 secrets、会话内容或认证文件；破坏性操作必须有显式参数和确认路径；使用 `uv`，代码放在 `src/codex_maintenance/`，测试放在 `tests/`；宣布完成前运行格式化、lint 和测试。报告问题或提交修复见 [CONTRIBUTING.md](CONTRIBUTING.md)，安全问题见 [SECURITY.md](SECURITY.md)。

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
