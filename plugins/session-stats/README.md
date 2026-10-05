# Session Stats

在 Codex App 对话中查看本机会话的统计快照。采集、去重、计算和 HTML 渲染全部由本地程序完成；模型只负责调用程序并展示结果。

## 安装

需要支持插件的 Codex CLI、Codex App，以及可通过 `python3` 调用的 Python 3.12 或更高版本。当前版本已在 macOS 和 Codex CLI 0.159.0 上验证。

```sh
codex plugin marketplace add nervouna/codex-plugins
codex plugin add session-stats@codex-plugins
```

重启 Codex App，在新会话中输入：

```text
$session-stats:session-stats
```

默认统计当前会话。可以附上 `codex://threads/<会话 UUID>` 链接，或通过 @ 引用指定会话。只支持本机可读取的会话。

## 指标

默认展示主会话与子代理合计，也可以切换到主会话或子代理。

- 总消耗、输入、缓存输入、输出、推理 Token。
- 缓存命中：缓存输入占输入的比例；推理占比：推理 Token 占输出的比例。
- 对话轮数、平均 TTFT、端到端吞吐。
- 压缩次数及累计压缩耗时。

端到端吞吐包含工具执行和等待。TTFT 使用 Codex 保存的轮次测量值。子代理耗时按各轮累加。缺失值显示「—」。每次调用生成一个固定快照，不自动刷新。

## 数据与文件

程序只读本机 Codex 索引和会话记录，不发送网络请求，不调用模型 API。输出只包含标识符、时间戳、数值和诊断代码，不包含会话正文、工具参数或工具输出。

HTML 和 JSON 快照保存在调用会话的输出目录中，用于再次打开历史结果。不需要保留时，可以删除对应快照文件；删除后历史对话中的图表将无法显示。

## 更新

```sh
codex plugin marketplace upgrade codex-plugins
codex plugin add session-stats@codex-plugins
```

更新后重启 Codex App。插件依赖 Codex 本地记录格式；字段缺失时不会估算补齐。

## 许可证

MIT，参见 [LICENSE](LICENSE)。
