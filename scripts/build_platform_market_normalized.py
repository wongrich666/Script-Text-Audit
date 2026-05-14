from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd


PLATFORM_TENCENT = "tencent_video"
PLATFORM_KUAISHOU = "kuaishou"


def read_csv_if_exists(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path, encoding="utf-8-sig")
    except UnicodeDecodeError:
        return pd.read_csv(path, encoding="utf-8")


def ensure_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    out = df.copy()
    for col in columns:
        if col not in out.columns:
            out[col] = ""
    return out[columns]


def write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")


def pick(df: pd.DataFrame, *names: str) -> pd.Series:
    for name in names:
        if name in df.columns:
            return df[name]
    return pd.Series([""] * len(df), index=df.index)


def normalize_number_series(s: pd.Series) -> pd.Series:
    return pd.to_numeric(
        s.astype(str).str.replace(",", "", regex=False).str.replace("%", "", regex=False),
        errors="coerce",
    )


DRAMA_CATALOG_COLUMNS = [
    "platform",
    "platform_drama_id",
    "raw_title",
    "canonical_title",
    "script_id",
    "script_title",
    "match_status",
    "match_confidence",
    "source_file",
    "source_table",
]

DRAMA_DAILY_COLUMNS = [
    "platform",
    "date",
    "platform_drama_id",
    "raw_title",
    "canonical_title",
    "script_id",
    "script_title",
    "match_status",
    "match_confidence",
    "play_count",
    "valid_play_count",
    "complete_play_count",
    "completion_rate",
    "like_count",
    "comment_count",
    "favorite_count",
    "share_count",
    "paid_users",
    "paid_orders",
    "paid_amount",
    "ad_spend",
    "roi",
    "source_file",
    "source_table",
]

EPISODE_DAILY_COLUMNS = [
    "platform",
    "date",
    "platform_drama_id",
    "platform_episode_id",
    "platform_video_id",
    "video_title",
    "raw_title",
    "canonical_title",
    "script_id",
    "script_title",
    "source_project",
    "episode_no",
    "match_status",
    "match_confidence",
    "play_count",
    "valid_play_count",
    "valid_view_rate",
    "avg_watch_duration",
    "avg_watch_duration_rate",
    "like_count",
    "comment_count",
    "favorite_count",
    "share_count",
    "source_file",
    "source_table",
]

AD_ACCOUNT_DAILY_COLUMNS = [
    "platform",
    "date",
    "ad_account_id",
    "ad_account_name",
    "extracted_title",
    "script_id",
    "script_title",
    "match_status",
    "match_confidence",
    "impressions",
    "spend",
    "valid_play_count",
    "complete_play_count",
    "completion_rate",
    "like_count",
    "comment_count",
    "share_count",
    "iaa_ltv",
    "iaa_roi",
    "source_file",
    "source_table",
]

OVERALL_DAILY_COLUMNS = [
    "platform",
    "date",
    "play_count",
    "valid_play_count",
    "like_count",
    "comment_count",
    "favorite_count",
    "share_count",
    "paid_users",
    "paid_orders",
    "paid_amount",
    "ad_spend",
    "global_roi",
    "commercial_roi",
    "iaa_ltv",
    "iaa_roi",
    "source_file",
    "source_table",
]

MAPPING_COLUMNS = [
    "platform",
    "platform_drama_id",
    "platform_video_id",
    "video_title",
    "raw_title",
    "canonical_title",
    "source_project",
    "episode_no",
    "script_id",
    "script_title",
    "script_file",
    "match_status",
    "match_confidence",
    "note",
    "source_table",
]


def build_kuaishou_drama_catalog(kuaishou_dir: Path) -> pd.DataFrame:
    df = read_csv_if_exists(kuaishou_dir / "kuaishou_drama_catalog.csv")
    if df.empty:
        return pd.DataFrame(columns=DRAMA_CATALOG_COLUMNS)

    out = pd.DataFrame(index=df.index)
    out["platform"] = PLATFORM_KUAISHOU
    out["platform_drama_id"] = pick(df, "platform_drama_id")
    out["raw_title"] = pick(df, "raw_title")
    out["canonical_title"] = pick(df, "canonical_title", "raw_title")
    out["script_id"] = pick(df, "script_id")
    out["script_title"] = pick(df, "script_title")
    out["match_status"] = pick(df, "match_status")
    out["match_confidence"] = pick(df, "match_confidence")
    out["source_file"] = pick(df, "source_file")
    out["source_table"] = "kuaishou_drama_catalog.csv"
    return ensure_columns(out, DRAMA_CATALOG_COLUMNS)


