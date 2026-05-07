# claude-logger

这是一个独立实现的 Claude Code 插件，用 Claude Code hooks 记录每轮任务的生命周期。

代码目录：

```text
claude-logger/
  .claude-plugin/
    plugin.json
    marketplace.json
  hooks/
    hooks.json
  bin/
    claude_logger.py
    install-local.sh
  docs/
    README.md
```

如果你想了解如何从零开发 Claude Code plugin、有哪些安装方式、如何调试和发布，请看：

[CLAUDE_PLUGIN_DEVELOPMENT.md](CLAUDE_PLUGIN_DEVELOPMENT.md)

## 记录内容

插件会把日志写到：

```text
~/.claude/logs/<session-id>/
  summary.md         # Markdown 汇总报告
  events.jsonl       # 结构化事件
  hook-inputs.jsonl  # Claude Code 传给 hook 的原始 JSON
  metadata.json      # session_id、transcript_path、cwd 等元信息
```

`summary.md` 包含：

- 用户提交的问题
- Claude Code 调用的工具、入参、失败信息
- transcript 中的工具请求和工具结果摘要
- transcript 中可见的 thinking 摘要
- assistant 可见输出和最终输出
- `Stop`、`StopFailure`、`SessionEnd` 的结束原因
- transcript stop_reason 统计
- token 用量汇总
- 按时间顺序排列的完整对话过程，时间格式为 `yyyy-mm-dd hh:mm:ss`
- 异常中止状态会在 `summary.md` 中用红色标记
- Claude Code 自动/手动上下文压缩事件；自动压缩会用橙色高亮，手动压缩会用蓝色高亮

## 重要限制

Claude Code hook 不会暴露隐藏 chain-of-thought。插件只能记录 transcript 中可见的 thinking/summary、assistant 输出、工具调用和工具结果。

如果 Claude Code 进程被系统强杀、终端崩溃、机器断电，结束 hook 可能没有机会运行。这种情况下可能没有 `summary.md`，但已经触发过的事件仍会保存在 `events.jsonl` 和 `hook-inputs.jsonl`。

## 本地验证

```bash
cd /Users/mark/Workspace/Python/agi/claude-logger
chmod +x bin/*.py bin/*.sh
python3 -m py_compile bin/claude_logger.py
claude plugin validate .
```

临时加载测试：

```bash
claude --plugin-dir /Users/mark/Workspace/Python/agi/claude-logger
```

进入 Claude Code 后执行：

```text
/hooks
```

确认能看到 `claude-logger` 提供的 hooks。

## 通过 Marketplace 安装

命令行安装：

```bash
cd /Users/mark/Workspace/Python/agi/claude-logger
./bin/install-local.sh
```

等价手动命令：

```bash
claude plugin marketplace add /Users/mark/Workspace/Python/agi/claude-logger
claude plugin install claude-logger@mark-local-plugins
```

也可以在 Claude Code 交互界面里执行：

```text
/plugin marketplace add /Users/mark/Workspace/Python/agi/claude-logger
/plugin install claude-logger@mark-local-plugins
```

安装后重启 Claude Code，再验证：

```bash
claude plugin list
claude plugin marketplace list
```

## 查看日志

查看最近 session：

```bash
ls -lt ~/.claude/logs | head
```

查找报告：

```bash
find ~/.claude/logs -maxdepth 2 -name summary.md -print | tail -20
```

打开某个报告：

```bash
open ~/.claude/logs/<session-id>/summary.md
```

## 排查中途停止

打开最近的 `summary.md` 后优先看：

1. `结束原因判断`
2. `工具调用` 的最后一条
3. `Transcript stop_reason 统计`
4. `最终输出`

常见判断：

- `normal_completion` / `Stop`：Claude Code 认为本轮正常结束
- `api_error` / `StopFailure`：API 或模型调用错误
- `session_ended` / `SessionEnd`：会话退出时补生成报告
- 最后一条工具后没有最终输出：重点看工具结果、API 错误、是否用户中断或进程退出

## 卸载

```bash
claude plugin uninstall claude-logger@mark-local-plugins
```

历史日志位于 `~/.claude/logs/`，卸载插件不会自动删除这些日志。
