from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass
class AnalysisResult:
    generated_files: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)


def _read_csv(path: Path, warnings: list[str]) -> pd.DataFrame | None:
    if not path.exists():
        warnings.append(f"{path.name}: 文件不存在，已跳过对应分析。")
        return None
    try:
        return pd.read_csv(path)
    except Exception as exc:
        warnings.append(f"{path.name}: 读取失败，原因：{exc}")
        return None


def _safe_number(value: Any) -> float | None:
    if pd.isna(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_rate(value: Any) -> str:
    number = _safe_number(value)
    if number is None:
        return "暂无"
    return f"{number * 100:.2f}%"


def _top_records(
    df: pd.DataFrame,
    sort_by: str,
    columns: list[str],
    ascending: bool = False,
    limit: int = 5,
) -> list[dict[str, Any]]:
    if sort_by not in df.columns or df.empty:
        return []
    ranked = df.copy()
    ranked[sort_by] = pd.to_numeric(ranked[sort_by], errors="coerce")
    ranked = ranked.dropna(subset=[sort_by]).sort_values(sort_by, ascending=ascending).head(limit)
    return _clean_records(ranked[[column for column in columns if column in ranked.columns]].to_dict("records"))


def _clean_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def _clean_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {key: _clean_value(value) for key, value in record.items()}
        for record in records
    ]


