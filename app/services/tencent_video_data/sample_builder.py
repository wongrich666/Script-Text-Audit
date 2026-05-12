from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from .analyzer import extract_episode_no_from_title


SAMPLE_COLUMNS = [
    "episode_no",
    "episode_title",
    "total_views",
    "total_valid_views",
    "valid_view_rate",
    "likes",
    "comments",
    "shares",
    "is_high_exposure_low_valid",
    "is_drop_off_episode",
    "is_high_interaction",
    "is_high_share",
    "script_text",
]


@dataclass
class SampleBuildResult:
    generated_files: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _read_summary(path: Path, warnings: list[str]) -> dict[str, Any]:
    if not path.exists():
        warnings.append(f"{path.name}: 文件不存在，样本标签将全部为 false。")
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        warnings.append(f"{path.name}: 读取失败，样本标签将全部为 false。原因：{exc}")
        return {}
    return data if isinstance(data, dict) else {}


def _normalize_episode_no(value: Any, title: Any = None) -> int | None:
    if value not in (None, "") and not pd.isna(value):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            pass
    return extract_episode_no_from_title(title)


def _episode_no_set(items: Any) -> set[int]:
    if not isinstance(items, list):
        return set()

    episode_numbers: set[int] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        episode_no = _normalize_episode_no(item.get("episode_no"), item.get("title"))
        if episode_no is not None:
            episode_numbers.add(episode_no)
    return episode_numbers


def _prepare_episode_stats(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    if "episode_no" not in work.columns:
        work["episode_no"] = pd.NA
    if "title" not in work.columns:
        work["title"] = ""

    work["episode_no"] = [
        _normalize_episode_no(episode_no, title)
        for episode_no, title in zip(work["episode_no"], work["title"])
    ]

    for field in [
        "total_views",
        "total_valid_views",
        "valid_view_rate",
        "likes",
        "comments",
        "shares",
    ]:
        if field not in work.columns:
            work[field] = pd.NA
        work[field] = pd.to_numeric(work[field], errors="coerce")

    return work


def build_episode_samples(normalized_dir: str | Path) -> SampleBuildResult:
    base_path = Path(normalized_dir)
    result = SampleBuildResult()
    episode_stats_path = base_path / "episode_stats.csv"
    summary_path = base_path / "market_feedback_summary.json"
    output_path = base_path / "episode_samples.csv"

    base_path.mkdir(parents=True, exist_ok=True)

    if not episode_stats_path.exists():
        result.warnings.append(f"{episode_stats_path.name}: 文件不存在，无法生成 episode_samples.csv。")
        return result

    try:
        episode_stats = pd.read_csv(episode_stats_path)
    except Exception as exc:
        result.warnings.append(f"{episode_stats_path.name}: 读取失败，无法生成 episode_samples.csv。原因：{exc}")
        return result

    summary = _read_summary(summary_path, result.warnings)
    high_exposure_low_valid_set = _episode_no_set(summary.get("high_exposure_low_valid_episodes"))
    drop_off_set = _episode_no_set(summary.get("episode_drop_off_ranking"))
    high_interaction_set = _episode_no_set(summary.get("high_interaction_episodes"))
    high_share_set = _episode_no_set(summary.get("high_share_episodes"))

    work = _prepare_episode_stats(episode_stats)
    samples = pd.DataFrame(
        {
            "episode_no": work["episode_no"],
            "episode_title": work["title"].fillna("").astype(str),
            "total_views": work["total_views"],
            "total_valid_views": work["total_valid_views"],
            "valid_view_rate": work["valid_view_rate"],
            "likes": work["likes"],
            "comments": work["comments"],
            "shares": work["shares"],
            "is_high_exposure_low_valid": work["episode_no"].map(lambda value: value in high_exposure_low_valid_set),
            "is_drop_off_episode": work["episode_no"].map(lambda value: value in drop_off_set),
            "is_high_interaction": work["episode_no"].map(lambda value: value in high_interaction_set),
            "is_high_share": work["episode_no"].map(lambda value: value in high_share_set),
            "script_text": "",
        },
        columns=SAMPLE_COLUMNS,
    )

    if not samples.empty:
        samples = samples.dropna(subset=["episode_no"]).copy()
        samples["episode_no"] = samples["episode_no"].astype(int)

    samples.to_csv(output_path, index=False, encoding="utf-8-sig")
    result.generated_files.append(str(output_path))
    return result