def build_kuaishou_drama_daily(kuaishou_dir: Path) -> pd.DataFrame:
    df = read_csv_if_exists(kuaishou_dir / "kuaishou_drama_daily_stats.csv")
    if df.empty:
        return pd.DataFrame(columns=DRAMA_DAILY_COLUMNS)

    out = pd.DataFrame(index=df.index)
    out["platform"] = PLATFORM_KUAISHOU
    out["date"] = pick(df, "date")
    out["platform_drama_id"] = pick(df, "platform_drama_id")
    out["raw_title"] = pick(df, "raw_title")
    out["canonical_title"] = pick(df, "canonical_title", "raw_title")
    out["script_id"] = pick(df, "script_id")
    out["script_title"] = pick(df, "script_title")
    out["match_status"] = pick(df, "match_status")
    out["match_confidence"] = pick(df, "match_confidence")
    out["play_count"] = pick(df, "play_count")
    out["valid_play_count"] = pick(df, "valid_play_count")
    out["complete_play_count"] = pick(df, "complete_play_count")
    out["completion_rate"] = pick(df, "completion_rate")
    out["like_count"] = pick(df, "like_count")
    out["comment_count"] = pick(df, "comment_count")
    out["favorite_count"] = pick(df, "favorite_count")
    out["share_count"] = pick(df, "share_count")
    out["paid_users"] = pick(df, "paid_users")
    out["paid_orders"] = pick(df, "paid_orders")
    out["paid_amount"] = pick(df, "paid_amount")
    out["ad_spend"] = pick(df, "ad_spend")
    out["roi"] = pick(df, "roi")
    out["source_file"] = pick(df, "source_file")
    out["source_table"] = "kuaishou_drama_daily_stats.csv"
    return ensure_columns(out, DRAMA_DAILY_COLUMNS)


def build_kuaishou_ad_daily(kuaishou_dir: Path) -> pd.DataFrame:
    df = read_csv_if_exists(kuaishou_dir / "kuaishou_ad_account_daily_stats.csv")
    if df.empty:
        return pd.DataFrame(columns=AD_ACCOUNT_DAILY_COLUMNS)

    out = pd.DataFrame(index=df.index)
    out["platform"] = PLATFORM_KUAISHOU
    out["date"] = pick(df, "date")
    out["ad_account_id"] = pick(df, "ad_account_id")
    out["ad_account_name"] = pick(df, "ad_account_name")
    out["extracted_title"] = pick(df, "extracted_title")
    out["script_id"] = pick(df, "script_id")
    out["script_title"] = pick(df, "script_title")
    out["match_status"] = pick(df, "match_status")
    out["match_confidence"] = pick(df, "match_confidence")
    out["impressions"] = pick(df, "impressions")
    out["spend"] = pick(df, "spend")
    out["valid_play_count"] = pick(df, "valid_play_count")
    out["complete_play_count"] = pick(df, "complete_play_count")
    out["completion_rate"] = pick(df, "completion_rate")
    out["like_count"] = pick(df, "like_count")
    out["comment_count"] = pick(df, "comment_count")
    out["share_count"] = pick(df, "share_count")
    out["iaa_ltv"] = pick(df, "iaa_ltv")
    out["iaa_roi"] = pick(df, "iaa_roi")
    out["source_file"] = pick(df, "source_file")
    out["source_table"] = "kuaishou_ad_account_daily_stats.csv"
    return ensure_columns(out, AD_ACCOUNT_DAILY_COLUMNS)


