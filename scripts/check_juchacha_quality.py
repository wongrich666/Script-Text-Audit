from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


ERROR_TYPES = {
    "duplicate_rank",
    "missing_rank",
    "empty_title",
}

WARNING_TYPES = {
    "title_noise",
    "episode_count_not_number",
    "empty_heat_text",
}


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path, encoding="utf-8-sig", dtype=str).fillna("")
    except UnicodeDecodeError:
        return pd.read_csv(path, encoding="utf-8", dtype=str).fillna("")


def add_issue(issues: list[dict], issue_type: str, row: dict | None = None, detail: str = "") -> None:
    row = row or {}
    severity = "error" if issue_type in ERROR_TYPES else "warning"
    issues.append(
        {
            "severity": severity,
            "issue_type": issue_type,
            "ranking_date": row.get("ranking_date", ""),
            "ranking_platform": row.get("ranking_platform", ""),
            "ranking_name": row.get("ranking_name", ""),
            "page_no": row.get("page_no", ""),
            "rank": row.get("rank", ""),
            "detail": detail,
        }
    )


def make_summary(draft_df: pd.DataFrame, issues_df: pd.DataFrame) -> dict:
    error_count = int((issues_df["severity"] == "error").sum()) if not issues_df.empty else 0
    warning_count = int((issues_df["severity"] == "warning").sum()) if not issues_df.empty else 0

    if draft_df.empty:
        platform_counts = {}
        ranking_counts = []
    else:
        platform_counts = draft_df.get("ranking_platform", pd.Series(dtype=str)).value_counts().to_dict()
        ranking_counts = (
            draft_df.groupby(["ranking_platform", "ranking_name"], dropna=False)
            .size()
            .reset_index(name="count")
            .to_dict(orient="records")
            if {"ranking_platform", "ranking_name"}.issubset(draft_df.columns)
            else []
        )

    return {
        "draft_rows": int(len(draft_df)),
        "issue_rows": int(len(issues_df)),
        "error_count": error_count,
        "warning_count": warning_count,
        "issue_type_counts": issues_df["issue_type"].value_counts().to_dict() if not issues_df.empty else {},
        "severity_counts": issues_df["severity"].value_counts().to_dict() if not issues_df.empty else {},
        "platform_counts": {str(k): int(v) for k, v in platform_counts.items()},
        "ranking_counts": ranking_counts,
        "can_finalize": error_count == 0,
    }


def check_quality(draft_path: Path) -> tuple[pd.DataFrame, dict]:
    df = read_csv(draft_path)
    issues: list[dict] = []

    issue_columns = [
        "severity",
        "issue_type",
        "ranking_date",
        "ranking_platform",
        "ranking_name",
        "page_no",
        "rank",
        "detail",
    ]

    if df.empty:
        add_issue(issues, "empty_title", detail=f"草稿表为空或不存在：{draft_path}")
        issues_df = pd.DataFrame(issues, columns=issue_columns)
        return issues_df, make_summary(df, issues_df)

    required_cols = [
        "ranking_date",
        "ranking_platform",
        "ranking_name",
        "page_no",
        "rank",
        "drama_title",
        "episode_count",
        "heat_text",
    ]

    for col in required_cols:
        if col not in df.columns:
            df[col] = ""

    group_cols = ["ranking_date", "ranking_platform", "ranking_name", "page_no"]

    for key, g in df.groupby(group_cols, dropna=False):
        ranking_date, platform, ranking_name, page_no = key
        base_row = {
            "ranking_date": ranking_date,
            "ranking_platform": platform,
            "ranking_name": ranking_name,
            "page_no": page_no,
            "rank": "",
        }

        ranks = pd.to_numeric(g["rank"], errors="coerce")
        rank_list = [int(x) for x in ranks.dropna().tolist()]

        duplicates = sorted(set([x for x in rank_list if rank_list.count(x) > 1]))
        missing = sorted(set(range(1, 31)) - set(rank_list))

        for r in duplicates:
            row = {**base_row, "rank": str(r)}
            add_issue(issues, "duplicate_rank", row, f"重复排名：{r}")

        for r in missing:
            row = {**base_row, "rank": str(r)}
            add_issue(issues, "missing_rank", row, f"缺失排名：{r}")

        if len(g) != 30:
            add_issue(issues, "missing_rank", base_row, f"该榜单行数不是 30，当前行数：{len(g)}")

    for _, row_obj in df.iterrows():
        row = row_obj.to_dict()
        title = str(row.get("drama_title", "")).strip()
        ep = str(row.get("episode_count", "")).strip()
        heat = str(row.get("heat_text", "")).strip()

        if not title:
            add_issue(issues, "empty_title", row, "剧名为空")

        if any(x in title for x in ["(", "（", ")", "）"]) or title.endswith(".") or "  " in title or ".." in title:
            add_issue(issues, "title_noise", row, f"剧名疑似有 OCR 噪声：{title}")

        if ep and not ep.isdigit():
            add_issue(issues, "episode_count_not_number", row, f"集数不是数字：{ep}")

        if not heat:
            add_issue(issues, "empty_heat_text", row, "热度/播放字段为空")

    issues_df = pd.DataFrame(issues, columns=issue_columns)
    return issues_df, make_summary(df, issues_df)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--draft", default="data/external_benchmark/juchacha_normalized/juchacha_rankings_draft.csv")
    parser.add_argument("--output", default="data/external_benchmark/juchacha_normalized/juchacha_rankings_quality_issues.csv")
    parser.add_argument("--summary", default="data/external_benchmark/juchacha_normalized/juchacha_quality_summary.json")
    parser.add_argument("--fail-on-error", action="store_true")
    args = parser.parse_args()

    draft_path = Path(args.draft)
    output_path = Path(args.output)
    summary_path = Path(args.summary)

    issues_df, summary = check_quality(draft_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    issues_df.to_csv(output_path, index=False, encoding="utf-8-sig")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("剧查查质量检查完成。")
    print(f"draft_rows: {summary['draft_rows']}")
    print(f"issue_rows: {summary['issue_rows']}")
    print(f"error_count: {summary['error_count']}")
    print(f"warning_count: {summary['warning_count']}")
    print(f"can_finalize: {summary['can_finalize']}")
    print(f"issues_output: {output_path}")
    print(f"summary_output: {summary_path}")

    if args.fail_on_error and summary["error_count"] > 0:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
