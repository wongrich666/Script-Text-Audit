from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def read_csv_if_exists(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path, encoding="utf-8-sig")
    except UnicodeDecodeError:
        return pd.read_csv(path, encoding="utf-8")


def md_escape(value) -> str:
    text = "" if pd.isna(value) else str(value)
    return text.replace("\n", " ").replace("|", "/")


def render_table(df: pd.DataFrame, columns: list[str], limit: int = 50) -> str:
    if df.empty:
        return "无\n"

    work = df.copy()
    for col in columns:
        if col not in work.columns:
            work[col] = ""

    work = work[columns].head(limit)

    lines = []
    lines.append("| " + " | ".join(columns) + " |")
    lines.append("| " + " | ".join(["---"] * len(columns)) + " |")
    for _, row in work.iterrows():
        lines.append("| " + " | ".join(md_escape(row[col]) for col in columns) + " |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-report", default="data/platform_market_normalized/market_feedback_report.md")
    parser.add_argument("--rankings", default="data/external_benchmark/juchacha_normalized/juchacha_rankings.csv")
    parser.add_argument("--output", default="data/platform_market_normalized/market_feedback_report_with_juchacha.md")
    args = parser.parse_args()

    base_path = Path(args.base_report)
    rankings_path = Path(args.rankings)
    output_path = Path(args.output)

    if base_path.exists():
        base = base_path.read_text(encoding="utf-8")
    else:
        base = "# 跨平台市场反馈复盘报告\n\n"

    rankings = read_csv_if_exists(rankings_path)

    lines = [base.rstrip(), "", "## 外部平台榜单参考：剧查查", ""]

    if rankings.empty:
        lines.append("未找到剧查查正式榜单数据。")
    else:
        lines.append(f"- 剧查查榜单总行数：{len(rankings)}")
        if "ranking_platform" in rankings.columns:
            lines.append(f"- 平台分布：{rankings['ranking_platform'].fillna('空值').value_counts().to_dict()}")
        if "ranking_name" in rankings.columns:
            lines.append(f"- 榜单分布：{rankings['ranking_name'].fillna('空值').value_counts().to_dict()}")
        lines.append("")
        lines.append("### 榜单样本")
        lines.append("")
        lines.append(render_table(
            rankings.sort_values(
                ["ranking_date", "ranking_platform", "ranking_name", "rank"],
                ascending=[False, True, True, True],
                kind="stable",
            ),
            [
                "ranking_date",
                "ranking_platform",
                "ranking_name",
                "rank",
                "drama_title",
                "heat_text",
                "genre_or_tag",
                "publisher_or_account",
                "source_image",
            ],
            limit=80,
        ))

        lines.append("")
        lines.append("说明：剧查查榜单只作为外部平台生态参考，不直接作为我方剧集播放效果归因。")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("已生成带剧查查外部榜单参考的报告。")
    print(f"输出：{output_path}")


if __name__ == "__main__":
    main()
