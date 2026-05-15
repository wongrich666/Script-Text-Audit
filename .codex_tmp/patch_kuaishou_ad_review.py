from pathlib import Path

p = Path("scripts/import_kuaishou_data.py")
text = p.read_text(encoding="utf-8")

backup = Path("scripts/import_kuaishou_data.py.before_review_patch")
backup.write_text(text, encoding="utf-8")

if "def make_ad_account_review_tables" not in text:
    insert_at = text.index("\ndef make_match_report")

    review_func = r'''
def make_ad_account_review_tables(ad_daily: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    review_columns_unique = [
        "ad_account_name",
        "extracted_title",
        "script_id",
        "script_title",
        "match_status",
        "match_method",
        "match_confidence",
        "match_reason",
        "review_required",
        "source_file",
    ]

    review_columns_by_spend = [
        "ad_account_name",
        "rows",
        "total_spend",
        "sample_extracted_title",
        "sample_script_title",
        "sample_match_status",
        "sample_match_method",
        "sample_match_confidence",
        "sample_match_reason",
    ]

    if ad_daily.empty or "match_status" not in ad_daily.columns:
        return (
            pd.DataFrame(columns=review_columns_unique),
            pd.DataFrame(columns=review_columns_by_spend),
        )

    review = ad_daily[
        ad_daily["match_status"].isin(["account_name_generic", "needs_review", "unmatched", "ambiguous_match"])
    ].copy()

    if review.empty:
        return (
            pd.DataFrame(columns=review_columns_unique),
            pd.DataFrame(columns=review_columns_by_spend),
        )

    for col in review_columns_unique:
        if col not in review.columns:
            review[col] = ""

    review_unique = (
        review[review_columns_unique]
        .drop_duplicates()
        .sort_values(["match_status", "ad_account_name"], kind="stable")
        .reset_index(drop=True)
    )

    review["spend_numeric"] = pd.to_numeric(review.get("spend", 0), errors="coerce").fillna(0)

    rows = []
    for account_name, group in review.groupby("ad_account_name", dropna=False):
        first = group.iloc[0]
        rows.append(
            {
                "ad_account_name": account_name,
                "rows": int(len(group)),
                "total_spend": round(float(group["spend_numeric"].sum()), 4),
                "sample_extracted_title": first.get("extracted_title", ""),
                "sample_script_title": first.get("script_title", ""),
                "sample_match_status": first.get("match_status", ""),
                "sample_match_method": first.get("match_method", ""),
                "sample_match_confidence": first.get("match_confidence", ""),
                "sample_match_reason": first.get("match_reason", ""),
            }
        )

    review_by_spend = pd.DataFrame(rows, columns=review_columns_by_spend)
    if not review_by_spend.empty:
        review_by_spend = review_by_spend.sort_values(
            ["total_spend", "rows", "ad_account_name"],
            ascending=[False, False, True],
            kind="stable",
        ).reset_index(drop=True)

    return review_unique, review_by_spend
'''
    text = text[:insert_at] + "\n\n" + review_func + text[insert_at:]

old = '''    match_report = make_match_report(catalog, drama_daily, ad_daily)
'''
new = '''    match_report = make_match_report(catalog, drama_daily, ad_daily)
    ad_account_review_unique, ad_account_review_by_spend = make_ad_account_review_tables(ad_daily)
'''
if old not in text:
    raise SystemExit("找不到 match_report 生成位置，请手动检查。")
text = text.replace(old, new, 1)

old = '''    write_csv(ad_daily, output_dir / "kuaishou_ad_account_daily_stats.csv")
    write_csv(overall_daily, output_dir / "kuaishou_overall_daily_stats.csv")
    write_csv(match_report, output_dir / "kuaishou_title_match_report.csv")
'''
new = '''    write_csv(ad_daily, output_dir / "kuaishou_ad_account_daily_stats.csv")
    write_csv(overall_daily, output_dir / "kuaishou_overall_daily_stats.csv")
    write_csv(match_report, output_dir / "kuaishou_title_match_report.csv")
    write_csv(ad_account_review_unique, output_dir / "kuaishou_ad_account_review_unique.csv")
    write_csv(ad_account_review_by_spend, output_dir / "kuaishou_ad_account_review_by_spend.csv")
'''
if old not in text:
    raise SystemExit("找不到 write_csv 输出位置，请手动检查。")
text = text.replace(old, new, 1)

old = '''        "match_report_rows": int(len(match_report)),
'''
new = '''        "match_report_rows": int(len(match_report)),
        "ad_account_review_unique_rows": int(len(ad_account_review_unique)),
        "ad_account_review_by_spend_rows": int(len(ad_account_review_by_spend)),
'''
if old not in text:
    raise SystemExit("找不到 summary match_report_rows 位置，请手动检查。")
text = text.replace(old, new, 1)

old = '''    print(f"[kuaishou] 需处理匹配问题行数：{len(match_report)}")
'''
new = '''    print(f"[kuaishou] 需处理匹配问题行数：{len(match_report)}")
    print(f"[kuaishou] 广告账户复核去重行数：{len(ad_account_review_unique)}")
    print(f"[kuaishou] 广告账户复核按消耗聚合行数：{len(ad_account_review_by_spend)}")
'''
if old not in text:
    raise SystemExit("找不到 print match_report 位置，请手动检查。")
text = text.replace(old, new, 1)

p.write_text(text, encoding="utf-8")
print("patched scripts/import_kuaishou_data.py for ad account review outputs")
