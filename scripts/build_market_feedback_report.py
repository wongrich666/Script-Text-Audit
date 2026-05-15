from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd


ISSUE_MATCH_STATUSES = {
    "script_file_missing",
    "account_name_generic",
    "needs_review",
    "unmatched",
    "ambiguous_match",
}


def read_csv_if_exists(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path, encoding="utf-8-sig")
    except UnicodeDecodeError:
        return pd.read_csv(path, encoding="utf-8")


def to_number(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.astype(str).str.replace(",", "", regex=False).str.replace("%", "", regex=False),
        errors="coerce",
    )


def safe_col(df: pd.DataFrame, name: str, default: Any = "") -> pd.Series:
    if name in df.columns:
        return df[name]
    return pd.Series([default] * len(df), index=df.index)


def latest_rows(df: pd.DataFrame, group_cols: list[str], date_col: str = "date") -> pd.DataFrame:
    if df.empty:
        return df.copy()

    work = df.copy()
    work["_row_order"] = range(len(work))

    if date_col in work.columns:
        work["_date_parsed"] = pd.to_datetime(work[date_col], errors="coerce")
    else:
        work["_date_parsed"] = pd.NaT

    sort_cols = [c for c in group_cols if c in work.columns] + ["_date_parsed", "_row_order"]
    work = work.sort_values(sort_cols, na_position="first", kind="stable")

    if not group_cols:
        out = work.tail(1)
    else:
        existing_group_cols = [c for c in group_cols if c in work.columns]
        if existing_group_cols:
            out = work.groupby(existing_group_cols, dropna=False).tail(1)
        else:
            out = work.tail(1)

    return out.drop(columns=["_row_order", "_date_parsed"], errors="ignore").reset_index(drop=True)


def records(df: pd.DataFrame, columns: list[str], limit: int = 20) -> list[dict[str, Any]]:
    if df.empty:
        return []
    out = df.copy()
    for col in columns:
        if col not in out.columns:
            out[col] = ""
    out = out[columns].head(limit)
    return out.fillna("").to_dict(orient="records")


def table_counts(platform_dir: Path) -> dict[str, int]:
    filenames = [
        "platform_drama_catalog.csv",
        "platform_drama_daily_stats.csv",
        "platform_episode_daily_stats.csv",
        "platform_ad_account_daily_stats.csv",
        "platform_overall_daily_stats.csv",
        "script_platform_mapping.csv",
    ]
    result = {}
    for filename in filenames:
        df = read_csv_if_exists(platform_dir / filename)
        result[filename] = int(len(df))
    return result


def platform_counts(df: pd.DataFrame) -> dict[str, int]:
    if df.empty or "platform" not in df.columns:
        return {}
    return {str(k): int(v) for k, v in df["platform"].fillna("空值").value_counts().to_dict().items()}


def summarize_mapping(mapping: pd.DataFrame) -> dict[str, Any]:
    if mapping.empty:
        return {
            "rows": 0,
            "match_status_counts": {},
            "issue_rows": 0,
            "issue_samples": [],
        }

    status = safe_col(mapping, "match_status")
    issue_mask = status.astype(str).isin(ISSUE_MATCH_STATUSES)
    issue_df = mapping[issue_mask].copy()

    return {
        "rows": int(len(mapping)),
        "match_status_counts": {
            str(k): int(v)
            for k, v in status.fillna("空值").value_counts().to_dict().items()
        },
        "issue_rows": int(len(issue_df)),
        "issue_samples": records(
            issue_df,
            [
                "platform",
                "raw_title",
                "video_title",
                "source_project",
                "script_title",
                "match_status",
                "note",
                "source_table",
            ],
            limit=30,
        ),
    }


def summarize_episode_performance(episode_daily: pd.DataFrame) -> dict[str, Any]:
    if episode_daily.empty:
        return {
            "rows": 0,
            "unique_videos": 0,
            "top_valid_view_rate": [],
            "low_valid_view_rate": [],
            "top_interaction": [],
        }

    latest = latest_rows(
        episode_daily,
        ["platform", "video_title"],
        date_col="date",
    )

    latest["valid_view_rate_num"] = to_number(safe_col(latest, "valid_view_rate"))
    latest["like_count_num"] = to_number(safe_col(latest, "like_count")).fillna(0)
    latest["comment_count_num"] = to_number(safe_col(latest, "comment_count")).fillna(0)
    latest["share_count_num"] = to_number(safe_col(latest, "share_count")).fillna(0)
    latest["interaction_latest"] = (
        latest["like_count_num"] + latest["comment_count_num"] + latest["share_count_num"]
    )

    view_cols = [
        "platform",
        "source_project",
        "video_title",
        "episode_no",
        "date",
        "play_count",
        "valid_play_count",
        "valid_view_rate",
        "avg_watch_duration_rate",
    ]

    interaction_cols = [
        "platform",
        "source_project",
        "video_title",
        "episode_no",
        "date",
        "play_count",
        "like_count",
        "comment_count",
        "share_count",
        "interaction_latest",
    ]

    valid_non_null = latest[latest["valid_view_rate_num"].notna()].copy()

    top_valid = valid_non_null.sort_values(
        ["valid_view_rate_num", "play_count"],
        ascending=[False, False],
        kind="stable",
    )

    low_valid = valid_non_null.sort_values(
        ["valid_view_rate_num", "play_count"],
        ascending=[True, False],
        kind="stable",
    )

    top_interaction = latest.sort_values(
        ["interaction_latest", "play_count"],
        ascending=[False, False],
        kind="stable",
    )

    return {
        "rows": int(len(episode_daily)),
        "unique_videos": int(safe_col(episode_daily, "video_title").nunique()),
        "platform_counts": platform_counts(episode_daily),
        "top_valid_view_rate": records(top_valid, view_cols, limit=15),
        "low_valid_view_rate": records(low_valid, view_cols, limit=15),
        "top_interaction": records(top_interaction, interaction_cols, limit=15),
    }


