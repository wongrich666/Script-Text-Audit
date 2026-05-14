from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_NORMALIZED_DIR = PROJECT_ROOT / "data" / "tencent_video_normalized"
DEFAULT_MAPPING_FILES = [
    "video_script_mapping.csv",
    "video_script_mapping_xiaoyinu.csv",
]

MAPPING_COLUMNS = [
    "video_title",
    "episode_no",
    "script_file",
    "script_episode_title",
    "source_project",
    "note",
]

OUTPUT_COLUMNS = [
    "source_project",
    "video_title",
    "episode_no",
    "script_episode_title",
    "script_file",
    "has_script_text",
    "script_text",
    "script_length",
    "line_count",
    "dialogue_line_count",
    "action_line_count",
    "date_start",
    "date_end",
    "total_views_latest",
    "total_valid_views_latest",
    "valid_view_rate_latest",
    "valid_view_rate_median",
    "avg_watch_duration_latest",
    "avg_watch_duration_rate_latest",
    "avg_watch_duration_rate_median",
    "likes_latest",
    "comments_latest",
    "shares_latest",
    "interaction_latest",
    "is_high_valid_view_rate",
    "is_low_valid_view_rate",
    "is_high_interaction",
    "is_low_retention",
    "hook_text",
    "ending_text",
    "note",
]

RAW_SCRIPT_FILENAMES = {"冥府审计师.txt", "小医奴.txt"}
TEXT_ENCODINGS = ["utf-8-sig", "utf-8", "gb18030"]
PROJECT_ALIASES = {
    "冥府审计师": "冥府审计师",
    "SJS": "冥府审计师",
    "小医奴": "小医奴",
    "Сҽū": "小医奴",
}
CHINESE_DIGITS = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}


@dataclass
class ModelingDatasetResult:
    mapping_files_read: list[str] = field(default_factory=list)
    generated_files: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    original_mapping_rows: int = 0
    auto_completed_mapping_rows: int = 0
    mapping_rows: int = 0
    video_title_count: int = 0
    dataset_rows: int = 0
    source_project_counts: dict[str, int] = field(default_factory=dict)
    missing_script_titles: list[str] = field(default_factory=list)
    missing_playback_titles: list[str] = field(default_factory=list)


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, keep_default_na=False)


def _nonempty_count(row: pd.Series) -> int:
    return sum(1 for value in row if str(value).strip())


def parse_chinese_episode_number(text: str) -> int | None:
    text = text.strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    if text in CHINESE_DIGITS:
        return CHINESE_DIGITS[text]
    if text == "十":
        return 10
    if text.startswith("十"):
        tail = text[1:]
        return 10 + CHINESE_DIGITS.get(tail, 0)
    if "十" in text:
        head, tail = text.split("十", 1)
        head_number = CHINESE_DIGITS.get(head)
        if head_number is None:
            return None
        return head_number * 10 + CHINESE_DIGITS.get(tail, 0)
    return None


def infer_project_episode(video_title: str) -> tuple[str, int] | None:
    title = str(video_title or "").strip()
    if not title:
        return None

    sjs_match = re.fullmatch(r"SJS[_-]?(\d{1,2})", title, flags=re.IGNORECASE)
    if sjs_match:
        return "冥府审计师", int(sjs_match.group(1))

    xiaoyinu_match = re.fullmatch(r"(?:小医奴|Сҽū)_?(\d{1,2})", title)
    if xiaoyinu_match:
        return "小医奴", int(xiaoyinu_match.group(1))

    xiaoyinu_episode_match = re.fullmatch(r"小医奴第([零〇一二两三四五六七八九十\d]{1,3})集", title)
    if xiaoyinu_episode_match:
        episode_no = parse_chinese_episode_number(xiaoyinu_episode_match.group(1))
        if episode_no is not None:
            return "小医奴", episode_no

    return None


def canonical_video_title(video_title: str) -> str:
    title = str(video_title or "").strip()
    inferred = infer_project_episode(title)
    if inferred is None:
        return title
    source_project, episode_no = inferred
    if source_project == "冥府审计师":
        return f"SJS_{episode_no:02d}"
    if source_project == "小医奴":
        return f"小医奴{episode_no:02d}"
    return title


