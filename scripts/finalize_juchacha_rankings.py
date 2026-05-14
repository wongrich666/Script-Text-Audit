from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


FINAL_COLUMNS = [
    "source_name",
    "ranking_date",
    "ranking_platform",
    "ranking_name",
    "page_no",
    "rank",
    "drama_title",
    "heat_text",
    "genre_or_tag",
    "publisher_or_account",
    "row_text",
    "source_image",
    "ocr_confidence",
    "review_status",
    "note",
    "import_batch_id",
]


def read_csv_if_exists(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=FINAL_COLUMNS)
    try:
        return pd.read_csv(path, encoding="utf-8-sig")
    except UnicodeDecodeError:
        return pd.read_csv(path, encoding="utf-8")


def ensure_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in FINAL_COLUMNS:
        if col not in out.columns:
            out[col] = ""
    return out[FINAL_COLUMNS]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--draft", default="data/external_benchmark/juchacha_normalized/juchacha_rankings_draft.csv")
    parser.add_argument("--final", default="data/external_benchmark/juchacha_normalized/juchacha_rankings.csv")
    parser.add_argument("--accept-all", action="store_true", help="不等人工改 review_status，直接全部进入正式表。")
    args = parser.parse_args()

    draft_path = Path(args.draft)
    final_path = Path(args.final)

    draft = ensure_columns(read_csv_if_exists(draft_path))
    existing = ensure_columns(read_csv_if_exists(final_path))

    if draft.empty:
        print(f"草稿为空：{draft_path}")
        return

    if args.accept_all:
        selected = draft.copy()
        selected["review_status"] = "confirmed"
    else:
        selected = draft[draft["review_status"].astype(str).str.lower().eq("confirmed")].copy()

    if selected.empty:
        print("没有 review_status=confirmed 的行。")
        print("你可以先人工校对 draft，把确认的行改成 confirmed；或者用 --accept-all。")
        return

    combined = pd.concat([existing, selected], ignore_index=True)
    combined = ensure_columns(combined)

    key_cols = [
        "source_name",
        "ranking_date",
        "ranking_platform",
        "ranking_name",
        "rank",
        "drama_title",
    ]

    combined = combined.drop_duplicates(subset=key_cols, keep="last")
    combined = combined.sort_values(
        ["ranking_date", "ranking_platform", "ranking_name", "rank"],
        ascending=[False, True, True, True],
        kind="stable",
    )

    final_path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(final_path, index=False, encoding="utf-8-sig")

    print("剧查查正式榜单表已更新。")
    print(f"草稿行数：{len(draft)}")
    print(f"本次确认行数：{len(selected)}")
    print(f"正式表总行数：{len(combined)}")
    print(f"输出：{final_path}")


if __name__ == "__main__":
    main()