def summarize_ad_accounts(ad_daily: pd.DataFrame) -> dict[str, Any]:
    if ad_daily.empty:
        return {
            "rows": 0,
            "issue_rows": 0,
            "issue_accounts": 0,
            "top_issue_accounts_by_spend": [],
        }

    status = safe_col(ad_daily, "match_status").astype(str)
    issue = ad_daily[status.isin(ISSUE_MATCH_STATUSES)].copy()

    if issue.empty:
        return {
            "rows": int(len(ad_daily)),
            "issue_rows": 0,
            "issue_accounts": 0,
            "top_issue_accounts_by_spend": [],
        }

    issue["spend_num"] = to_number(safe_col(issue, "spend")).fillna(0)

    group_cols = ["ad_account_name"]
    rows = []
    for account_name, group in issue.groupby(group_cols, dropna=False):
        first = group.iloc[0]
        rows.append(
            {
                "ad_account_name": account_name,
                "rows": int(len(group)),
                "total_spend": round(float(group["spend_num"].sum()), 4),
                "sample_extracted_title": first.get("extracted_title", ""),
                "sample_script_title": first.get("script_title", ""),
                "sample_match_status": first.get("match_status", ""),
                "sample_match_confidence": first.get("match_confidence", ""),
            }
        )

    top = pd.DataFrame(rows)
    if not top.empty:
        top = top.sort_values(
            ["total_spend", "rows", "ad_account_name"],
            ascending=[False, False, True],
            kind="stable",
        )

    return {
        "rows": int(len(ad_daily)),
        "platform_counts": platform_counts(ad_daily),
        "issue_rows": int(len(issue)),
        "issue_accounts": int(safe_col(issue, "ad_account_name").nunique()),
        "top_issue_accounts_by_spend": records(
            top,
            [
                "ad_account_name",
                "rows",
                "total_spend",
                "sample_extracted_title",
                "sample_script_title",
                "sample_match_status",
                "sample_match_confidence",
            ],
            limit=30,
        ),
    }


def summarize_overall(overall_daily: pd.DataFrame) -> dict[str, Any]:
    if overall_daily.empty:
        return {
            "rows": 0,
            "latest_by_platform": [],
        }

    latest = latest_rows(overall_daily, ["platform"], date_col="date")

    cols = [
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
        "source_table",
    ]

    return {
        "rows": int(len(overall_daily)),
        "platform_counts": platform_counts(overall_daily),
        "latest_by_platform": records(latest, cols, limit=20),
    }


def build_market_feedback_report(platform_dir: Path, output_dir: Path | None = None) -> dict[str, Any]:
    output_dir = output_dir or platform_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    drama_catalog = read_csv_if_exists(platform_dir / "platform_drama_catalog.csv")
    drama_daily = read_csv_if_exists(platform_dir / "platform_drama_daily_stats.csv")
    episode_daily = read_csv_if_exists(platform_dir / "platform_episode_daily_stats.csv")
    ad_daily = read_csv_if_exists(platform_dir / "platform_ad_account_daily_stats.csv")
    overall_daily = read_csv_if_exists(platform_dir / "platform_overall_daily_stats.csv")
    mapping = read_csv_if_exists(platform_dir / "script_platform_mapping.csv")

    report = {
        "input_dir": str(platform_dir),
        "table_counts": table_counts(platform_dir),
        "drama_catalog": {
            "rows": int(len(drama_catalog)),
            "platform_counts": platform_counts(drama_catalog),
        },
        "drama_daily": {
            "rows": int(len(drama_daily)),
            "platform_counts": platform_counts(drama_daily),
        },
        "episode_performance": summarize_episode_performance(episode_daily),
        "ad_account_review": summarize_ad_accounts(ad_daily),
        "overall_daily": summarize_overall(overall_daily),
        "mapping": summarize_mapping(mapping),
    }

    json_path = output_dir / "market_feedback_report.json"
    md_path = output_dir / "market_feedback_report.md"

    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    md_path.write_text(render_markdown_report(report), encoding="utf-8")

    return report


