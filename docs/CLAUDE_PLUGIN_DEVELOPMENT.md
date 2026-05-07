# Claude Code Plugin 开发、安装与发布完整流程

这份文档说明如何从零开发一个 Claude Code plugin，如何组织 marketplace，如何安装、调试、更新和发布插件。本文也以本仓库 `claude-logger` 为例说明完整流程。

## 1. Claude Code Plugin 是什么

Claude Code plugin 是一组可分发的能力包，可以包含：

- hooks：监听 Claude Code 生命周期事件，例如用户提交 prompt、工具调用完成、任务停止、API 错误、会话结束。
- skills / commands：给 Claude Code 增加可调用的技能或 slash command。
- agents：增加专用 subagent。
- MCP servers：随插件分发 MCP 服务配置。
- output styles、themes、monitors 等扩展项。
- bin 可执行文件：插件启用后，`bin/` 下的可执行文件会加入 Bash tool 的 `PATH`。

一个插件最小只需要：

```text
my-plugin/
  .claude-plugin/
    plugin.json
```

如果要通过 marketplace 分发，还需要 marketplace 文件：

```text
my-plugin/
  .claude-plugin/
    marketplace.json
```

## 2. 标准目录结构

推荐结构：

```text
my-plugin/
  .claude-plugin/
    plugin.json          # 插件 manifest
    marketplace.json     # marketplace catalog，作为 marketplace 仓库时使用
  hooks/
    hooks.json           # hook 配置，Claude Code 会自动发现
  bin/
    my_hook.py           # hook 脚本或其他可执行文件
  skills/
    my-skill/
      SKILL.md
  agents/
    reviewer.md
  commands/
    status.md
  docs/
    README.md
  README.md
  LICENSE
```

注意：

- `.claude-plugin/` 里主要放元数据：`plugin.json` 和作为 marketplace 仓库时的 `marketplace.json`。
- `hooks/`、`skills/`、`agents/`、`commands/`、`bin/` 应该放在插件根目录，不要放到 `.claude-plugin/` 里面。
- 默认 hook 文件路径是 `hooks/hooks.json`。如果就使用默认路径，通常不需要在 `plugin.json` 里再声明 `hooks` 字段，否则有些版本会提示重复加载。

## 3. plugin.json

`plugin.json` 是插件 manifest，标准位置：

```text
.claude-plugin/plugin.json
```

示例：

```json
{
  "name": "claude-logger",
  "version": "0.1.0",
  "description": "Record Claude Code task lifecycle logs.",
  "author": {
    "name": "mark"
  },
  "license": "MIT",
  "keywords": ["hooks", "logging", "debugging"]
}
```

常用字段：

- `name`：插件名，kebab-case，例如 `claude-logger`。
- `version`：插件版本。设置了显式版本后，发布更新时要 bump 版本，否则用户可能不会收到更新。
- `description`：插件说明。
- `author`：作者信息。
- `license`：许可证。
- `keywords`：搜索标签。

## 4. hooks/hooks.json

hook 配置文件默认位置：

```text
hooks/hooks.json
```

基本结构：

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/bin/my_hook.py\" UserPromptSubmit",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

关键点：

- `type: "command"` 表示运行本地命令。
- `${CLAUDE_PLUGIN_ROOT}` 是 Claude Code 提供的插件安装目录变量，hook 脚本应使用它引用插件内文件。
- hook input 会通过 stdin 传入 JSON。
- `timeout` 单位是秒。
- 对工具事件如 `PostToolUse` 可以使用 `matcher` 匹配工具名；空字符串表示全部匹配。

常用生命周期事件：

```text
SessionStart          会话开始
UserPromptSubmit      用户提交 prompt
PostToolUse           工具调用成功后
PostToolUseFailure    工具调用失败后
Stop                  Claude 正常结束本轮响应
StopFailure           本轮因为 API/模型错误结束
SessionEnd            会话结束、清理或退出
```

常见 hook 输入字段：

