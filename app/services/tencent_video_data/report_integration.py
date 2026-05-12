from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_SUMMARY_PATH = Path("data/tencent_video_normalized/market_feedback_summary.json")


def load_market_feedback_summary(path: str | Path = DEFAULT_SUMMARY_PATH) -> dict[str, Any] | None:
    summary_path = Path(path)
    if not summary_path.exists():
        return None
    try:
        with summary_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def _episode_label(item: dict[str, Any]) -> str:
    title = str(item.get("title") or "").strip()
    episode = item.get("episode_no")
    parts = []
    if title:
        parts.append(title)
    if episode not in (None, ""):
        parts.append(f"第{episode}集")
    return " ".join(parts) or "未标注集数"


def build_market_feedback_markdown(summary: dict[str, Any] | None) -> str:
    if not summary:
        return ""

    lines = [
        "",
        "## 八、腾讯视频平台反馈分析",
        "",
        "### 账号整体趋势",
        "",
    ]

    account = summary.get("account_growth_summary") or {}
    account_items = account.get("diagnosis")
    if isinstance(account_items, list) and account_items:
        lines.extend(f"- {item}" for item in account_items)
    else:
        lines.append(f"- {account.get('diagnosis', '暂无账号趋势数据。')}")

    lines.extend(["", "### 专辑表现", ""])
    album = summary.get("album_performance_summary") or {}
    album_items = album.get("diagnosis")
    if isinstance(album_items, list) and album_items:
        lines.extend(f"- {item}" for item in album_items)
    else:
        lines.append(f"- {album.get('diagnosis', '暂无专辑趋势数据。')}")

    lines.extend(["", "### 剧集异常点", ""])
    abnormal_sections = [
        ("有效播放下滑", summary.get("episode_drop_off_ranking")),
        ("高曝光低有效播放", summary.get("high_exposure_low_valid_episodes")),
        ("高互动", summary.get("high_interaction_episodes")),
        ("高分享", summary.get("high_share_episodes")),
        ("低停留", summary.get("low_retention_episodes")),
    ]
    has_abnormal = False
    for label, items in abnormal_sections:
        for item in _as_list(items)[:5]:
            if not isinstance(item, dict):
                continue
            has_abnormal = True
            lines.append(f"- {label}：{_episode_label(item)}")
    if not has_abnormal:
        lines.append("- 暂未发现可展示的剧集异常点。")

    lines.extend(["", "### 可用于剧本复盘的建议", ""])
    suggestions = _as_list(summary.get("script_review_suggestions"))
    if suggestions:
        lines.extend(f"- {item}" for item in suggestions)
    else:
        lines.append("- 当前平台数据不足，建议继续以文本审核结论为主。")

    note = summary.get("diagnostic_note")
    if note:
        lines.extend(["", f"> {note}"])

    return "\n".join(lines)


def append_market_feedback_section(markdown_text: str, summary_path: str | Path = DEFAULT_SUMMARY_PATH) -> str:
    summary = load_market_feedback_summary(summary_path)
    section = build_market_feedback_markdown(summary)
    if not section:
        return markdown_text
    return markdown_text.rstrip() + "\n" + section + "\n"
