#!/usr/bin/env python3
"""Claude Code lifecycle logger plugin.

This file is intentionally self-contained and uses only the Python standard
library so the plugin can run in a fresh Claude Code environment.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


MAX_FIELD_CHARS = int(os.environ.get("CLAUDE_LOGGER_MAX_FIELD_CHARS", "6000"))
LOG_ROOT = Path(os.environ.get("CLAUDE_LOGGER_DIR", "~/.claude/logs")).expanduser()


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def local_now_display() -> str:
    return dt.datetime.now().replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")


def display_time(value: Any) -> str:
    if not value:
        return "N/A"
    text = str(value)
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text[:19].replace("T", " ")
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone()
    return parsed.replace(tzinfo=None, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")


def timestamp_sort_key(value: Any) -> tuple[int, str]:
    if not value:
        return (1, "")
    text = str(value)
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return (1, text)
    return (0, parsed.astimezone(dt.UTC).isoformat())


def safe_name(value: str) -> str:
    value = value or "unknown"
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value)


def truncate(value: Any, limit: int = MAX_FIELD_CHARS) -> str:
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if len(text) <= limit:
        return text
    return text[:limit] + f"... [truncated {len(text) - limit} chars]"


def read_hook_input() -> tuple[str, dict[str, Any]]:
    raw = sys.stdin.read()
    if not raw.strip():
        return "", {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = {"_raw": raw}
    if not isinstance(parsed, dict):
        parsed = {"_value": parsed}
    return raw, parsed


def session_dir_for(data: dict[str, Any]) -> Path:
    session_id = str(data.get("session_id") or data.get("sessionId") or os.environ.get("CLAUDE_SESSION_ID") or "unknown")
    session_dir = LOG_ROOT / safe_name(session_id)
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir


def append_jsonl(path: Path, obj: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                rows.append(value)
    return rows


def merge_metadata(session_dir: Path, data: dict[str, Any], timestamp: str, event: str) -> None:
    metadata_path = session_dir / "metadata.json"
    if metadata_path.exists():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            metadata = {}
    else:
        metadata = {}

    for key in ("session_id", "transcript_path", "cwd", "permission_mode"):
        value = data.get(key)
        if value not in (None, ""):
            metadata[key] = value
    metadata["last_hook_event_name"] = data.get("hook_event_name") or event
    metadata["last_seen_at"] = timestamp
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def reset_session_if_fresh_start(session_dir: Path, data: dict[str, Any]) -> None:
    source = data.get("source")
    if source == "resume":
        return
    for name in ("events.jsonl", "hook-inputs.jsonl", "summary.md", "metadata.json"):
        path = session_dir / name
        if path.exists():
            path.unlink()


def record_common_event(session_dir: Path, event: str, raw: str, data: dict[str, Any], timestamp: str) -> None:
    common = {
        "session_id": data.get("session_id") or data.get("sessionId"),
        "transcript_path": data.get("transcript_path"),
        "cwd": data.get("cwd"),
        "permission_mode": data.get("permission_mode"),
        "hook_event_name": data.get("hook_event_name") or event,
    }
    common = {k: v for k, v in common.items() if v not in (None, "")}
    append_jsonl(
        session_dir / "events.jsonl",
        {
            "event": event,
            "timestamp": timestamp,
            "common": common,
            "raw": truncate(raw),
        },
    )
    append_jsonl(session_dir / "hook-inputs.jsonl", {"event": event, "timestamp": timestamp, "input": data})
    merge_metadata(session_dir, data, timestamp, event)


def record_prompt(session_dir: Path, data: dict[str, Any], timestamp: str) -> None:
    append_jsonl(
        session_dir / "events.jsonl",
        {
            "event": "user_prompt",
            "timestamp": timestamp,
            "prompt": str(data.get("prompt") or ""),
        },
    )


def record_tool(session_dir: Path, data: dict[str, Any], timestamp: str, failed: bool) -> None:
    entry: dict[str, Any] = {
        "event": "tool_call_failure" if failed else "tool_call",
        "timestamp": timestamp,
        "tool": data.get("tool_name") or "unknown",
        "tool_use_id": data.get("tool_use_id"),
        "duration_ms": data.get("duration_ms"),
        "input": data.get("tool_input") or {},
    }
    if failed:
        entry["error"] = data.get("error") or data.get("message") or ""
    else:
        entry["response"] = data.get("tool_response")
    append_jsonl(session_dir / "events.jsonl", entry)


def record_completion(session_dir: Path, data: dict[str, Any], timestamp: str, event: str) -> None:
    if event == "Stop":
        entry = {
            "event": "completion",
            "timestamp": timestamp,
            "kind": "stop",
            "status": "normal_completion",
            "reason": "Claude finished responding",
            "stop_hook_active": data.get("stop_hook_active"),
            "last_assistant_message": data.get("last_assistant_message") or "",
        }
    elif event == "StopFailure":
        entry = {
            "event": "completion",
            "timestamp": timestamp,
            "kind": "stop_failure",
            "status": "api_error",
            "reason": data.get("error") or "unknown",
            "error_details": data.get("error_details") or "",
            "last_assistant_message": data.get("last_assistant_message") or "",
        }
    else:
        entry = {
            "event": "completion",
            "timestamp": timestamp,
            "kind": "session_end",
            "status": "session_ended",
            "reason": data.get("reason") or "other",
        }
    append_jsonl(session_dir / "events.jsonl", entry)


def record_compact(session_dir: Path, data: dict[str, Any], timestamp: str, event: str) -> None:
    trigger = str(data.get("trigger") or "unknown")
    entry: dict[str, Any] = {
        "event": "compact",
        "timestamp": timestamp,
        "phase": "before" if event == "PreCompact" else "after",
        "hook_event_name": event,
        "trigger": trigger,
    }
    if event == "PreCompact":
        entry["custom_instructions"] = data.get("custom_instructions") or ""
    else:
        entry["compact_summary"] = data.get("compact_summary") or ""
    append_jsonl(session_dir / "events.jsonl", entry)


def load_metadata(session_dir: Path) -> dict[str, Any]:
    path = session_dir / "metadata.json"
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def normalize_content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text":
                parts.append(str(item.get("text") or ""))
            elif item.get("type") == "tool_result":
                parts.append(str(item.get("content") or ""))
        return "\n".join(p for p in parts if p)
    return ""


def content_blocks(content: Any) -> list[dict[str, Any]]:
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if isinstance(content, list):
        return [item for item in content if isinstance(item, dict)]
    return []


def transcript_rows(path_value: Any) -> list[dict[str, Any]]:
    if not path_value:
        return []
    path = Path(str(path_value).replace("~", str(Path.home()), 1)).expanduser()
    if not path.exists():
        return []
    return load_jsonl(path)


def assistant_blocks(rows: list[dict[str, Any]], block_type: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for row in rows:
        if row.get("type") != "assistant":
            continue
        message = row.get("message")
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for item in content:
            if isinstance(item, dict) and item.get("type") == block_type:
                blocks.append(item)
    return blocks


def transcript_user_prompts(rows: list[dict[str, Any]]) -> list[str]:
    prompts: list[str] = []
    for row in rows:
        if row.get("type") != "user":
            continue
        message = row.get("message")
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if isinstance(content, str):
            prompts.append(content)
    return prompts


def transcript_tool_results(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for row in rows:
        if row.get("type") != "user":
            continue
        message = row.get("message")
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for item in content:
            if isinstance(item, dict) and item.get("type") == "tool_result":
                results.append(item)
    return results


def transcript_stop_reasons(rows: list[dict[str, Any]]) -> Counter[str]:
    reasons: Counter[str] = Counter()
    for row in rows:
        if row.get("type") != "assistant":
            continue
        message = row.get("message")
        if isinstance(message, dict):
            reason = message.get("stop_reason")
            if reason:
                reasons[str(reason)] += 1
    return reasons


def transcript_usage(rows: list[dict[str, Any]]) -> Counter[str]:
    totals: Counter[str] = Counter()
    usage_keys = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
    for row in rows:
        if row.get("type") != "assistant":
            continue
        message = row.get("message")
        if not isinstance(message, dict):
            continue
        usage = message.get("usage")
        if not isinstance(usage, dict):
            continue
        for key in usage_keys:
            value = usage.get(key)
            if isinstance(value, int):
                totals[key] += value
    return totals


def conversation_timeline(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    timeline: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        row_type = row.get("type")
        timestamp = display_time(row.get("timestamp"))
        sort_key = timestamp_sort_key(row.get("timestamp")) + (index,)
        message = row.get("message")
        if row_type not in ("user", "assistant") or not isinstance(message, dict):
            continue

        role = str(message.get("role") or row_type)
        for block in content_blocks(message.get("content")):
            block_type = str(block.get("type") or "text")
            if role == "user" and block_type == "text":
                text = str(block.get("text") or "")
                if text:
                    timeline.append({"sort_key": sort_key, "time": timestamp, "kind": "用户", "text": text})
            elif role == "user" and block_type == "tool_result":
                text = str(block.get("content") or "")
                prefix = f"tool_result `{block.get('tool_use_id') or 'unknown'}`"
                if block.get("is_error"):
                    prefix += " ERROR"
                timeline.append({"sort_key": sort_key, "time": timestamp, "kind": "工具结果", "text": f"{prefix}\n{truncate(text, 1000)}"})
            elif role == "assistant" and block_type == "text":
                text = str(block.get("text") or "")
                if text:
                    timeline.append({"sort_key": sort_key, "time": timestamp, "kind": "Assistant", "text": text})
            elif role == "assistant" and block_type == "thinking":
                thinking = str(block.get("thinking") or "")
                if thinking:
                    timeline.append({"sort_key": sort_key, "time": timestamp, "kind": "可见思考摘要", "text": thinking})
            elif role == "assistant" and block_type == "tool_use":
                name = block.get("name") or "unknown"
                tool_input = block.get("input") or {}
                timeline.append({"sort_key": sort_key, "time": timestamp, "kind": "工具请求", "text": f"{name} {truncate(tool_input, 1000)}"})
    return [{k: str(v) for k, v in item.items() if k != "sort_key"} for item in sorted(timeline, key=lambda item: item["sort_key"])]


def compact_label(event: dict[str, Any]) -> str:
    trigger = str(event.get("trigger") or "unknown")
    phase = str(event.get("phase") or "unknown")
    phase_label = "压缩开始" if phase == "before" else "压缩完成"
    trigger_label = "自动压缩" if trigger == "auto" else "手动压缩" if trigger == "manual" else f"{trigger} 压缩"
    return f"{trigger_label} · {phase_label}"


def compact_html(event: dict[str, Any]) -> str:
    trigger = str(event.get("trigger") or "unknown")
    color = "#b45309" if trigger == "auto" else "#1d4ed8" if trigger == "manual" else "#6b7280"
    background = "#fff7ed" if trigger == "auto" else "#eff6ff" if trigger == "manual" else "#f3f4f6"
    label = compact_label(event)
    return f'<span style="color: {color}; background: {background}; font-weight: 700; padding: 2px 6px; border-radius: 4px;">{label}</span>'


def compact_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        [event for event in events if event.get("event") == "compact"],
        key=lambda event: timestamp_sort_key(event.get("timestamp")),
    )


def first_timestamp(events: list[dict[str, Any]]) -> str:
    return str(events[0].get("timestamp") or "N/A") if events else "N/A"


def last_timestamp(events: list[dict[str, Any]]) -> str:
    return str(events[-1].get("timestamp") or "N/A") if events else "N/A"


def completion_event(events: list[dict[str, Any]]) -> dict[str, Any]:
    for event in reversed(events):
        if event.get("event") == "completion":
            return event
    return {}


def duration_text(start: str, end: str) -> str:
    try:
        start_dt = dt.datetime.fromisoformat(start.replace("Z", "+00:00"))
        end_dt = dt.datetime.fromisoformat(end.replace("Z", "+00:00"))
    except ValueError:
        return "N/A"
    seconds = int((end_dt - start_dt).total_seconds())
    if seconds < 0:
        return "N/A"
    return f"{seconds // 60}m {seconds % 60}s"


def md_quote(text: str) -> str:
    lines = text.splitlines() or [""]
    return "\n".join(f"> {line}" for line in lines)


def code_inline(value: Any, limit: int = 500) -> str:
    text = truncate(value, limit).replace("\n", " ")
    return f"`{text}`"


def status_html(completion: dict[str, Any]) -> str:
    status = str(completion.get("status") or "unknown")
    kind = str(completion.get("kind") or "unknown")
    reason = str(completion.get("reason") or "unknown")
    is_error = status not in ("normal_completion",) or kind in ("stop_failure", "session_end")
    text = f"{status} / {kind} / {reason}"
    if is_error:
        return f'<span style="color: red; font-weight: 700;">异常中止：{text}</span>'
    return f'<span style="color: green; font-weight: 700;">正常完成：{text}</span>'


def generate_summary(session_dir: Path) -> None:
    events = load_jsonl(session_dir / "events.jsonl")
    metadata = load_metadata(session_dir)
    rows = transcript_rows(metadata.get("transcript_path"))
    completion = completion_event(events)

    prompts = [str(e.get("prompt") or "") for e in events if e.get("event") == "user_prompt" and e.get("prompt")]
    if not prompts:
        prompts = transcript_user_prompts(rows)[-5:]

    tool_events = [e for e in events if e.get("event") in ("tool_call", "tool_call_failure")]
    tool_counter = Counter(str(e.get("tool") or "unknown") for e in tool_events)
    tool_uses = assistant_blocks(rows, "tool_use")[-80:]
    tool_results = transcript_tool_results(rows)[-80:]
    text_blocks = assistant_blocks(rows, "text")
    thinking_blocks = assistant_blocks(rows, "thinking")
    stop_reasons = transcript_stop_reasons(rows)
    usage = transcript_usage(rows)
    timeline = conversation_timeline(rows)
    compactions = compact_events(events)

    start = first_timestamp(events)
    end = last_timestamp(events)
    session_id = session_dir.name
    transcript_path = metadata.get("transcript_path") or ""
    final_from_hook = str(completion.get("last_assistant_message") or "")
    final_from_transcript = str(text_blocks[-1].get("text") or "") if text_blocks else ""

    lines: list[str] = [
        "# Claude Code 会话日志",
        "",
        f"- **报告生成时间:** {local_now_display()}",
        f"- **Session ID:** `{session_id}`",
        f"- **状态:** {status_html(completion)}",
        f"- **完成类型:** `{completion.get('kind') or 'unknown'}`",
        f"- **完成原因:** {completion.get('reason') or 'unknown'}",
        f"- **开始时间:** {display_time(start)}",
        f"- **结束时间:** {display_time(end)}",
        f"- **耗时:** {duration_text(start, end)}",
    ]
    if metadata.get("cwd"):
        lines.append(f"- **工作目录:** `{metadata['cwd']}`")
    if metadata.get("permission_mode"):
        lines.append(f"- **权限模式:** `{metadata['permission_mode']}`")
    if transcript_path:
        lines.append(f"- **Transcript:** `{transcript_path}`")

    lines += ["", "## 对话过程", ""]
    if timeline:
        for item in timeline:
            lines.append(f"### {item['time']} · {item['kind']}")
            lines.append("")
            lines.append(item["text"])
            lines.append("")
    else:
        lines.append("_未能从 transcript 生成按时间顺序的对话过程。_")
        lines.append("")

    if compactions:
        lines += ["## 上下文压缩事件", ""]
        lines.append("这些事件表示 Claude Code 对会话上下文做了压缩。自动压缩通常发生在上下文窗口接近或达到上限时。")
        lines.append("")
        for event in compactions:
            lines.append(f"### {display_time(event.get('timestamp'))} · {compact_html(event)}")
            lines.append("")
            if event.get("custom_instructions"):
                lines.append("**自定义压缩指令：**")
                lines.append("")
                lines.append(str(event["custom_instructions"]))
                lines.append("")
            if event.get("compact_summary"):
                lines.append("**压缩摘要：**")
                lines.append("")
                lines.append(truncate(event["compact_summary"], 4000))
                lines.append("")

    lines += ["## 用户问题摘要", ""]
    if prompts:
        prompt_events = [e for e in events if e.get("event") == "user_prompt" and e.get("prompt")]
        if prompt_events:
            for event in prompt_events:
                lines.append(f"### {display_time(event.get('timestamp'))}")
                lines.append("")
                lines.append(md_quote(str(event.get("prompt") or "")))
                lines.append("")
        else:
            for prompt in prompts:
                lines.append(md_quote(prompt))
                lines.append("")
    elif prompts:
        for prompt in prompts:
            lines.append(md_quote(prompt))
            lines.append("")
    else:
        lines.append("_未捕获到用户问题。_")
        lines.append("")

    lines += ["## 工具调用", "", f"- Hook 捕获数量: {len(tool_events)}"]
    if tool_counter:
        lines += ["", "### 工具统计", "", "```text"]
        for name, count in tool_counter.most_common():
            lines.append(f"{count:4d} {name}")
        lines.append("```")

    if tool_events:
        lines += ["", "### Hook 捕获明细", ""]
        for event in tool_events[-120:]:
            status = " **FAILED**" if event.get("event") == "tool_call_failure" else ""
            duration = f" ({event.get('duration_ms')} ms)" if event.get("duration_ms") not in (None, "") else ""
            line = f"- **{event.get('tool') or 'unknown'}**{status}{duration}: {code_inline(event.get('input') or {})}"
            if event.get("error"):
                line += f" - {truncate(event.get('error'), 300)}"
            lines.append(line)

    if tool_uses:
        lines += ["", "### Transcript 工具请求", ""]
        for block in tool_uses:
            lines.append(f"- **{block.get('name') or 'unknown'}** {code_inline(block.get('input') or {})}")

    if tool_results:
        lines += ["", "### Transcript 工具结果摘要", ""]
        for result in tool_results:
            prefix = "**ERROR** " if result.get("is_error") else ""
            lines.append(f"- `{result.get('tool_use_id') or 'unknown'}` {prefix}{truncate(result.get('content') or '', 500).replace(chr(10), ' ')}")

    lines += ["", "## 大模型思考过程", ""]
    visible_thinking = [str(b.get("thinking") or "") for b in thinking_blocks if b.get("thinking")]
    if visible_thinking:
        lines.append("Claude Code transcript 中存在可见 thinking 摘要。隐藏链路思考不会暴露给插件。")
        lines += ["", "```text"]
        lines.extend(visible_thinking[-10:])
        lines.append("```")
    else:
        lines.append("Claude Code hook 不暴露隐藏链路思考；这里只能记录 transcript 中可见的 thinking/summary、assistant 输出、工具请求和工具结果。")

    if text_blocks:
        lines += ["", "## Assistant 可见输出", ""]
        for block in text_blocks[-20:]:
            text = str(block.get("text") or "")
            if text:
                lines.append(text)
                lines.append("")

    lines += ["## 最终输出", ""]
    if final_from_hook:
        lines.append(final_from_hook)
    elif final_from_transcript:
        lines.append(final_from_transcript)
    else:
        lines.append("_未捕获到最终 assistant 文本，可能是 API 错误、会话退出、用户中断或进程异常退出。_")

    lines += ["", "## 结束原因判断", ""]
    lines.append(f"- Hook 完成类型: `{completion.get('kind') or 'unknown'}`")
    lines.append(f"- Hook 状态字段: `{completion.get('status') or 'unknown'}`")
    lines.append(f"- Hook 原因字段: `{completion.get('reason') or 'unknown'}`")
    if completion.get("error_details"):
        lines.append(f"- 错误详情: {completion['error_details']}")
    if stop_reasons:
        lines += ["- Transcript stop_reason 统计:", "```text"]
        for name, count in stop_reasons.most_common():
            lines.append(f"{count:4d} {name}")
        lines.append("```")

    if usage:
        lines += ["", "## Token 用量", ""]
        for key in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"):
            lines.append(f"- {key}: {usage.get(key, 0)}")

    lines += [
        "",
        "## 原始文件",
        "",
        f"- Hook 原始输入: `{session_dir / 'hook-inputs.jsonl'}`",
        f"- 结构化事件: `{session_dir / 'events.jsonl'}`",
        f"- 报告文件: `{session_dir / 'summary.md'}`",
        "",
        "_Generated by claude-logger._",
        "",
    ]

    (session_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    event_arg = sys.argv[1] if len(sys.argv) > 1 else ""
    raw, data = read_hook_input()
    event = str(data.get("hook_event_name") or event_arg or "Unknown")
    timestamp = utc_now()
    session_dir = session_dir_for(data)

    if event == "SessionStart":
        reset_session_if_fresh_start(session_dir, data)

    record_common_event(session_dir, event, raw, data, timestamp)

    if event == "UserPromptSubmit":
        record_prompt(session_dir, data, timestamp)
    elif event == "PostToolUse":
        record_tool(session_dir, data, timestamp, failed=False)
    elif event == "PostToolUseFailure":
        record_tool(session_dir, data, timestamp, failed=True)
    elif event in ("PreCompact", "PostCompact"):
        record_compact(session_dir, data, timestamp, event)
    elif event in ("Stop", "StopFailure", "SessionEnd"):
        record_completion(session_dir, data, timestamp, event)
        generate_summary(session_dir)
        if event in ("Stop", "StopFailure"):
            print((session_dir / "summary.md").read_text(encoding="utf-8"))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