```json
{
  "session_id": "abc123",
  "transcript_path": "/Users/.../.claude/projects/.../abc123.jsonl",
  "cwd": "/Users/me/project",
  "permission_mode": "default",
  "hook_event_name": "PostToolUse",
  "tool_name": "Bash",
  "tool_input": {
    "command": "pytest"
  },
  "tool_response": {
    "stdout": "1 passed",
    "stderr": ""
  }
}
```

不同事件会有不同的额外字段。例如：

- `UserPromptSubmit` 有 `prompt`。
- `PostToolUse` 有 `tool_name`、`tool_input`、`tool_response`、`duration_ms`。
- `PostToolUseFailure` 有 `tool_name`、`tool_input`、`error`。
- `Stop` 有 `last_assistant_message`、`stop_hook_active`。
- `StopFailure` 有 `error`、`error_details`、`last_assistant_message`。
- `SessionEnd` 有 `reason`。

## 5. marketplace.json

Claude Code marketplace 标准文件位置：

```text
.claude-plugin/marketplace.json
```

本仓库只保留这一份标准 marketplace 文件。实际 `claude plugin marketplace add markyang2020/claude-logger` 读取的是 `.claude-plugin/marketplace.json`。

示例：

```json
{
  "name": "mark-local-plugins",
  "owner": {
    "name": "mark"
  },
  "metadata": {
    "description": "Local Claude Code plugins maintained by mark.",
    "version": "0.1.0"
  },
  "plugins": [
    {
      "name": "claude-logger",
      "source": "./",
      "description": "Record Claude Code task lifecycle logs.",
      "version": "0.1.0",
      "author": {
        "name": "mark"
      },
      "license": "MIT",
      "category": "observability",
      "tags": ["hooks", "logging", "debugging"]
    }
  ]
}
```

字段说明：

- `name`：marketplace 名，安装时会用到，例如 `claude-logger@mark-local-plugins`。
- `owner`：维护者信息。
- `plugins`：插件列表。
- `plugins[].name`：插件名。
- `plugins[].source`：插件来源。

常见 `source` 写法：

```json
"source": "./"
```

表示插件就在 marketplace 仓库根目录。

如果 marketplace 仓库里有多个插件：

```json
"source": "./plugins/formatter"
```

如果插件来自另一个 GitHub 仓库：

```json
{
  "source": "github",
  "repo": "owner/plugin-repo"
}
```

如果插件在 monorepo 子目录：

```json
{
  "source": "git-subdir",
  "url": "owner/repo",
  "path": "tools/my-plugin"
}
```

## 6. 从零开发一个插件

### 6.1 创建目录

```bash
mkdir -p my-plugin/.claude-plugin my-plugin/hooks my-plugin/bin docs
cd my-plugin
```

### 6.2 写 plugin.json

```bash
cat > .claude-plugin/plugin.json <<'JSON'
{
  "name": "my-plugin",
  "version": "0.1.0",
  "description": "My Claude Code plugin.",
  "author": {
    "name": "me"
  },
  "license": "MIT"
}
JSON
```

### 6.3 写 hook 配置

```bash
cat > hooks/hooks.json <<'JSON'
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/bin/my_hook.py\" UserPromptSubmit",
            "timeout": 5
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/bin/my_hook.py\" Stop",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
JSON
```

### 6.4 写 hook 脚本

```python
#!/usr/bin/env python3
import json
import sys
from pathlib import Path

raw = sys.stdin.read()
data = json.loads(raw) if raw.strip() else {}
session_id = data.get("session_id", "unknown")
out = Path.home() / ".claude" / "logs" / session_id
out.mkdir(parents=True, exist_ok=True)

with (out / "events.jsonl").open("a", encoding="utf-8") as f:
    f.write(json.dumps(data, ensure_ascii=False) + "\n")
```

保存为：

```text
bin/my_hook.py
```

然后：

```bash
chmod +x bin/my_hook.py
```

### 6.5 写 marketplace.json

```bash
cat > .claude-plugin/marketplace.json <<'JSON'
{
  "name": "my-plugins",
  "owner": {
    "name": "me"
  },
  "plugins": [
    {
      "name": "my-plugin",
      "source": "./",
      "description": "My Claude Code plugin.",
      "version": "0.1.0"
    }
  ]
}
JSON
```

