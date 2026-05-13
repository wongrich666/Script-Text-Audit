from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd


FIELD_MAPPING = {
    "时间": "date",
    "标题": "title",
    "集数": "episode_no",
    "总播放量": "total_views",
    "总有效播放量": "total_valid_views",
    "有效播放量占比": "valid_view_rate",
    "总播放时长": "total_watch_time",
    "单次播放时长": "avg_watch_duration",
    "单次播放时长占比": "avg_watch_duration_rate",
    "粉丝数": "followers",
    "总在追数": "total_subscribers",
    "专辑在追数": "album_subscribers",
    "点赞": "likes",
    "总点赞": "likes",
    "评论": "comments",
    "总评论": "comments",
    "分享": "shares",
    "总分享": "shares",
}

PERCENT_FIELDS = {"valid_view_rate", "avg_watch_duration_rate"}
NUMERIC_FIELDS = {
    "episode_no",
    "total_views",
    "total_valid_views",
    "valid_view_rate",
    "total_watch_time",
    "avg_watch_duration",
    "avg_watch_duration_rate",
    "followers",
    "total_subscribers",
    "album_subscribers",
    "likes",
    "comments",
    "shares",
}

VIDEO_TREND_DAILY_FIELDS = [
    "video_title",
    "source_file",
    "date",
    "total_views",
    "total_valid_views",
    "valid_view_rate",
    "avg_watch_duration",
    "avg_watch_duration_rate",
    "likes",
    "comments",
    "shares",
]

ALBUM_TREND_DAILY_FIELDS = [
    "title",
    "source_file",
    "date",
    "total_views",
    "total_valid_views",
    "valid_view_rate",
    "total_watch_time",
    "avg_watch_duration",
    "avg_watch_duration_rate",
    "total_subscribers",
    "album_subscribers",
    "likes",
    "comments",
    "shares",
]

INVALID_ALBUM_TITLES = {
    "",
    "当前",
    "已经到底啦",
    "查看数据汇总",
    "切换专辑",
    "专辑切换",
}

FILE_SPECS = {
    "account": {
        "pattern": re.compile(r"^账号趋势数据-.*\.xlsx$", re.IGNORECASE),
        "output": "account_daily_stats.csv",
        "expected_fields": [
            "date",
            "followers",
            "total_views",
            "total_valid_views",
            "valid_view_rate",
            "total_watch_time",
            "avg_watch_duration",
            "avg_watch_duration_rate",
            "likes",
            "comments",
            "shares",
        ],
    },
    "album": {
        "pattern": re.compile(r"^专辑趋势数据-.*\.xlsx$", re.IGNORECASE),
        "output": "album_daily_stats.csv",
        "expected_fields": [
            "date",
            "title",
            "total_views",
            "total_valid_views",
            "valid_view_rate",
            "total_watch_time",
            "avg_watch_duration",
            "avg_watch_duration_rate",
            "total_subscribers",
            "album_subscribers",
            "likes",
            "comments",
            "shares",
        ],
    },
    "episode": {
        "pattern": re.compile(r"^剧集趋势数据-.*\.xlsx$", re.IGNORECASE),
        "output": "episode_stats.csv",
        "expected_fields": [
            "title",
            "episode_no",
            "total_views",
            "total_valid_views",
            "valid_view_rate",
            "total_watch_time",
            "avg_watch_duration",
            "avg_watch_duration_rate",
            "likes",
            "comments",
            "shares",
        ],
    },
    "video": {
        "pattern": re.compile(r"^视频趋势数据-.*\.xlsx$", re.IGNORECASE),
        "output": "video_daily_stats.csv",
        "expected_fields": [
            "date",
            "title",
            "episode_no",
            "total_views",
            "total_valid_views",
            "valid_view_rate",
            "total_watch_time",
            "avg_watch_duration",
            "avg_watch_duration_rate",
            "likes",
            "comments",
            "shares",
        ],
    },
}