def extract_episode_no_from_title(title: Any) -> int | None:
    if pd.isna(title):
        return None

    text = str(title)
    patterns = [
        r"(?:^|[^A-Za-z0-9])SJS[_-]?0*(\d+)(?:\D|$)",
        r"第\s*0*(\d+)\s*集",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


def _ensure_episode_no(work: pd.DataFrame) -> pd.DataFrame:
    if "episode_no" not in work.columns:
        work["episode_no"] = pd.NA

    work["episode_no"] = pd.to_numeric(work["episode_no"], errors="coerce")
    if "title" not in work.columns:
        return work

    missing_episode = work["episode_no"].isna()
    if missing_episode.any():
        extracted = work.loc[missing_episode, "title"].map(extract_episode_no_from_title)
        extracted = pd.to_numeric(extracted, errors="coerce")
        work.loc[missing_episode, "episode_no"] = extracted
    return work


def _sample_size_threshold(work: pd.DataFrame) -> float | None:
    if "total_views" not in work.columns:
        return None

    total_views = pd.to_numeric(work["total_views"], errors="coerce").dropna()
    if total_views.empty:
        return None
    return max(100.0, float(total_views.median()))


def build_account_summary(df: pd.DataFrame | None) -> dict[str, Any]:
    if df is None or df.empty:
        return {"status": "no_data", "diagnosis": "暂无账号趋势数据。"}

    summary: dict[str, Any] = {"status": "ok", "diagnosis": []}
    if "date" in df.columns:
        summary["date_range"] = {
            "start": str(df["date"].dropna().min()) if not df["date"].dropna().empty else "",
            "end": str(df["date"].dropna().max()) if not df["date"].dropna().empty else "",
        }

    for field, label in [
        ("followers", "粉丝数"),
        ("total_views", "总播放量"),
        ("total_valid_views", "总有效播放量"),
        ("likes", "点赞"),
        ("comments", "评论"),
        ("shares", "分享"),
    ]:
        if field not in df.columns:
            continue
        series = pd.to_numeric(df[field], errors="coerce").dropna()
        if series.empty:
            continue
        summary[field] = {
            "latest": float(series.iloc[-1]),
            "mean": float(series.mean()),
            "median": float(series.median()),
            "change": float(series.iloc[-1] - series.iloc[0]) if len(series) >= 2 else 0,
        }
        summary["diagnosis"].append(f"{label}最新值为 {summary[field]['latest']:.0f}，较首条记录变化 {summary[field]['change']:.0f}。")

    if "valid_view_rate" in df.columns:
        rate = pd.to_numeric(df["valid_view_rate"], errors="coerce").dropna()
        if not rate.empty:
            summary["valid_view_rate"] = {
                "mean": float(rate.mean()),
                "median": float(rate.median()),
                "latest": float(rate.iloc[-1]),
            }
            summary["diagnosis"].append(f"有效播放量占比中位数为 {_format_rate(rate.median())}。")

    return summary


def build_album_summary(df: pd.DataFrame | None) -> dict[str, Any]:
    if df is None or df.empty:
        return {"status": "no_data", "diagnosis": "暂无专辑趋势数据。"}

    summary: dict[str, Any] = {"status": "ok", "diagnosis": []}
    for field, label in [
        ("total_views", "总播放量"),
        ("total_valid_views", "总有效播放量"),
        ("valid_view_rate", "有效播放量占比"),
        ("avg_watch_duration", "单次播放时长"),
        ("album_subscribers", "专辑在追数"),
    ]:
        if field not in df.columns:
            continue
        series = pd.to_numeric(df[field], errors="coerce").dropna()
        if series.empty:
            continue
        summary[field] = {
            "mean": float(series.mean()),
            "median": float(series.median()),
            "max": float(series.max()),
        }
        value = _format_rate(series.median()) if field.endswith("rate") else f"{series.median():.2f}"
        summary["diagnosis"].append(f"{label}中位数为 {value}。")

    summary["top_days_by_valid_views"] = _top_records(
        df,
        "total_valid_views",
        ["date", "title", "total_valid_views", "valid_view_rate", "avg_watch_duration"],
    )
    return summary


def build_episode_diagnostics(df: pd.DataFrame | None) -> dict[str, Any]:
    if df is None or df.empty:
        return {
            "drop_off_ranking": [],
            "high_exposure_low_valid": [],
            "high_interaction_episodes": [],
            "high_share_episodes": [],
            "low_retention_episodes": [],
            "review_suggestions": ["暂无剧集趋势数据，无法给出分集复盘方向。"],
        }

    work = _ensure_episode_no(df.copy())
    for field in [
        "episode_no",
        "total_views",
        "total_valid_views",
        "valid_view_rate",
        "avg_watch_duration",
        "likes",
        "comments",
        "shares",
    ]:
        if field in work.columns:
            work[field] = pd.to_numeric(work[field], errors="coerce")

    columns = ["title", "episode_no", "total_views", "total_valid_views", "valid_view_rate", "avg_watch_duration", "likes", "comments", "shares"]
    result: dict[str, Any] = {}

    if {"episode_no", "total_views", "total_valid_views"}.issubset(work.columns):
        ordered = work.dropna(subset=["episode_no", "total_views", "total_valid_views"]).sort_values("episode_no")
        previous_views = ordered["total_views"].shift(1)
        previous_valid_views = ordered["total_valid_views"].shift(1)
        ordered["views_drop_rate"] = (previous_views - ordered["total_views"]) / previous_views
        ordered["valid_views_drop_rate"] = (previous_valid_views - ordered["total_valid_views"]) / previous_valid_views
        ordered = ordered[
            (previous_views > 0)
            & (previous_valid_views > 0)
            & (ordered["valid_views_drop_rate"] > 0)
        ]
        result["drop_off_ranking"] = _clean_records(ordered.sort_values("valid_views_drop_rate", ascending=False).head(10)[
            [column for column in columns + ["views_drop_rate", "valid_views_drop_rate"] if column in ordered.columns]
        ].to_dict("records"))
    else:
        result["drop_off_ranking"] = []

    total_views_median = work["total_views"].median() if "total_views" in work.columns else None
    valid_rate_median = work["valid_view_rate"].median() if "valid_view_rate" in work.columns else None
    if total_views_median is not None and valid_rate_median is not None:
        high_exposure_low_valid = work[
            (work["total_views"] >= total_views_median)
            & (work["valid_view_rate"] < valid_rate_median)
        ].copy()
        high_exposure_low_valid["reason"] = "播放量高于中位数，但有效播放率低于中位数"
        result["high_exposure_low_valid"] = _clean_records(
            high_exposure_low_valid[[column for column in columns + ["reason"] if column in high_exposure_low_valid.columns]]
            .head(10)
            .to_dict("records")
        )
    else:
        result["high_exposure_low_valid"] = []

    sample_threshold = _sample_size_threshold(work)
    if sample_threshold is not None and "total_views" in work.columns:
        eligible_work = work[work["total_views"] >= sample_threshold].copy()
    else:
        eligible_work = work.copy()

    if {"likes", "comments"}.issubset(work.columns):
        eligible_work["interaction_score"] = eligible_work["likes"].fillna(0) + eligible_work["comments"].fillna(0)
        result["high_interaction_episodes"] = _top_records(
            eligible_work[eligible_work["interaction_score"] > 0],
            "interaction_score",
            columns + ["interaction_score"],
        )
    else:
        result["high_interaction_episodes"] = []

    if "shares" in eligible_work.columns:
        result["high_share_episodes"] = _top_records(eligible_work[eligible_work["shares"] > 0], "shares", columns)
    else:
        result["high_share_episodes"] = []

    duration_median = work["avg_watch_duration"].median() if "avg_watch_duration" in work.columns else None
    if duration_median is not None:
        result["low_retention_episodes"] = _clean_records(work[
            work["avg_watch_duration"] < duration_median
        ][[column for column in columns if column in work.columns]].head(10).to_dict("records"))
    else:
        result["low_retention_episodes"] = []

    suggestions = []
    if result["high_exposure_low_valid"]:
        suggestions.append("高曝光但有效播放偏低的集数，建议复盘前30秒、标题封面预期和本集冲突推进是否匹配。")
    if result["drop_off_ranking"]:
        suggestions.append("出现相邻集数掉点时，建议复盘上一集结尾钩子和本集开场承接是否足够顺滑。")
    if result["high_interaction_episodes"] or result["high_share_episodes"]:
        suggestions.append("高互动或高分享集数可提取情绪点、反转点和话题点，作为后续剧本复盘参考。")
    if result["low_retention_episodes"]:
        suggestions.append("低停留集数可重点检查解释性段落、冲突强度和情绪补偿是否延迟。")

    result["review_suggestions"] = suggestions or ["当前分集数据未显示明显异常，建议结合文本审核结论继续人工复核。"]
    return result


def generate_market_feedback_summary(normalized_dir: str | Path) -> AnalysisResult:
    base_path = Path(normalized_dir)
    result = AnalysisResult()
    base_path.mkdir(parents=True, exist_ok=True)

    account_df = _read_csv(base_path / "account_daily_stats.csv", result.warnings)
    album_df = _read_csv(base_path / "album_daily_stats.csv", result.warnings)
    episode_df = _read_csv(base_path / "episode_stats.csv", result.warnings)
    video_df = _read_csv(base_path / "video_daily_stats.csv", result.warnings)

    episode_diagnostics = build_episode_diagnostics(episode_df)
    video_diagnostics = build_episode_diagnostics(video_df)

    summary = {
        "generated_at": pd.Timestamp.now().isoformat(),
        "account_growth_summary": build_account_summary(account_df),
        "album_performance_summary": build_album_summary(album_df),
        "episode_drop_off_ranking": episode_diagnostics["drop_off_ranking"],
        "high_exposure_low_valid_episodes": episode_diagnostics["high_exposure_low_valid"] or video_diagnostics["high_exposure_low_valid"],
        "high_interaction_episodes": episode_diagnostics["high_interaction_episodes"] or video_diagnostics["high_interaction_episodes"],
        "high_share_episodes": episode_diagnostics["high_share_episodes"] or video_diagnostics["high_share_episodes"],
        "low_retention_episodes": episode_diagnostics["low_retention_episodes"] or video_diagnostics["low_retention_episodes"],
        "script_review_suggestions": episode_diagnostics["review_suggestions"],
        "diagnostic_note": "本摘要基于均值和中位数做数据诊断，仅作为剧本复盘辅助依据，不代表因果结论。",
    }

    output_file = base_path / "market_feedback_summary.json"
    output_file.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    result.summary = summary
    result.generated_files.append(str(output_file))
    return result