def build_kuaishou_overall_daily(kuaishou_dir: Path) -> pd.DataFrame:
    df = read_csv_if_exists(kuaishou_dir / "kuaishou_overall_daily_stats.csv")
    if df.empty:
        return pd.DataFrame(columns=OVERALL_DAILY_COLUMNS)

    out = pd.DataFrame(index=df.index)
    out["platform"] = PLATFORM_KUAISHOU
    out["date"] = pick(df, "date")
    out["play_count"] = pick(df, "play_count")
    out["valid_play_count"] = pick(df, "valid_play_count")
    out["like_count"] = pick(df, "like_count")
    out["comment_count"] = pick(df, "comment_count")
    out["favorite_count"] = pick(df, "favorite_count")
    out["share_count"] = pick(df, "share_count")
    out["paid_users"] = pick(df, "paid_users")
    out["paid_orders"] = pick(df, "paid_orders")
    out["paid_amount"] = pick(df, "paid_amount")
    out["ad_spend"] = pick(df, "ad_spend")
    out["global_roi"] = pick(df, "global_roi")
    out["commercial_roi"] = pick(df, "commercial_roi")
    out["iaa_ltv"] = pick(df, "iaa_ltv_with_rebate", "iaa_ltv_without_rebate")
    out["iaa_roi"] = pick(df, "iaa_roi_with_rebate", "iaa_roi_without_rebate")
    out["source_file"] = pick(df, "source_file")
    out["source_table"] = "kuaishou_overall_daily_stats.csv"
    return ensure_columns(out, OVERALL_DAILY_COLUMNS)


def build_tencent_episode_daily(tencent_dir: Path) -> pd.DataFrame:
    df = read_csv_if_exists(tencent_dir / "video_trend_daily_stats.csv")
    mapping = read_csv_if_exists(tencent_dir / "video_script_mapping_all.csv")

    if df.empty:
        return pd.DataFrame(columns=EPISODE_DAILY_COLUMNS)

    merged = df.copy()
    if not mapping.empty and "video_title" in mapping.columns:
        keep_cols = [
            c for c in [
                "video_title",
                "source_project",
                "episode_no",
                "script_file",
                "script_episode_title",
                "note",
            ]
            if c in mapping.columns
        ]
        mapping_small = mapping[keep_cols].drop_duplicates(subset=["video_title"], keep="last")
        merged = merged.merge(mapping_small, on="video_title", how="left")

    out = pd.DataFrame(index=merged.index)
    out["platform"] = PLATFORM_TENCENT
    out["date"] = pick(merged, "date")
    out["platform_drama_id"] = pick(merged, "album_id", "platform_drama_id")
    out["platform_episode_id"] = pick(merged, "episode_id", "platform_episode_id")
    out["platform_video_id"] = pick(merged, "video_id", "vid", "platform_video_id")
    out["video_title"] = pick(merged, "video_title")
    out["raw_title"] = pick(merged, "video_title")
    out["canonical_title"] = pick(merged, "script_episode_title", "video_title")
    out["script_id"] = ""
    out["script_title"] = pick(merged, "source_project")
    out["source_project"] = pick(merged, "source_project").fillna("未映射")
    out["episode_no"] = pick(merged, "episode_no")
    out["match_status"] = out["source_project"].apply(lambda x: "matched" if str(x) and str(x) != "未映射" else "unmatched")
    out["match_confidence"] = out["match_status"].apply(lambda x: 1.0 if x == "matched" else "")
    out["play_count"] = pick(merged, "total_views", "play_count")
    out["valid_play_count"] = pick(merged, "total_valid_views", "valid_play_count")
    out["valid_view_rate"] = pick(merged, "valid_view_rate")
    out["avg_watch_duration"] = pick(merged, "avg_watch_duration")
    out["avg_watch_duration_rate"] = pick(merged, "avg_watch_duration_rate")
    out["like_count"] = pick(merged, "likes", "like_count")
    out["comment_count"] = pick(merged, "comments", "comment_count")
    out["favorite_count"] = pick(merged, "favorites", "favorite_count")
    out["share_count"] = pick(merged, "shares", "share_count")
    out["source_file"] = pick(merged, "source_file")
    out["source_table"] = "video_trend_daily_stats.csv"
    return ensure_columns(out, EPISODE_DAILY_COLUMNS)


