# 技能目录

以下八个技能是本仓库的公开安装面。它们是工作流指引，不是运行时或工具的安装包；安装前应阅读对应 `SKILL.md`，确认权限和环境适用。

| 技能 | 用途 | 使用前提 |
| --- | --- | --- |
| [app-icon-design](app-icon-design/SKILL.md) | 探索、制作和集成应用图标 | 图片生成能力或现有素材；Apple 图标流程需要 macOS、Xcode / Icon Composer，自动操作还需要 GUI 能力，否则手动操作 |
| [apple-signing-workflow](apple-signing-workflow/SKILL.md) | 检查 Apple 构建、签名、描述文件及成品身份 | macOS、对应 Xcode 工具；实际签名需要用户自己的账号、证书和适用描述文件，团队从项目和用户要求确定 |
| [keep-calm-and-yolo-on](keep-calm-and-yolo-on/SKILL.md) | 从需求确认推进到实现、独立审查和分批本地提交 | 可用的实现与独立审查子代理、Git 和项目测试工具；安装技能不会新增子代理能力 |
| [mcp-secrets-and-local-config](mcp-secrets-and-local-config/SKILL.md) | 安全配置 MCP、环境文件与本地凭据 | 目标服务及其凭据；使用 1Password 流程时另需 `op`，本技能不提供任何密钥 |
| [node-npm-workflow](node-npm-workflow/SKILL.md) | 统一 Node/npm 工具链与验证方式 | 面向 macOS、mise 管理 Node、npm 的环境；尊重项目已有包管理器配置 |
| [project-memory](project-memory/SKILL.md) | 维护可随仓库流转的长期项目约束与决策 | 可读写项目文件的 agent；新建或维护记忆须有用户或项目规则授权 |
| [python-workflow](python-workflow/SKILL.md) | 统一 Python 解释器、依赖和测试流程 | 面向 macOS、mise 与 uv 的环境；具体 Python 版本及检查由项目决定 |
| [review-and-merge-branch](review-and-merge-branch/SKILL.md) | 独立审查已提交分支，并通过门禁后本地合并 | Git、独立审查子代理、项目检查工具和明确的本地合并授权；不隐含远端操作授权 |

## 安装

需要 Node.js、npm（包含 `npx`）、Git，以及支持技能的 agent。通过 `npm view skills engines` 查看 CLI 的 Node 版本要求。本文以 Codex 为安装目标，不承诺其他 agent 具备相同工具能力。

以下命令以远端已经作为公开的 `nervouna/agent-workflows` 发布为前提：

```sh
# 列出技能，或交互选择安装到当前项目
npx skills add nervouna/agent-workflows --list
npx skills add nervouna/agent-workflows -a codex

# 安装单个技能到当前项目
npx skills add nervouna/agent-workflows --skill app-icon-design -a codex

# 安装全部公开技能到当前项目
npx skills add nervouna/agent-workflows --skill '*' -a codex

# 加 -g 可为当前用户全局安装
npx skills add nervouna/agent-workflows --skill '*' -a codex -g
```

项目安装位于 `.agents/skills/`，全局安装位于 `~/.agents/skills/`。使用引号保护 `'*'`，避免 shell 将它展开为本地文件名。安装前检查同名技能和自己的修改；确认安装结果后，在新的 agent 任务中验证所需技能可以使用。

已有本地克隆时，也可把命令中的 `nervouna/agent-workflows` 换成克隆目录的绝对路径。更换电脑只需安装所选技能和其运行前提，不需要复制作者的 Codex 配置、凭据或运行状态，也不需要本仓库的 Python 开发依赖。

## 内部技能与许可

仓库维护技能位于 `.agents/skills/`，不是上表公开目录的一部分。`metadata.internal: true` 只用于默认发现过滤，不保密，也不阻止显式安装或通过 `INSTALL_INTERNAL_SKILLS=1` 发现它。批量公开安装使用 `--skill '*'`，不要改为可能包含额外目标的 `--all`。

整个仓库采用 [MIT 许可证](../LICENSE)，每个公开技能目录内均包含同样的 `LICENSE`，按项安装也会携带许可文本。

维护者可使用[原生安装与公开验证手册](../docs/runbooks/skill-distribution.md)复现隔离安装检查。CLI 的完整选项见 [Vercel Skills](https://github.com/vercel-labs/skills)。
