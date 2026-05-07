# claude-logger

`claude-logger` 是一个 Claude Code 插件，用 hooks 记录每轮任务的执行过程，并在任务正常结束、API 错误结束或会话退出时生成 Markdown 报告。

日志默认写到：

```text
~/.claude/logs/<session-id>/summary.md
```

## 记录内容

- 用户提交的问题
- Claude Code 调用过的工具、工具入参、耗时和失败信息
- transcript 中可见的工具请求和工具结果摘要
- transcript 中可见的 thinking/summary 文本
- assistant 可见输出和最终输出
- `Stop`、`StopFailure`、`SessionEnd` 对应的结束原因
- transcript 里的 `stop_reason` 统计
- token 用量汇总
- 按时间顺序排列的完整对话过程，时间格式为 `yyyy-mm-dd hh:mm:ss`
- 异常中止状态会在 `summary.md` 中用红色标记
- Claude Code 自动/手动上下文压缩事件；自动压缩会用橙色高亮，手动压缩会用蓝色高亮

## 关于 marketplace.json

Claude Code 插件 marketplace 的标准文件位置是：

```text
.claude-plugin/marketplace.json
```

本仓库只保留这一份标准 marketplace 文件。通过 `claude plugin marketplace add markyang2020/claude-logger` 添加 marketplace 时，Claude Code 读取的就是 `.claude-plugin/marketplace.json`。

## 安装

```bash
claude plugin marketplace add markyang2020/claude-logger
claude plugin install claude-logger@mark-local-plugins
```

安装后重启 Claude Code，然后执行：

```text
/hooks
```

确认 `claude-logger` 的 hooks 已加载。

## 本地开发验证

```bash
git clone https://github.com/markyang2020/claude-logger.git
cd claude-logger
python3 -m py_compile bin/claude_logger.py
claude plugin validate .
claude --plugin-dir .
```

完整的 Claude Code plugin 开发、安装、调试和发布流程见：

[docs/CLAUDE_PLUGIN_DEVELOPMENT.md](docs/CLAUDE_PLUGIN_DEVELOPMENT.md)

## 日志文件

每个 session 会生成一个目录：

```text
~/.claude/logs/<session-id>/
  summary.md         # Markdown 汇总报告
  events.jsonl       # 结构化事件
  hook-inputs.jsonl  # Claude Code 传给 hook 的原始 JSON
  metadata.json      # session_id、transcript_path、cwd 等元信息
```

查看最近报告：

```bash
ls -lt ~/.claude/logs | head
find ~/.claude/logs -maxdepth 2 -name summary.md -print | tail -20
```

## 重要限制

Claude Code hooks 不会暴露隐藏 chain-of-thought。因此本插件只能记录 transcript 中可见的 thinking/summary、assistant 输出、工具调用和工具结果。

如果 Claude Code 进程被系统强杀、终端崩溃或机器断电，结束 hook 可能没有机会运行。这种情况下可能没有 `summary.md`，但已经触发过的事件仍会保存在 `events.jsonl` 和 `hook-inputs.jsonl`。

## 卸载

```bash
claude plugin uninstall claude-logger@mark-local-plugins
```

历史日志位于 `~/.claude/logs/`，卸载插件不会自动删除这些日志。