@dataclass
class ImportResult:
    read_excels: list[str] = field(default_factory=list)
    generated_files: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def identify_file_type(path: Path) -> str | None:
    for file_type, spec in FILE_SPECS.items():
        if spec["pattern"].match(path.name):
            return file_type
    return None


def _series_all_blank(series: pd.Series) -> bool:
    if series.empty:
        return True
    return series.isna().all() or series.map(lambda value: str(value).strip() == "").all()


def extract_video_title_from_trend_filename(path: Path) -> str | None:
    match = re.match(r"^视频趋势数据-(.+)-\d{8}-\d{6}\.xlsx$", path.name, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip() or None
    return None


def extract_album_title_from_trend_filename(path: Path) -> str:
    """
    兼容旧的根目录专辑趋势文件名。

    例：
    专辑趋势数据-mzc003erjj7mr11-2026-05-12-16-33-09.xlsx
    -> mzc003erjj7mr11

    这个函数保留给根目录旧文件使用。
    批量下载的中文专辑文件由 extract_album_title_from_download_filename 处理。
    """
    patterns = [
        r"^专辑趋势数据-(.+)-\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}\.xlsx$",
        r"^专辑趋势数据-(.+)-\d{8}-\d{6}\.xlsx$",
    ]
    for pattern in patterns:
        match = re.match(pattern, path.name, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
    parts = path.name.split("-")
    if len(parts) > 1:
        return parts[1].strip()
    return ""


def extract_album_title_from_download_filename(path: Path) -> str:
    """
    从 Playwright 批量下载文件名中提取真实专辑名。

    支持：
    专辑数据-冥府审计师-20260513-145426.xlsx
    专辑数据-小医奴-20260513-145443.xlsx
    专辑数据-穿成宁采臣后我带崩了神仙界-20260513-145554.xlsx
    专辑数据-2026-04-09_17_22_40_创建-20260513-150036.xlsx

    注意：
    不能用 split('-')[1]，因为有些标题本身含有 '-'，比如 2026-04-09_17_22_40_创建。
    这里用正则只剥掉最末尾的下载时间戳。
    """
    patterns = [
        r"^专辑数据-(.+)-\d{8}-\d{6}\.xlsx$",
        r"^专辑趋势数据-(.+)-\d{8}-\d{6}\.xlsx$",
        r"^专辑趋势数据-(.+)-\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}\.xlsx$",
    ]
    for pattern in patterns:
        match = re.match(pattern, path.name, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return path.stem.strip()


def parse_percent(value: Any) -> float | None:
    if pd.isna(value):
        return None

    text = str(value).strip()
    if not text:
        return None

    has_percent = text.endswith("%")
    text = text.rstrip("%").replace(",", "")
    try:
        number = float(text)
    except ValueError:
        return None

    if has_percent or abs(number) > 1:
        number = number / 100
    return number


def parse_duration_or_number(value: Any) -> float | None:
    if pd.isna(value):
        return None

    text = str(value).strip()
    if not text:
        return None

    parts = text.split(":")
    if len(parts) in (2, 3):
        try:
            numbers = [float(part) for part in parts]
        except ValueError:
            numbers = []
        if len(numbers) == 2:
            return numbers[0] * 60 + numbers[1]
        if len(numbers) == 3:
            return numbers[0] * 3600 + numbers[1] * 60 + numbers[2]

    cleaned = text.replace(",", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


def normalize_numeric(value: Any, field_name: str) -> float | int | None:
    if field_name in PERCENT_FIELDS:
        return parse_percent(value)

    parsed = parse_duration_or_number(value)
    if parsed is None:
        return None

    if field_name == "episode_no":
        return int(parsed)
    return parsed


def _normalize_columns(df: pd.DataFrame, source_name: str, warnings: list[str]) -> pd.DataFrame:
    df = df.rename(columns=lambda value: str(value).strip())
    available_mapping = {
        source: target
        for source, target in FIELD_MAPPING.items()
        if source in df.columns
    }

    known_source_columns = set(FIELD_MAPPING.keys())
    unrecognized_columns = [
        column
        for column in df.columns
        if column not in known_source_columns and not str(column).startswith("Unnamed:")
    ]
    if unrecognized_columns:
        warnings.append(f"{source_name}: 存在未映射字段 {unrecognized_columns}，已忽略。")

    normalized = df.rename(columns=available_mapping)
    if normalized.columns.duplicated().any():
        normalized = normalized.T.groupby(level=0, sort=False).first().T

    return normalized


def _ensure_expected_fields(
    normalized: pd.DataFrame,
    expected_fields: list[str],
    source_name: str,
    warnings: list[str],
) -> pd.DataFrame:
    missing_fields = [field for field in expected_fields if field not in normalized.columns]
    if missing_fields:
        warnings.append(f"{source_name}: 缺少字段 {missing_fields}，已用空值补齐。")

    for field in expected_fields:
        if field not in normalized.columns:
            normalized[field] = pd.NA

    return normalized[expected_fields].copy()


def _normalize_common_fields(normalized: pd.DataFrame) -> pd.DataFrame:
    if "date" in normalized.columns:
        normalized["date"] = pd.to_datetime(normalized["date"], errors="coerce").dt.strftime("%Y-%m-%d")

    for field in NUMERIC_FIELDS.intersection(normalized.columns):
        normalized[field] = normalized[field].map(lambda value: normalize_numeric(value, field))

    return normalized


def normalize_dataframe(df: pd.DataFrame, file_type: str, source_name: str, warnings: list[str]) -> pd.DataFrame:
    spec = FILE_SPECS[file_type]

    if df.empty:
        warnings.append(f"{source_name}: Excel 内容为空，已生成空的标准化 CSV。")

    normalized = _normalize_columns(df, source_name, warnings)

    if file_type == "album":
        if "title" not in normalized.columns or _series_all_blank(normalized["title"]):
            normalized["title"] = extract_album_title_from_trend_filename(Path(source_name))

    expected_fields = list(spec["expected_fields"])
    normalized = _ensure_expected_fields(normalized, expected_fields, source_name, warnings)
    normalized = _normalize_common_fields(normalized)
    return normalized


def normalize_video_trend_daily_dataframe(
    df: pd.DataFrame,
    excel_path: Path,
    warnings: list[str],
) -> pd.DataFrame:
    if df.empty:
        warnings.append(f"{excel_path.name}: Excel 内容为空，已生成空的视频趋势标准化记录。")

    video_title = extract_video_title_from_trend_filename(excel_path)
    if video_title is None:
        warnings.append(f"{excel_path.name}: 无法从文件名提取 video_title，已置为空。")
        video_title = ""

    normalized = _normalize_columns(df, excel_path.name, warnings)

    for field in VIDEO_TREND_DAILY_FIELDS:
        if field not in normalized.columns:
            normalized[field] = pd.NA

    normalized["video_title"] = video_title
    normalized["source_file"] = excel_path.name
    normalized = normalized[VIDEO_TREND_DAILY_FIELDS].copy()
    normalized = _normalize_common_fields(normalized)
    return normalized


def normalize_album_trend_daily_dataframe(
    df: pd.DataFrame,
    excel_path: Path,
    warnings: list[str],
) -> pd.DataFrame:
    if df.empty:
        warnings.append(f"{excel_path.name}: Excel 内容为空，已生成空的专辑趋势标准化记录。")

    album_title = extract_album_title_from_download_filename(excel_path)
    if album_title in INVALID_ALBUM_TITLES:
        raise ValueError(f"无效专辑标题：{album_title}")

    normalized = _normalize_columns(df, excel_path.name, warnings)

    for field in ALBUM_TREND_DAILY_FIELDS:
        if field not in normalized.columns:
            normalized[field] = pd.NA

    normalized["title"] = album_title
    normalized["source_file"] = excel_path.name
    normalized = normalized[ALBUM_TREND_DAILY_FIELDS].copy()
    normalized = _normalize_common_fields(normalized)
    return normalized


def import_video_trend_daily_exports(input_path: Path, output_path: Path, result: ImportResult) -> None:
    trend_dir = input_path / "video_trends"
    if not trend_dir.exists():
        return

    frames: list[pd.DataFrame] = []
    for excel_path in sorted(trend_dir.glob("*.xlsx")):
        try:
            df = pd.read_excel(excel_path, engine="openpyxl")
        except Exception as exc:
            result.warnings.append(f"{excel_path.name}: 读取失败，原因：{exc}")
            continue

        result.read_excels.append(str(excel_path))
        frames.append(normalize_video_trend_daily_dataframe(df, excel_path, result.warnings))

    if not frames:
        return

    merged = pd.concat(frames, ignore_index=True)
    output_file = output_path / "video_trend_daily_stats.csv"
    merged.to_csv(output_file, index=False, encoding="utf-8-sig")
    result.generated_files.append(str(output_file))


def import_album_trend_daily_exports(input_path: Path, output_path: Path, result: ImportResult) -> None:
    trend_dir = input_path / "album_trends"
    if not trend_dir.exists():
        return

    frames: list[pd.DataFrame] = []
    for excel_path in sorted(trend_dir.glob("*.xlsx")):
        try:
            album_title = extract_album_title_from_download_filename(excel_path)
            if album_title in INVALID_ALBUM_TITLES:
                result.warnings.append(f"{excel_path.name}: 识别为无效专辑标题“{album_title}”，已跳过。")
                continue

            df = pd.read_excel(excel_path, engine="openpyxl")
        except Exception as exc:
            result.warnings.append(f"{excel_path.name}: 读取失败，原因：{exc}")
            continue

        result.read_excels.append(str(excel_path))
        try:
            frames.append(normalize_album_trend_daily_dataframe(df, excel_path, result.warnings))
        except Exception as exc:
            result.warnings.append(f"{excel_path.name}: 标准化失败，原因：{exc}")

    if not frames:
        return

    merged = pd.concat(frames, ignore_index=True)
    output_file = output_path / "album_trend_daily_stats.csv"
    merged.to_csv(output_file, index=False, encoding="utf-8-sig")
    result.generated_files.append(str(output_file))


def import_tencent_video_exports(input_dir: str | Path, output_dir: str | Path) -> ImportResult:
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    result = ImportResult()

    output_path.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        result.warnings.append(f"输入目录不存在：{input_path}")
        return result

    grouped_frames: dict[str, list[pd.DataFrame]] = {file_type: [] for file_type in FILE_SPECS}

    for excel_path in sorted(input_path.glob("*.xlsx")):
        file_type = identify_file_type(excel_path)
        if file_type is None:
            result.warnings.append(f"{excel_path.name}: 未识别的腾讯视频 Excel 文件名，已跳过。")
            continue

        try:
            df = pd.read_excel(excel_path, engine="openpyxl")
        except Exception as exc:
            result.warnings.append(f"{excel_path.name}: 读取失败，原因：{exc}")
            continue

        result.read_excels.append(str(excel_path))
        normalized = normalize_dataframe(df, file_type, excel_path.name, result.warnings)
        grouped_frames[file_type].append(normalized)

    for file_type, frames in grouped_frames.items():
        if not frames:
            continue

        merged = pd.concat(frames, ignore_index=True)
        output_file = output_path / FILE_SPECS[file_type]["output"]
        merged.to_csv(output_file, index=False, encoding="utf-8-sig")
        result.generated_files.append(str(output_file))

    import_video_trend_daily_exports(input_path, output_path, result)
    import_album_trend_daily_exports(input_path, output_path, result)

    return result