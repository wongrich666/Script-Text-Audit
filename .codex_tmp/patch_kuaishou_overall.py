from pathlib import Path

p = Path("scripts/import_kuaishou_data.py")
text = p.read_text(encoding="utf-8")

backup = Path("scripts/import_kuaishou_data.py.before_overall_patch")
backup.write_text(text, encoding="utf-8")

# 1. 修复 build_script_registry 空 rows 时没有表头的问题
old_registry_return = '''    return pd.DataFrame(rows)


def classify_table(df: pd.DataFrame) -> str:
'''
new_registry_return = '''    return pd.DataFrame(
        rows,
        columns=[
            "script_id",
            "canonical_title",
            "title_norm",
            "aliases",
            "script_path",
            "episode_count",
            "content_hash",
        ],
    )


def classify_table(df: pd.DataFrame) -> str:
'''
if old_registry_return in text:
    text = text.replace(old_registry_return, new_registry_return, 1)

# 2. 替换 classify_table，增加 overall_daily 分类
start = text.index("def classify_table")
end = text.index("\ndef safe_get", start)

new_classify = '''def classify_table(df: pd.DataFrame) -> str:
    cols = set(df.columns)

    if {"短剧ID", "短剧名称"}.issubset(cols):
        return "drama_catalog"

    if "短剧名称" in cols and ("付费金额" in cols or "全域ROI" in cols or "消耗" in cols):
        return "drama_daily"

    has_date = "日期" in cols
    has_drama_entity = "短剧名称" in cols
    has_ad_entity = "广告账户名称" in cols or "广告账户" in cols
    overall_markers = {
        "视频-播放量",
        "视频-点赞量",
        "视频-评论量",
        "视频-收藏量",
        "付费人数",
        "付费订单数",
        "付费金额（元）",
        "付费金额(元)",
        "消耗（元）",
        "消耗(元)",
        "消耗（ 元）",
        "全域ROI",
        "商业化ROI",
        "IAA广告含返货LTV(元)",
        "IAA广告含返货变现ROI",
        "IAA广告不含返货LTV(元)",
        "IAA广告不含返货变现ROI",
    }

    if has_date and not has_drama_entity and not has_ad_entity and (cols & overall_markers):
        return "overall_daily"

    if "广告账户名称" in cols or "广告账户" in cols or "花费（元）" in cols or "花费(元)" in cols:
        return "ad_account_daily"

    if "日期" in cols and ("播放量" in cols or "视频播放数" in cols or "消耗" in cols):
        return "core_daily"

    return "unknown"
'''

text = text[:start] + new_classify + "\n" + text[end + 1:]

# 3. 插入 normalize_overall_daily
if "def normalize_overall_daily" not in text:
    insert_at = text.index("\ndef normalize_catalog")
    new_overall = r'''
def normalize_overall_daily(df: pd.DataFrame) -> pd.DataFrame:
    rows = []

    for _, row in df.iterrows():
        rows.append(
            {
                "platform": PLATFORM,
                "date": safe_get(row, "日期"),
                "play_count": to_number(safe_get(row, "视频-播放量", "视频播放量", "播放量")),
                "like_count": to_number(safe_get(row, "视频-点赞量", "点赞量", "点赞数")),
                "comment_count": to_number(safe_get(row, "视频-评论量", "评论量", "评论数")),
                "favorite_count": to_number(safe_get(row, "视频-收藏量", "收藏量", "收藏数")),
                "paid_users": to_number(safe_get(row, "付费人数")),
                "paid_orders": to_number(safe_get(row, "付费订单数", "付费单量")),
                "paid_amount": to_number(safe_get(row, "付费金额（元）", "付费金额(元)", "付费金额")),
                "ad_spend": to_number(safe_get(row, "消耗（元）", "消耗(元)", "消耗（ 元）", "消耗", "花费（元）", "花费(元)")),
                "global_roi": to_number(safe_get(row, "全域ROI", "全域 ROI")),
                "commercial_roi": to_number(safe_get(row, "商业化ROI", "商业化 ROI")),
                "iaa_ltv_with_rebate": to_number(safe_get(row, "IAA广告含返货LTV(元)", "IAA广告含返货LTV（元）")),
                "iaa_roi_with_rebate": to_number(safe_get(row, "IAA广告含返货变现ROI")),
                "iaa_ltv_without_rebate": to_number(safe_get(row, "IAA广告不含返货LTV(元)", "IAA广告不含返货LTV（元）")),
                "iaa_roi_without_rebate": to_number(safe_get(row, "IAA广告不含返货变现ROI")),
                "source_file": safe_get(row, "source_file"),
                "source_sheet": safe_get(row, "source_sheet"),
            }
        )

    return pd.DataFrame(
        rows,
        columns=[
            "platform",
            "date",
            "play_count",
            "like_count",
            "comment_count",
            "favorite_count",
            "paid_users",
            "paid_orders",
            "paid_amount",
            "ad_spend",
            "global_roi",
            "commercial_roi",
            "iaa_ltv_with_rebate",
            "iaa_roi_with_rebate",
            "iaa_ltv_without_rebate",
            "iaa_roi_without_rebate",
            "source_file",
            "source_sheet",
        ],
    )
'''
    text = text[:insert_at] + "\n\n" + new_overall + text[insert_at:]