def _script_file_from_path(path: Path, normalized_dir: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        pass
    try:
        return path.resolve().relative_to(normalized_dir.resolve()).as_posix()
    except ValueError:
        return str(path)


def _existing_script_path(relative_path: str, normalized_dir: Path) -> Path | None:
    path = _resolve_script_path(relative_path, normalized_dir)
    return path if path.exists() else None


def find_local_script_file(source_project: str, episode_no: int, normalized_dir: Path) -> str:
    episode = f"{episode_no:02d}"
    candidate_paths: list[Path] = []
    if source_project == "冥府审计师":
        candidate_paths.append(normalized_dir / "episode_scripts" / f"SJS_{episode}.txt")
        candidate_paths.extend(sorted((normalized_dir / "episode_scripts_split" / "冥府审计师").glob(f"第{episode}集_*.txt")))
        candidate_paths.append(PROJECT_ROOT / "data" / "episode_scripts" / f"SJS_{episode}.txt")
        candidate_paths.extend(
            sorted((PROJECT_ROOT / "data" / "episode_scripts_split" / "冥府审计师").glob(f"第{episode}集_*.txt"))
        )
    elif source_project == "小医奴":
        candidate_paths.append(normalized_dir / "episode_scripts" / "xiaoyinu" / f"小医奴_{episode}.txt")
        candidate_paths.extend(sorted((normalized_dir / "episode_scripts_split" / "小医奴").glob(f"第{episode}集_*.txt")))
        candidate_paths.append(PROJECT_ROOT / "data" / "episode_scripts" / "xiaoyinu" / f"小医奴_{episode}.txt")
        candidate_paths.extend(sorted((PROJECT_ROOT / "data" / "episode_scripts_split" / "小医奴").glob(f"第{episode}集_*.txt")))

    for path in candidate_paths:
        if path.exists() and path.name not in RAW_SCRIPT_FILENAMES:
            return _script_file_from_path(path, normalized_dir)
    return ""


def load_mapping_tables(normalized_dir: Path, result: ModelingDatasetResult) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for filename in DEFAULT_MAPPING_FILES:
        path = normalized_dir / filename
        if not path.exists():
            result.warnings.append(f"{filename}: 映射表不存在，已跳过。")
            continue
        df = _read_csv(path)
        for column in MAPPING_COLUMNS:
            if column not in df.columns:
                df[column] = ""
        frames.append(df[MAPPING_COLUMNS].copy())
        result.mapping_files_read.append(str(path))
        result.original_mapping_rows += len(df)

    if not frames:
        result.warnings.append("未读取到任何 video_script_mapping 映射表。")
        return pd.DataFrame(columns=MAPPING_COLUMNS)

    merged = pd.concat(frames, ignore_index=True)
    merged = merged.fillna("")
    for column in MAPPING_COLUMNS:
        merged[column] = merged[column].map(lambda value: str(value).strip())
    merged["video_title"] = merged["video_title"].map(canonical_video_title)

    merged["_nonempty_count"] = merged[MAPPING_COLUMNS].apply(_nonempty_count, axis=1)
    merged["_row_order"] = range(len(merged))
    merged = merged.sort_values(["source_project", "video_title", "_nonempty_count", "_row_order"])
    merged = merged.drop_duplicates(["source_project", "video_title"], keep="last")
    merged = merged.sort_values(["source_project", "episode_no", "video_title"], kind="stable")
    return merged[MAPPING_COLUMNS].reset_index(drop=True)


def write_mapping_all(mapping: pd.DataFrame, normalized_dir: Path, result: ModelingDatasetResult) -> Path:
    output_file = normalized_dir / "video_script_mapping_all.csv"
    normalized_dir.mkdir(parents=True, exist_ok=True)
    mapping.to_csv(output_file, index=False, encoding="utf-8-sig")
    result.generated_files.append(str(output_file))
    result.mapping_rows = len(mapping)
    return output_file


def _to_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def aggregate_video_trends(normalized_dir: Path, result: ModelingDatasetResult) -> pd.DataFrame:
    trend_path = normalized_dir / "video_trend_daily_stats.csv"
    if not trend_path.exists():
        result.warnings.append("video_trend_daily_stats.csv: 文件不存在，无法聚合播放数据。")
        return pd.DataFrame(columns=["video_title"])

    trends = _read_csv(trend_path)
    if "video_title" not in trends.columns:
        result.warnings.append("video_trend_daily_stats.csv: 缺少 video_title 字段。")
        return pd.DataFrame(columns=["video_title"])

    trends = trends.copy()
    trends["video_title"] = trends["video_title"].map(lambda value: canonical_video_title(str(value).strip()))
    trends = trends[trends["video_title"] != ""].copy()
    result.video_title_count = int(trends["video_title"].nunique())
    trends["_row_order"] = range(len(trends))

    numeric_fields = [
        "total_views",
        "total_valid_views",
        "valid_view_rate",
        "avg_watch_duration",
        "avg_watch_duration_rate",
        "likes",
        "comments",
        "shares",
    ]
    for field_name in numeric_fields:
        if field_name not in trends.columns:
            trends[field_name] = pd.NA
        trends[field_name] = _to_numeric(trends[field_name])

    if "date" not in trends.columns:
        trends["date"] = ""
    trends["_date"] = pd.to_datetime(trends["date"], errors="coerce", format="mixed")

    rows: list[dict[str, Any]] = []
    for video_title, group in trends.groupby("video_title", sort=False):
        valid_dates = group["_date"].dropna()
        if valid_dates.empty or group["_date"].isna().any():
            result.warnings.append(f"{video_title}: date 解析失败或存在空值，已按原始行顺序取最后一行。")
            latest = group.sort_values("_row_order").iloc[-1]
        else:
            latest = group.sort_values(["_date", "_row_order"]).iloc[-1]

        likes_latest = latest.get("likes")
        comments_latest = latest.get("comments")
        shares_latest = latest.get("shares")
        interaction_latest = sum(
            value for value in [likes_latest, comments_latest, shares_latest] if pd.notna(value)
        )

        rows.append(
            {
                "video_title": video_title,
                "date_start": valid_dates.min().strftime("%Y-%m-%d") if not valid_dates.empty else "",
                "date_end": valid_dates.max().strftime("%Y-%m-%d") if not valid_dates.empty else "",
                "total_views_latest": latest.get("total_views"),
                "total_valid_views_latest": latest.get("total_valid_views"),
                "valid_view_rate_latest": latest.get("valid_view_rate"),
                "valid_view_rate_median": group["valid_view_rate"].median(),
                "avg_watch_duration_latest": latest.get("avg_watch_duration"),
                "avg_watch_duration_rate_latest": latest.get("avg_watch_duration_rate"),
                "avg_watch_duration_rate_median": group["avg_watch_duration_rate"].median(),
                "likes_latest": likes_latest,
                "comments_latest": comments_latest,
                "shares_latest": shares_latest,
                "interaction_latest": interaction_latest,
            }
        )

    return pd.DataFrame(rows)


def _script_episode_title_from_file(script_file: str, source_project: str, episode_no: int) -> str:
    path = Path(script_file)
    name = path.stem
    match = re.match(rf"第{episode_no:02d}集_(.+)", name)
    if match:
        return match.group(1).strip()
    return f"{source_project} 第{episode_no}集"


def auto_complete_mapping_from_trends(
    mapping: pd.DataFrame,
    trend_agg: pd.DataFrame,
    normalized_dir: Path,
    result: ModelingDatasetResult,
) -> pd.DataFrame:
    if "video_title" not in trend_agg.columns:
        return mapping

    existing_titles = set(mapping["video_title"].map(canonical_video_title)) if "video_title" in mapping.columns else set()
    auto_rows: list[dict[str, Any]] = []
    for video_title in trend_agg["video_title"].dropna().map(canonical_video_title).drop_duplicates():
        if not str(video_title).strip() or video_title in existing_titles:
            continue
        inferred = infer_project_episode(video_title)
        if inferred is None:
            result.warnings.append(f"{video_title}: 无法自动推断项目和集数，已标记为未映射。")
            auto_rows.append(
                {
                    "video_title": video_title,
                    "episode_no": "",
                    "script_file": "",
                    "script_episode_title": "",
                    "source_project": "未映射",
                    "note": "missing_script_file_after_auto_completion",
                }
            )
            continue

        source_project, episode_no = inferred
        script_file = find_local_script_file(source_project, episode_no, normalized_dir)
        note = "auto_completed_from_local_script" if script_file else "missing_script_file_after_auto_completion"
        if not script_file:
            result.warnings.append(f"{video_title}: 自动补全映射时未找到本地单集剧本文本。")
        auto_rows.append(
            {
                "video_title": video_title,
                "episode_no": episode_no,
                "script_file": script_file,
                "script_episode_title": _script_episode_title_from_file(script_file, source_project, episode_no),
                "source_project": source_project,
                "note": note,
            }
        )

    if not auto_rows:
        result.auto_completed_mapping_rows = 0
        return mapping

    result.auto_completed_mapping_rows = len(auto_rows)
    completed = pd.concat([mapping, pd.DataFrame(auto_rows, columns=MAPPING_COLUMNS)], ignore_index=True)
    completed["_nonempty_count"] = completed[MAPPING_COLUMNS].apply(_nonempty_count, axis=1)
    completed["_row_order"] = range(len(completed))
    completed = completed.sort_values(["source_project", "video_title", "_nonempty_count", "_row_order"])
    completed = completed.drop_duplicates(["source_project", "video_title"], keep="last")
    completed = completed.sort_values(["source_project", "episode_no", "video_title"], kind="stable")
    return completed[MAPPING_COLUMNS].reset_index(drop=True)


def _resolve_script_path(script_file: str, normalized_dir: Path) -> Path:
    path = Path(script_file)
    if path.is_absolute():
        return path
    project_path = PROJECT_ROOT / path
    if project_path.exists():
        return project_path
    return normalized_dir / path


def read_text_with_fallback(path: Path) -> str:
    for encoding in TEXT_ENCODINGS:
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding=TEXT_ENCODINGS[-1], errors="ignore")