def build_tencent_drama_daily(tencent_dir: Path) -> pd.DataFrame:
    parts = []

    for filename in ["album_daily_stats.csv", "album_trend_daily_stats.csv"]:
        df = read_csv_if_exists(tencent_dir / filename)
        if df.empty:
            continue

        out = pd.DataFrame(index=df.index)
        out["platform"] = PLATFORM_TENCENT
        out["date"] = pick(df, "date")
        out["platform_drama_id"] = pick(df, "album_id", "platform_drama_id")
        out["raw_title"] = pick(df, "album_title", "title", "raw_title")
        out["canonical_title"] = pick(df, "album_title", "title", "raw_title")
        out["script_id"] = ""
        out["script_title"] = pick(df, "source_project", "album_title", "title")
        out["match_status"] = ""
        out["match_confidence"] = ""
        out["play_count"] = pick(df, "total_views", "play_count")
        out["valid_play_count"] = pick(df, "total_valid_views", "valid_play_count")
        out["complete_play_count"] = pick(df, "complete_play_count")
        out["completion_rate"] = pick(df, "completion_rate")
        out["like_count"] = pick(df, "likes", "like_count")
        out["comment_count"] = pick(df, "comments", "comment_count")
        out["favorite_count"] = pick(df, "favorites", "favorite_count")
        out["share_count"] = pick(df, "shares", "share_count")
        out["paid_users"] = ""
        out["paid_orders"] = ""
        out["paid_amount"] = ""
        out["ad_spend"] = ""
        out["roi"] = ""
        out["source_file"] = pick(df, "source_file")
        out["source_table"] = filename
        parts.append(ensure_columns(out, DRAMA_DAILY_COLUMNS))

    if not parts:
        return pd.DataFrame(columns=DRAMA_DAILY_COLUMNS)

    return pd.concat(parts, ignore_index=True)


def build_tencent_overall_daily(tencent_dir: Path) -> pd.DataFrame:
    df = read_csv_if_exists(tencent_dir / "account_daily_stats.csv")
    if df.empty:
        return pd.DataFrame(columns=OVERALL_DAILY_COLUMNS)

    out = pd.DataFrame(index=df.index)
    out["platform"] = PLATFORM_TENCENT
    out["date"] = pick(df, "date")
    out["play_count"] = pick(df, "total_views", "play_count")
    out["valid_play_count"] = pick(df, "total_valid_views", "valid_play_count")
    out["like_count"] = pick(df, "likes", "like_count")
    out["comment_count"] = pick(df, "comments", "comment_count")
    out["favorite_count"] = pick(df, "favorites", "favorite_count")
    out["share_count"] = pick(df, "shares", "share_count")
    out["paid_users"] = ""
    out["paid_orders"] = ""
    out["paid_amount"] = ""
    out["ad_spend"] = ""
    out["global_roi"] = ""
    out["commercial_roi"] = ""
    out["iaa_ltv"] = ""
    out["iaa_roi"] = ""
    out["source_file"] = pick(df, "source_file")
    out["source_table"] = "account_daily_stats.csv"
    return ensure_columns(out, OVERALL_DAILY_COLUMNS)


def build_script_platform_mapping(tencent_dir: Path, kuaishou_dir: Path) -> pd.DataFrame:
    rows = []

    tencent_mapping = read_csv_if_exists(tencent_dir / "video_script_mapping_all.csv")
    if not tencent_mapping.empty:
        for _, r in tencent_mapping.iterrows():
            rows.append(
                {
                    "platform": PLATFORM_TENCENT,
                    "platform_drama_id": "",
                    "platform_video_id": "",
                    "video_title": r.get("video_title", ""),
                    "raw_title": r.get("video_title", ""),
                    "canonical_title": r.get("script_episode_title", r.get("video_title", "")),
                    "source_project": r.get("source_project", ""),
                    "episode_no": r.get("episode_no", ""),
                    "script_id": "",
                    "script_title": r.get("source_project", ""),
                    "script_file": r.get("script_file", ""),
                    "match_status": "matched" if str(r.get("script_file", "")).strip() else "script_file_missing",
                    "match_confidence": 1.0 if str(r.get("script_file", "")).strip() else "",
                    "note": r.get("note", ""),
                    "source_table": "video_script_mapping_all.csv",
                }
            )

    kuaishou_catalog = read_csv_if_exists(kuaishou_dir / "kuaishou_drama_catalog.csv")
    if not kuaishou_catalog.empty:
        for _, r in kuaishou_catalog.iterrows():
            rows.append(
                {
                    "platform": PLATFORM_KUAISHOU,
                    "platform_drama_id": r.get("platform_drama_id", ""),
                    "platform_video_id": "",
                    "video_title": "",
                    "raw_title": r.get("raw_title", ""),
                    "canonical_title": r.get("canonical_title", r.get("raw_title", "")),
                    "source_project": r.get("script_title", ""),
                    "episode_no": "",
                    "script_id": r.get("script_id", ""),
                    "script_title": r.get("script_title", ""),
                    "script_file": "",
                    "match_status": r.get("match_status", ""),
                    "match_confidence": r.get("match_confidence", ""),
                    "note": r.get("match_reason", ""),
                    "source_table": "kuaishou_drama_catalog.csv",
                }
            )

    if not rows:
        return pd.DataFrame(columns=MAPPING_COLUMNS)

    return ensure_columns(pd.DataFrame(rows), MAPPING_COLUMNS)


