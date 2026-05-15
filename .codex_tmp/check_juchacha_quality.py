from pathlib import Path
import pandas as pd

draft_path = Path("data/external_benchmark/juchacha_normalized/juchacha_rankings_draft.csv")
out_path = Path("data/external_benchmark/juchacha_normalized/juchacha_rankings_quality_issues.csv")

df = pd.read_csv(draft_path, encoding="utf-8-sig")

issues = []

group_cols = ["ranking_date", "ranking_platform", "ranking_name", "page_no"]

for key, g in df.groupby(group_cols, dropna=False):
    ranking_date, platform, ranking_name, page_no = key

    ranks = pd.to_numeric(g["rank"], errors="coerce")
    rank_list = [int(x) for x in ranks.dropna().tolist()]

    duplicates = sorted(set([x for x in rank_list if rank_list.count(x) > 1]))
    missing = sorted(set(range(1, 31)) - set(rank_list))

    for r in duplicates:
        issues.append({
            "issue_type": "duplicate_rank",
            "ranking_date": ranking_date,
            "ranking_platform": platform,
            "ranking_name": ranking_name,
            "page_no": page_no,
            "rank": r,
            "detail": f"重复排名：{r}",
        })

    for r in missing:
        issues.append({
            "issue_type": "missing_rank",
            "ranking_date": ranking_date,
            "ranking_platform": platform,
            "ranking_name": ranking_name,
            "page_no": page_no,
            "rank": r,
            "detail": f"缺失排名：{r}",
        })

for _, row in df.iterrows():
    title = str(row.get("drama_title", ""))
    ep = str(row.get("episode_count", ""))
    heat = str(row.get("heat_text", ""))

    if not title.strip():
        issues.append({
            "issue_type": "empty_title",
            "ranking_date": row.get("ranking_date", ""),
            "ranking_platform": row.get("ranking_platform", ""),
            "ranking_name": row.get("ranking_name", ""),
            "page_no": row.get("page_no", ""),
            "rank": row.get("rank", ""),
            "detail": "剧名为空",
        })

    if any(x in title for x in ["(", "（", ")", "）"]) or title.endswith(".") or "  " in title:
        issues.append({
            "issue_type": "title_noise",
            "ranking_date": row.get("ranking_date", ""),
            "ranking_platform": row.get("ranking_platform", ""),
            "ranking_name": row.get("ranking_name", ""),
            "page_no": row.get("page_no", ""),
            "rank": row.get("rank", ""),
            "detail": f"剧名疑似有 OCR 噪声：{title}",
        })

    if ep and not ep.isdigit():
        issues.append({
            "issue_type": "episode_count_not_number",
            "ranking_date": row.get("ranking_date", ""),
            "ranking_platform": row.get("ranking_platform", ""),
            "ranking_name": row.get("ranking_name", ""),
            "page_no": row.get("page_no", ""),
            "rank": row.get("rank", ""),
            "detail": f"集数不是数字：{ep}",
        })

    if not str(heat).strip():
        issues.append({
            "issue_type": "empty_heat_text",
            "ranking_date": row.get("ranking_date", ""),
            "ranking_platform": row.get("ranking_platform", ""),
            "ranking_name": row.get("ranking_name", ""),
            "page_no": row.get("page_no", ""),
            "rank": row.get("rank", ""),
            "detail": "热度/播放字段为空",
        })

issues_df = pd.DataFrame(issues)
issues_df.to_csv(out_path, index=False, encoding="utf-8-sig")

print(f"quality issues: {len(issues_df)}")
print(f"output: {out_path}")
if not issues_df.empty:
    print(issues_df.groupby("issue_type").size())