# 4. main 中增加 overall frame 收集
old = '''    all_catalog_frames: list[pd.DataFrame] = []
    all_drama_daily_frames: list[pd.DataFrame] = []
    all_ad_daily_frames: list[pd.DataFrame] = []
    unknown_files: list[dict[str, str]] = []
'''
new = '''    all_catalog_frames: list[pd.DataFrame] = []
    all_drama_daily_frames: list[pd.DataFrame] = []
    all_ad_daily_frames: list[pd.DataFrame] = []
    all_overall_daily_frames: list[pd.DataFrame] = []
    unknown_files: list[dict[str, str]] = []
'''
if old not in text:
    raise SystemExit("找不到 main frame 初始化块，请手动检查脚本。")
text = text.replace(old, new, 1)

old = '''            elif kind in {"ad_account_daily", "core_daily"}:
                all_ad_daily_frames.append(df)
            else:
                unknown_files.append({"file": path.name, "columns": ",".join(df.columns)})
'''
new = '''            elif kind == "overall_daily":
                all_overall_daily_frames.append(df)
            elif kind in {"ad_account_daily", "core_daily"}:
                all_ad_daily_frames.append(df)
            else:
                unknown_files.append({"file": path.name, "columns": ",".join(df.columns)})
'''
if old not in text:
    raise SystemExit("找不到 kind 分流块，请手动检查脚本。")
text = text.replace(old, new, 1)

old = '''    raw_catalog = pd.concat(all_catalog_frames, ignore_index=True) if all_catalog_frames else pd.DataFrame()
    raw_drama_daily = pd.concat(all_drama_daily_frames, ignore_index=True) if all_drama_daily_frames else pd.DataFrame()
    raw_ad_daily = pd.concat(all_ad_daily_frames, ignore_index=True, sort=False) if all_ad_daily_frames else pd.DataFrame()
'''
new = '''    raw_catalog = pd.concat(all_catalog_frames, ignore_index=True) if all_catalog_frames else pd.DataFrame()
    raw_drama_daily = pd.concat(all_drama_daily_frames, ignore_index=True) if all_drama_daily_frames else pd.DataFrame()
    raw_ad_daily = pd.concat(all_ad_daily_frames, ignore_index=True, sort=False) if all_ad_daily_frames else pd.DataFrame()
    raw_overall_daily = pd.concat(all_overall_daily_frames, ignore_index=True, sort=False) if all_overall_daily_frames else pd.DataFrame()
'''
if old not in text:
    raise SystemExit("找不到 raw concat 块，请手动检查脚本。")
text = text.replace(old, new, 1)

marker = '''    match_report = make_match_report(catalog, drama_daily, ad_daily)
'''
insert = '''    overall_daily = (
        normalize_overall_daily(raw_overall_daily)
        if not raw_overall_daily.empty
        else pd.DataFrame()
    )

'''
if marker not in text:
    raise SystemExit("找不到 match_report 位置，请手动检查脚本。")
text = text.replace(marker, insert + marker, 1)

old = '''    write_csv(ad_daily, output_dir / "kuaishou_ad_account_daily_stats.csv")
    write_csv(match_report, output_dir / "kuaishou_title_match_report.csv")
'''
new = '''    write_csv(ad_daily, output_dir / "kuaishou_ad_account_daily_stats.csv")
    write_csv(overall_daily, output_dir / "kuaishou_overall_daily_stats.csv")
    write_csv(match_report, output_dir / "kuaishou_title_match_report.csv")
'''
if old not in text:
    raise SystemExit("找不到 write_csv 块，请手动检查脚本。")
text = text.replace(old, new, 1)

old = '''        "ad_account_daily_rows": int(len(ad_daily)),
        "match_report_rows": int(len(match_report)),
'''
new = '''        "ad_account_daily_rows": int(len(ad_daily)),
        "overall_daily_rows": int(len(overall_daily)),
        "match_report_rows": int(len(match_report)),
'''
if old not in text:
    raise SystemExit("找不到 summary rows 块，请手动检查脚本。")
text = text.replace(old, new, 1)

old = '''    print(f"[kuaishou] 广告账户日数据行数：{len(ad_daily)}")
    print(f"[kuaishou] 需处理匹配问题行数：{len(match_report)}")
'''
new = '''    print(f"[kuaishou] 广告账户日数据行数：{len(ad_daily)}")
    print(f"[kuaishou] 平台整体日数据行数：{len(overall_daily)}")
    print(f"[kuaishou] 需处理匹配问题行数：{len(match_report)}")
'''
if old not in text:
    raise SystemExit("找不到 print 块，请手动检查脚本。")
text = text.replace(old, new, 1)

p.write_text(text, encoding="utf-8")
print("patched scripts/import_kuaishou_data.py")