### 6.6 校验

```bash
python3 -m py_compile bin/my_hook.py
claude plugin validate .
```

## 7. 插件安装方式

### 方式一：临时加载本地插件，适合开发调试

```bash
claude --plugin-dir /path/to/my-plugin
```

特点：

- 不需要安装到用户配置。
- 只对当前 Claude Code 会话生效。
- 适合开发时快速验证。

进入 Claude Code 后执行：

```text
/hooks
```

确认 hooks 是否加载。

### 方式二：通过本地 marketplace 安装

```bash
claude plugin marketplace add /path/to/my-plugin
claude plugin install my-plugin@my-plugins
```

也可以在 Claude Code 交互界面里执行：

```text
/plugin marketplace add /path/to/my-plugin
/plugin install my-plugin@my-plugins
```

特点：

- 模拟正式 marketplace 安装流程。
- 适合本机长期使用。
- 安装后一般需要重启 Claude Code。

### 方式三：通过 GitHub marketplace 安装

如果仓库是公开 GitHub 仓库，并且 `.claude-plugin/marketplace.json` 位于仓库内：

```bash
claude plugin marketplace add owner/repo
claude plugin install my-plugin@my-plugins
```

本仓库安装命令：

```bash
claude plugin marketplace add markyang2020/claude-logger
claude plugin install claude-logger@mark-local-plugins
```

特点：

- 最适合公开分发。
- 用户只需要 Claude Code 能访问 GitHub。
- 如果是私有仓库，用户需要提前配置 GitHub 凭据。

### 方式四：通过 Git URL 安装 marketplace

```bash
claude plugin marketplace add https://github.com/owner/repo.git
claude plugin install my-plugin@my-plugins
```

也可以使用其他 Git 托管服务，例如 GitLab、Bitbucket、自建 Git 服务。

### 方式五：通过远程 marketplace.json URL 添加

```bash
claude plugin marketplace add https://example.com/marketplace.json
```

注意：

- URL 方式通常只下载 marketplace JSON 本身。
- 如果 `plugins[].source` 是 `./plugins/foo` 这种相对路径，URL 方式可能无法安装，因为插件文件不会随 JSON 一起下载。
- URL marketplace 更适合搭配 `github`、`url`、`git-subdir`、`npm` 等外部插件 source。

### 方式六：通过插件 zip 临时加载

```bash
claude --plugin-url https://example.com/my-plugin.zip
```

特点：

- 适合测试 CI 构建产物。
- 只对当前会话生效。

## 8. 安装 scope

安装 plugin 时可以指定 scope：

```bash
claude plugin install my-plugin@my-plugins --scope user
claude plugin install my-plugin@my-plugins --scope project
claude plugin install my-plugin@my-plugins --scope local
```

区别：

- `user`：默认安装到当前用户，适合个人长期使用。
- `project`：写入项目配置，适合团队共享。
- `local`：写入本地配置，适合当前项目但不提交到 Git。

## 9. 常用管理命令

查看 marketplace：

```bash
claude plugin marketplace list
```

更新 marketplace：

```bash
claude plugin marketplace update my-plugins
```

查看已安装插件：

```bash
claude plugin list
claude plugin list --json
```

更新插件：

```bash
claude plugin update my-plugin@my-plugins
```

禁用插件：

```bash
claude plugin disable my-plugin@my-plugins
```

启用插件：

```bash
claude plugin enable my-plugin@my-plugins
```

卸载插件：

```bash
claude plugin uninstall my-plugin@my-plugins
```

## 10. 调试流程

推荐顺序：

1. 校验 JSON：
   ```bash
   python3 -m json.tool .claude-plugin/plugin.json >/dev/null
   python3 -m json.tool hooks/hooks.json >/dev/null
   python3 -m json.tool .claude-plugin/marketplace.json >/dev/null
   ```
2. 校验脚本：
   ```bash
   python3 -m py_compile bin/my_hook.py
   ```
