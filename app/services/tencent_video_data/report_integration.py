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


def _format_number(value: Any) -> str:
    if value in (None, ""):
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number.is_integer():
        return f"{int(number):,}"
    return f"{number:,.2f}"


def _format_rate(value: Any) -> str:
    if value in (None, ""):
        return ""
    try:
        return f"{float(value) * 100:.2f}%"
    except (TypeError, ValueError):
        return str(value)


def _append_non_empty(lines: list[str], text: str) -> None:
    text = str(text or "").strip()
    if text and text not in {"None", "null", "[]"}:
        lines.append(f"- {text}")


def _render_diagnosis_items(value: Any, prefix: str) -> list[str]:
    lines: list[str] = []
    for item in _as_list(value):
        if isinstance(item, str):
            _append_non_empty(lines, f"{prefix}{item}")
    return lines


def _render_account_summary(summary: dict[str, Any]) -> list[str]:
    lines = _render_diagnosis_items(summary.get("diagnosis"), "数据提示：")
    date_range = summary.get("date_range") or {}
    if isinstance(date_range, dict):
        start = str(date_range.get("start") or "").strip()
        end = str(date_range.get("end") or "").strip()
        if start and end:
            lines.insert(0, f"- 数据范围：{start} 至 {end}。")

    valid_rate = summary.get("valid_view_rate") or {}
    if isinstance(valid_rate, dict):
        median_rate = _format_rate(valid_rate.get("median"))
        if median_rate:
            _append_non_empty(lines, f"数据提示：账号有效播放率中位数约为 {median_rate}，建议结合具体集数继续复盘。")
    return lines


def _render_album_summary(summary: dict[str, Any]) -> list[str]:
    lines = _render_diagnosis_items(summary.get("diagnosis"), "数据提示：")
    top_days = _as_list(summary.get("top_days_by_valid_views"))
    if top_days:
        rendered_days = []
        for item in top_days[:3]:
            if not isinstance(item, dict):
                continue
            date = str(item.get("date") or "").strip()
            title = str(item.get("title") or "").strip()
            valid_views = _format_number(item.get("total_valid_views"))
            label = " ".join(part for part in [date, title] if part)
            if label and valid_views:
                rendered_days.append(f"{label}（有效播放 {valid_views}）")
        if rendered_days:
            _append_non_empty(lines, f"数据提示：有效播放较高的记录包括：{'；'.join(rendered_days)}。")
    return lines


def _render_high_exposure_low_valid(items: Any) -> list[str]:
    lines: list[str] = []
    for item in _as_list(items)[:5]:
        if not isinstance(item, dict):
            continue
        label = _episode_label(item)
        total_views = _format_number(item.get("total_views"))
        valid_rate = _format_rate(item.get("valid_view_rate"))
        reason = str(item.get("reason") or "播放量相对较高，但有效播放率低于对照水平").strip()
        detail = []
        if total_views:
            detail.append(f"播放量 {total_views}")
        if valid_rate:
            detail.append(f"有效播放率 {valid_rate}")
        suffix = f"（{'，'.join(detail)}）" if detail else ""
        _append_non_empty(lines, f"数据提示：{label}{suffix}，{reason}，建议复盘前30秒、标题封面预期和本集冲突推进。")
    return lines


def _render_drop_off(items: Any) -> list[str]:
    lines: list[str] = []
    for item in _as_list(items)[:10]:
        if not isinstance(item, dict):
            continue
        label = _episode_label(item)
        views_drop = _format_rate(item.get("views_drop_rate"))
        valid_drop = _format_rate(item.get("valid_views_drop_rate"))
        detail = []
        if views_drop:
            detail.append(f"播放量环比下降 {views_drop}")
        if valid_drop:
            detail.append(f"有效播放环比下降 {valid_drop}")
        suffix = f"（{'，'.join(detail)}）" if detail else ""
        _append_non_empty(lines, f"数据提示：{label}{suffix}，建议复盘上一集结尾钩子和本集开场承接。")
    return lines


def _render_interaction_or_share(items: Any, label: str, metric_name: str, metric_field: str) -> list[str]:
    lines: list[str] = []
    for item in _as_list(items)[:5]:
        if not isinstance(item, dict):
            continue
        episode_label = _episode_label(item)
        metric = _format_number(item.get(metric_field))
        views = _format_number(item.get("total_views"))
        detail = []
        if metric:
            detail.append(f"{metric_name} {metric}")
        if views:
            detail.append(f"播放量 {views}")
        suffix = f"（{'，'.join(detail)}）" if detail else ""
        _append_non_empty(lines, f"数据提示：{episode_label}{suffix}进入{label}，建议提取其中的情绪点、反转点和话题点。")
    return lines


def build_market_feedback_markdown(summary: dict[str, Any] | None) -> str:
    if not summary:
        return ""

    lines = [
        "",
        "## 腾讯视频平台反馈分析",
        "",
        "### 账号整体趋势",
        "",
    ]

    account = summary.get("account_growth_summary") or {}
    account_lines = _render_account_summary(account) if isinstance(account, dict) else []
    lines.extend(account_lines or ["- 暂无可用于账号整体趋势判断的平台数据。"])

    lines.extend(["", "### 专辑表现", ""])
    album = summary.get("album_performance_summary") or {}
    album_lines = _render_album_summary(album) if isinstance(album, dict) else []
    lines.extend(album_lines or ["- 暂无可用于专辑表现判断的平台数据。"])

    lines.extend(["", "### 高曝光低有效播放集数", ""])
    high_exposure_lines = _render_high_exposure_low_valid(summary.get("high_exposure_low_valid_episodes"))
    lines.extend(high_exposure_lines or ["- 暂无可展示的高曝光低有效播放集数。"])

    lines.extend(["", "### 剧集掉点排行", ""])
    drop_lines = _render_drop_off(summary.get("episode_drop_off_ranking"))
    lines.extend(drop_lines or ["- 暂无可展示的相邻集数掉点记录。"])

    lines.extend(["", "### 高互动/高分享集数", ""])
    interaction_lines = _render_interaction_or_share(
        summary.get("high_interaction_episodes"),
        "高互动样本",
        "互动分",
        "interaction_score",
    )
    share_lines = _render_interaction_or_share(
        summary.get("high_share_episodes"),
        "高分享样本",
        "分享数",
        "shares",
    )
    lines.extend(interaction_lines + share_lines or ["- 暂无可展示的高互动或高分享集数。"])

    lines.extend(["", "### 剧本复盘建议", ""])
    suggestion_lines = [
        f"- 建议复盘：{str(item).strip()}"
        for item in _as_list(summary.get("script_review_suggestions"))
        if str(item or "").strip()
    ]
    lines.extend(suggestion_lines or ["- 当前平台数据不足，建议继续以纯文本审核结论为主。"])

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
