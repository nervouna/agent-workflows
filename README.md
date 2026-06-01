# codex-maintenance

维护 Codex 本地配置和工具链的工作区。

这个仓库不替代 `~/.codex`，也不保存 Codex 的运行状态。它只存放可测试、可复用、可审计的维护工具、模板和操作手册。

## V0

- 提供只读审计命令，检查 `~/.codex` 的基础安全边界。
- 默认不读取或输出 secrets、sessions、history 等运行数据。
- 使用 `uv`、`ruff` 和标准库测试流程维护代码质量。

## 目标边界

- `~/.codex`: 真实 Codex 配置目录。
- 本仓库: 审计工具、维护脚本、runbook、模板、测试。

## 常用命令

```sh
uv run python -m codex_maintenance audit
uv run pytest
uv run ruff format --check .
uv run ruff check .
```