3. 校验插件：
   ```bash
   claude plugin validate .
   ```
4. 临时加载：
   ```bash
   claude --plugin-dir .
   ```
5. 进入 Claude Code 后查看：
   ```text
   /hooks
   /plugin list
   ```
6. 触发一次真实任务，查看日志。
7. 如果 hook 没有运行，使用：
   ```bash
   claude --debug --plugin-dir .
   ```

## 11. 发布与更新流程

### 11.1 首次发布

```bash
git init
git add .
git commit -m "Initial plugin"
gh repo create owner/my-plugin --public --source=. --remote=origin --push
```

用户安装：

```bash
claude plugin marketplace add owner/my-plugin
claude plugin install my-plugin@my-plugins
```

### 11.2 发布新版本

如果 `plugin.json` 里写了显式版本：

```json
{
  "version": "0.1.0"
}
```

那么更新插件时必须 bump 版本，例如：

```json
{
  "version": "0.1.1"
}
```

同时建议同步更新 `.claude-plugin/marketplace.json` 里的 `plugins[].version`。

然后：

```bash
git add .
git commit -m "Release 0.1.1"
git push
```

用户侧更新：

```bash
claude plugin marketplace update my-plugins
claude plugin update my-plugin@my-plugins
```

## 12. 本仓库 claude-logger 的完整使用流程

### 12.1 安装

```bash
claude plugin marketplace add markyang2020/claude-logger
claude plugin install claude-logger@mark-local-plugins
```

重启 Claude Code。

### 12.2 验证 hooks

进入 Claude Code 后执行：

```text
/hooks
```

应能看到这些 hook：

```text
SessionStart
UserPromptSubmit
PostToolUse
PostToolUseFailure
Stop
StopFailure
SessionEnd
```

### 12.3 使用

正常向 Claude Code 提问或让它执行多步任务。任务结束后查看：

```bash
ls -lt ~/.claude/logs | head
find ~/.claude/logs -maxdepth 2 -name summary.md -print | tail -20
```

打开某个报告：

```bash
open ~/.claude/logs/<session-id>/summary.md
```

报告中的 `对话过程` 会按 transcript 时间顺序展示用户、Assistant、工具请求、工具结果。每条记录使用 `yyyy-mm-dd hh:mm:ss` 格式展示时间。异常中止会在报告顶部状态中以红色标记。

### 12.4 排查中途停止

优先看报告中的：

```text
结束原因判断
工具调用
Transcript stop_reason 统计
最终输出
```

常见含义：

- `normal_completion`：Claude Code 认为任务正常结束。
- `api_error`：API 或模型调用错误触发 `StopFailure`。
- `session_ended`：没有正常 Stop 报告，SessionEnd 退出时补生成。
- 工具调用最后一条失败：重点看工具错误、stderr、权限、路径和超时。
- 没有最终输出：可能是 API 错误、用户中断、进程退出，或 Stop hook 没有机会运行。

## 13. 常见问题

### 13.1 为什么看不到隐藏思考过程

Claude Code hooks 不暴露隐藏 chain-of-thought。插件只能记录 transcript 中可见的 thinking/summary、assistant 输出、工具调用和工具结果。

### 13.2 为什么 marketplace add 后安装不到插件

检查：

- `.claude-plugin/marketplace.json` 是否存在。
- `plugins[].source` 是否指向正确目录。
- `claude plugin validate .` 是否通过。
- 如果用 URL 方式添加 marketplace，避免使用相对路径 source。

### 13.3 为什么 hooks 不触发

检查：

- `hooks/hooks.json` 是否在插件根目录。
- hook 脚本是否可执行。
- command 是否使用 `${CLAUDE_PLUGIN_ROOT}` 引用插件内文件。
- 是否重启了 Claude Code。
- `/hooks` 是否能看到插件提供的 hook。

### 13.4 为什么更新后仍然是旧代码

如果插件设置了显式版本，必须 bump `plugin.json` 版本号，并让用户执行：

```bash
claude plugin marketplace update my-plugins
claude plugin update my-plugin@my-plugins
```

必要时重启 Claude Code。