def summarize_outputs(outputs: dict[str, pd.DataFrame]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "tables": {},
        "platform_counts": {},
    }

    for name, df in outputs.items():
        summary["tables"][name] = int(len(df))
        if "platform" in df.columns and not df.empty:
            summary["platform_counts"][name] = df["platform"].value_counts(dropna=False).to_dict()
        else:
            summary["platform_counts"][name] = {}

    mapping = outputs.get("script_platform_mapping.csv", pd.DataFrame())
    if not mapping.empty and "match_status" in mapping.columns:
        summary["mapping_match_status_counts"] = mapping["match_status"].value_counts(dropna=False).to_dict()
    else:
        summary["mapping_match_status_counts"] = {}

    return summary


def build_platform_market_normalized(tencent_dir: Path, kuaishou_dir: Path, output_dir: Path) -> dict[str, pd.DataFrame]:
    outputs = {
        "platform_drama_catalog.csv": pd.concat(
            [
                pd.DataFrame(columns=DRAMA_CATALOG_COLUMNS),
                build_kuaishou_drama_catalog(kuaishou_dir),
            ],
            ignore_index=True,
        ),
        "platform_drama_daily_stats.csv": pd.concat(
            [
                build_tencent_drama_daily(tencent_dir),
                build_kuaishou_drama_daily(kuaishou_dir),
            ],
            ignore_index=True,
        ),
        "platform_episode_daily_stats.csv": build_tencent_episode_daily(tencent_dir),
        "platform_ad_account_daily_stats.csv": build_kuaishou_ad_daily(kuaishou_dir),
        "platform_overall_daily_stats.csv": pd.concat(
            [
                build_tencent_overall_daily(tencent_dir),
                build_kuaishou_overall_daily(kuaishou_dir),
            ],
            ignore_index=True,
        ),
        "script_platform_mapping.csv": build_script_platform_mapping(tencent_dir, kuaishou_dir),
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    for filename, df in outputs.items():
        write_csv(df, output_dir / filename)

    summary = summarize_outputs(outputs)
    (output_dir / "market_feedback_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return outputs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tencent", default="data/tencent_video_normalized")
    parser.add_argument("--kuaishou", default="data/kuaishou_normalized")
    parser.add_argument("--output", default="data/platform_market_normalized")
    args = parser.parse_args()

    tencent_dir = Path(args.tencent)
    kuaishou_dir = Path(args.kuaishou)
    output_dir = Path(args.output)

    outputs = build_platform_market_normalized(tencent_dir, kuaishou_dir, output_dir)
    summary = summarize_outputs(outputs)

    print("跨平台市场数据统一完成。")
    print(f"腾讯目录：{tencent_dir}")
    print(f"快手目录：{kuaishou_dir}")
    print(f"输出目录：{output_dir}")
    print("输出表：")
    for filename, row_count in summary["tables"].items():
        print(f"- {filename}: {row_count}")

    print("各表 platform 分布：")
    for filename, counts in summary["platform_counts"].items():
        print(f"- {filename}: {counts}")

    print("映射状态统计：")
    print(summary.get("mapping_match_status_counts", {}))


if __name__ == "__main__":
    main()