def build_text_features(script_file: str, video_title: str, normalized_dir: Path, warnings: list[str]) -> dict[str, Any]:
    script_file = str(script_file or "").strip()
    empty_features = {
        "has_script_text": False,
        "script_text": "",
        "script_length": 0,
        "line_count": 0,
        "dialogue_line_count": 0,
        "action_line_count": 0,
        "hook_text": "",
        "ending_text": "",
    }
    if not script_file:
        warnings.append(f"{video_title}: script_file 为空，缺少剧本文本。")
        return empty_features

    script_path = _resolve_script_path(script_file, normalized_dir)
    if script_path.name in RAW_SCRIPT_FILENAMES:
        warnings.append(f"{video_title}: script_file 指向原始总文本 {script_path.name}，已跳过。")
        return empty_features
    if not script_path.exists():
        warnings.append(f"{video_title}: script_file 不存在：{script_file}")
        return empty_features

    text = read_text_with_fallback(script_path).strip()
    if not text:
        warnings.append(f"{video_title}: script_file 文本为空：{script_file}")
        return empty_features

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return {
        "has_script_text": True,
        "script_text": text,
        "script_length": len(text),
        "line_count": len(lines),
        "dialogue_line_count": sum(1 for line in lines if "：" in line or ":" in line),
        "action_line_count": sum(1 for line in lines if line.startswith("△")),
        "hook_text": text[:300],
        "ending_text": text[-300:],
    }


