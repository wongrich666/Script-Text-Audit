from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_DIRECTOR_BRIEF_PATH = Path("data/director_brief/director_brief.json")


def load_director_brief(
    path: str | Path = DEFAULT_DIRECTOR_BRIEF_PATH,
    warnings: list[str] | None = None,
) -> dict[str, Any] | None:
    brief_path = Path(path)
    if not brief_path.exists():
        return None

    try:
        with brief_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        if warnings is not None:
            warnings.append(f"{brief_path}: JSON 格式错误，已跳过导演目标匹配度分析。原因：{exc}")
        return None
    except Exception as exc:
        if warnings is not None:
            warnings.append(f"{brief_path}: 读取失败，已跳过导演目标匹配度分析。原因：{exc}")
        return None

    if not isinstance(data, dict):
        if warnings is not None:
            warnings.append(f"{brief_path}: JSON 顶层不是对象，已跳过导演目标匹配度分析。")
        return None
    return data


def _text(value: Any) -> str:
    return str(value or "").strip()


def _as_text_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item or "").strip()]
    text = _text(value)
    return [text] if text else []


def _append_field(lines: list[str], label: str, value: Any) -> None:
    text = _text(value)
    if text:
        lines.append(f"- {label}：{text}")


def _append_list_field(lines: list[str], label: str, value: Any) -> None:
    items = _as_text_list(value)
    if items:
        lines.append(f"- {label}：{'、'.join(items)}")


def build_director_brief_markdown(brief: dict[str, Any] | None) -> str:
    if not brief:
        return ""

    lines = [
        "",
        "## 导演目标匹配度分析",
        "",
        "以下内容来自可选导演表单，仅作为审核目标和偏好参考；当前不作为必填输入，也不替代剧本文本审核结论。",
        "",
    ]

    _append_field(lines, "项目名称", brief.get("project_name"))
    _append_field(lines, "题材类型", brief.get("genre"))
    _append_field(lines, "目标受众", brief.get("target_audience"))
    _append_field(lines, "平台目标", brief.get("platform_goal"))
    _append_list_field(lines, "核心卖点", brief.get("core_selling_points"))
    _append_field(lines, "导演关注重点", brief.get("director_focus"))
    _append_list_field(lines, "审核优先级", brief.get("review_priorities"))

    if len(lines) <= 5:
        return ""
    return "\n".join(lines)


def append_director_brief_section(
    markdown_text: str,
    brief_path: str | Path = DEFAULT_DIRECTOR_BRIEF_PATH,
    warnings: list[str] | None = None,
) -> str:
    brief = load_director_brief(brief_path, warnings=warnings)
    section = build_director_brief_markdown(brief)
    if not section:
        return markdown_text
    return markdown_text.rstrip() + "\n" + section + "\n"