def render_markdown_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    if not rows:
        return "无\n"

    lines = []
    lines.append("| " + " | ".join(columns) + " |")
    lines.append("| " + " | ".join(["---"] * len(columns)) + " |")

    for row in rows:
        values = [str(row.get(col, "")).replace("\n", " ") for col in columns]
        lines.append("| " + " | ".join(values) + " |")

    return "\n".join(lines) + "\n"


def render_markdown_report(report: dict[str, Any]) -> str:
    lines = []
    lines.append("# 跨平台市场反馈复盘报告")
    lines.append("")
    lines.append("## 1. 数据表概览")
    lines.append("")
    lines.append(render_markdown_table(
        [{"table": k, "rows": v} for k, v in report["table_counts"].items()],
        ["table", "rows"],
    ))

    lines.append("")
    lines.append("## 2. 剧本/平台映射状态")
    lines.append("")
    lines.append(f"- 映射总行数：{report['mapping']['rows']}")
    lines.append(f"- 问题映射行数：{report['mapping']['issue_rows']}")
    lines.append(f"- 状态分布：{report['mapping']['match_status_counts']}")
    lines.append("")
    lines.append("### 需要关注的映射样本")
    lines.append("")
    lines.append(render_markdown_table(
        report["mapping"]["issue_samples"],
        ["platform", "raw_title", "video_title", "source_project", "script_title", "match_status", "note"],
    ))

    lines.append("")
    lines.append("## 3. 腾讯单集表现")
    lines.append("")
    lines.append(f"- 单集日数据行数：{report['episode_performance']['rows']}")
    lines.append(f"- 视频数量：{report['episode_performance']['unique_videos']}")
    lines.append("")
    lines.append("### 有效播放率较高")
    lines.append("")
    lines.append(render_markdown_table(
        report["episode_performance"]["top_valid_view_rate"],
        ["platform", "source_project", "video_title", "episode_no", "date", "play_count", "valid_play_count", "valid_view_rate"],
    ))
    lines.append("")
    lines.append("### 有效播放率较低")
    lines.append("")
    lines.append(render_markdown_table(
        report["episode_performance"]["low_valid_view_rate"],
        ["platform", "source_project", "video_title", "episode_no", "date", "play_count", "valid_play_count", "valid_view_rate"],
    ))
    lines.append("")
    lines.append("### 互动较高")
    lines.append("")
    lines.append(render_markdown_table(
        report["episode_performance"]["top_interaction"],
        ["platform", "source_project", "video_title", "episode_no", "date", "play_count", "like_count", "comment_count", "share_count", "interaction_latest"],
    ))

    lines.append("")
    lines.append("## 4. 快手广告账户复核")
    lines.append("")
    lines.append(f"- 广告账户日数据行数：{report['ad_account_review']['rows']}")
    lines.append(f"- 需要复核的数据行数：{report['ad_account_review']['issue_rows']}")
    lines.append(f"- 需要复核的账户数：{report['ad_account_review']['issue_accounts']}")
    lines.append("")
    lines.append(render_markdown_table(
        report["ad_account_review"]["top_issue_accounts_by_spend"],
        ["ad_account_name", "rows", "total_spend", "sample_extracted_title", "sample_script_title", "sample_match_status", "sample_match_confidence"],
    ))

    lines.append("")
    lines.append("## 5. 平台整体日数据")
    lines.append("")
    lines.append(render_markdown_table(
        report["overall_daily"]["latest_by_platform"],
        ["platform", "date", "play_count", "valid_play_count", "paid_amount", "ad_spend", "global_roi", "commercial_roi", "iaa_ltv", "iaa_roi"],
    ))

    lines.append("")
    lines.append("## 6. 当前结论")
    lines.append("")
    lines.append("- 当前报告只做复盘与数据质量检查，不训练模型。")
    lines.append("- 腾讯侧重点关注单集有效播放率、互动与剧本文本之间的关系。")
    lines.append("- 快手侧重点关注广告账户映射质量、消耗和 ROI。")
    lines.append("- 后续应优先处理 script_file_missing、account_name_generic、needs_review。")
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/platform_market_normalized")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    input_dir = Path(args.input)
    output_dir = Path(args.output) if args.output else input_dir

    report = build_market_feedback_report(input_dir, output_dir)

    print("跨平台市场反馈报告生成完成。")
    print(f"输入目录：{input_dir}")
    print(f"输出目录：{output_dir}")
    print(f"报告 JSON：{output_dir / 'market_feedback_report.json'}")
    print(f"报告 Markdown：{output_dir / 'market_feedback_report.md'}")
    print("核心统计：")
    print(f"- 映射问题行数：{report['mapping']['issue_rows']}")
    print(f"- 广告账户复核行数：{report['ad_account_review']['issue_rows']}")
    print(f"- 广告账户复核账户数：{report['ad_account_review']['issue_accounts']}")


if __name__ == "__main__":
    main()