def add_text_features(dataset: pd.DataFrame, normalized_dir: Path, result: ModelingDatasetResult) -> pd.DataFrame:
    if dataset.empty:
        for column in ["has_script_text", "script_text", "script_length", "line_count", "dialogue_line_count", "action_line_count", "hook_text", "ending_text"]:
            dataset[column] = []
        return dataset

    features = [
        build_text_features(row.get("script_file", ""), row.get("video_title", ""), normalized_dir, result.warnings)
        for _, row in dataset.iterrows()
    ]
    feature_df = pd.DataFrame(features)
    return pd.concat([dataset.reset_index(drop=True), feature_df], axis=1)


def add_labels(dataset: pd.DataFrame) -> pd.DataFrame:
    label_specs = [
        ("valid_view_rate_median", "is_high_valid_view_rate", "is_low_valid_view_rate"),
        ("interaction_latest", "is_high_interaction", None),
        ("avg_watch_duration_rate_median", None, "is_low_retention"),
    ]
    for value_column, high_column, low_column in label_specs:
        if value_column in dataset.columns:
            values = pd.to_numeric(dataset[value_column], errors="coerce")
        else:
            values = pd.Series([pd.NA] * len(dataset))
        median = values.dropna().median()
        if high_column:
            dataset[high_column] = values > median if pd.notna(median) else False
        if low_column:
            dataset[low_column] = values < median if pd.notna(median) else False
    return dataset


def build_modeling_episode_dataset(normalized_dir: str | Path = DEFAULT_NORMALIZED_DIR) -> ModelingDatasetResult:
    normalized_path = Path(normalized_dir)
    result = ModelingDatasetResult()

    mapping = load_mapping_tables(normalized_path, result)
    trend_agg = aggregate_video_trends(normalized_path, result)
    mapping = auto_complete_mapping_from_trends(mapping, trend_agg, normalized_path, result)
    write_mapping_all(mapping, normalized_path, result)

    dataset = mapping.merge(trend_agg, on="video_title", how="outer")
    for column in MAPPING_COLUMNS:
        if column not in dataset.columns:
            dataset[column] = ""
    dataset[MAPPING_COLUMNS] = dataset[MAPPING_COLUMNS].fillna("")
    dataset["video_title"] = dataset["video_title"].map(canonical_video_title)
    dataset["source_project"] = dataset["source_project"].replace("", "未映射").fillna("未映射")
    dataset["note"] = dataset["note"].where(
        dataset["note"].astype(str).str.strip() != "",
        "missing_script_file_after_auto_completion",
    )

    dataset = add_text_features(dataset, normalized_path, result)
    dataset = add_labels(dataset)

    for column in OUTPUT_COLUMNS:
        if column not in dataset.columns:
            dataset[column] = False if column.startswith("is_") or column == "has_script_text" else ""
    dataset = dataset[OUTPUT_COLUMNS].copy()

    output_file = normalized_path / "modeling_episode_dataset.csv"
    dataset.to_csv(output_file, index=False, encoding="utf-8-sig")
    result.generated_files.append(str(output_file))
    result.dataset_rows = len(dataset)
    if "source_project" in dataset.columns:
        result.source_project_counts = {
            str(project or "未映射"): int(count)
            for project, count in dataset["source_project"].fillna("").replace("", "未映射").value_counts().items()
        }
    result.missing_script_titles = sorted(
        str(title)
        for title in dataset.loc[~dataset["has_script_text"].astype(bool), "video_title"].fillna("")
        if str(title).strip()
    )
    trend_titles = set(trend_agg["video_title"].astype(str)) if "video_title" in trend_agg.columns else set()
    result.missing_playback_titles = sorted(
        str(title)
        for title in mapping["video_title"].astype(str)
        if str(title).strip() and str(title) not in trend_titles
    )
    return result


def print_result(result: ModelingDatasetResult) -> None:
    print("建模数据集生成完成。")
    print(f"读取了几个映射表：{len(result.mapping_files_read)}")
    for path in result.mapping_files_read:
        print(f"- {path}")
    print(f"原始映射表行数：{result.original_mapping_rows}")
    print(f"自动补全映射行数：{result.auto_completed_mapping_rows}")
    print(f"统一映射表行数：{result.mapping_rows}")
    print(f"video_trend_daily_stats.csv 中 video_title 数量：{result.video_title_count}")
    print(f"modeling_episode_dataset.csv 行数：{result.dataset_rows}")
    print("每个 source_project 的样本数：")
    if result.source_project_counts:
        for project, count in result.source_project_counts.items():
            print(f"- {project}: {count}")
    else:
        print("- 无")
    print("缺少剧本文本的 video_title：")
    if result.missing_script_titles:
        for title in result.missing_script_titles:
            print(f"- {title}")
    else:
        print("- 无")
    print("缺少播放数据的 video_title：")
    if result.missing_playback_titles:
        for title in result.missing_playback_titles:
            print(f"- {title}")
    else:
        print("- 无")
    print("Warnings：")
    if result.warnings:
        for warning in result.warnings:
            print(f"- {warning}")
    else:
        print("- 无")


def main() -> None:
    parser = argparse.ArgumentParser(description="生成腾讯视频多项目逐集建模数据集。")
    parser.add_argument(
        "--normalized-dir",
        default=str(DEFAULT_NORMALIZED_DIR),
        help="腾讯视频标准化 CSV 目录",
    )
    args = parser.parse_args()

    result = build_modeling_episode_dataset(args.normalized_dir)
    print_result(result)


if __name__ == "__main__":
    main()
