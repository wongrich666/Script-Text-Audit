from pathlib import Path
import pandas as pd

p = Path("data/external_benchmark/juchacha_normalized/juchacha_rankings_draft.csv")
backup = Path("data/external_benchmark/juchacha_normalized/juchacha_rankings_draft.before_manual_fix.csv")

df = pd.read_csv(p, encoding="utf-8-sig", dtype=str).fillna("")
df.to_csv(backup, index=False, encoding="utf-8-sig")

def mask(platform=None, rank=None, title_contains=None):
    m = pd.Series([True] * len(df), index=df.index)
    if platform is not None:
        m &= df["ranking_platform"].astype(str).eq(platform)
    if rank is not None:
        m &= pd.to_numeric(df["rank"], errors="coerce").eq(int(rank))
    if title_contains is not None:
        m &= df["drama_title"].astype(str).str.contains(title_contains, regex=False, na=False)
    return m

# 漫剧 / 真人AI：NEW 混进集数，修成 42
df.loc[mask(platform="漫剧", rank=13), "episode_count"] = "42"
df.loc[mask(platform="真人AI", rank=11), "episode_count"] = "42"

# 真人AI 第30：OCR 把“凑”识别错
df.loc[mask(platform="真人AI", rank=30), "drama_title"] = "彩礼不够，脸皮来凑"
df.loc[mask(platform="真人AI", rank=30), "episode_count"] = "60"

# 红果第1：连续霸榜标签混进集数
df.loc[mask(platform="红果", rank=1), "episode_count"] = "119"

# 红果：八零安晴应该是第9，不是第6
df.loc[mask(platform="红果", title_contains="八零安晴"), "rank"] = "9"
df.loc[mask(platform="红果", title_contains="八零安晴"), "episode_count"] = "102"

# 红果第28：集数漏识别
df.loc[mask(platform="红果", rank=28), "episode_count"] = "59"

# 把明显的 NEW 从 episode_count 里去掉
df["episode_count"] = (
    df["episode_count"]
    .astype(str)
    .str.replace("NEW", "", regex=False)
    .str.strip()
)

df.loc[df["episode_count"].isin(["nan", "None", "NaN"]), "episode_count"] = ""

# 这批先全部标记 confirmed
df["review_status"] = "confirmed"

# 排序前把 rank 临时转数字，避免 1,10,11 排在 2 前面
df["_rank_num"] = pd.to_numeric(df["rank"], errors="coerce")
df = df.sort_values(
    ["ranking_date", "ranking_platform", "ranking_name", "page_no", "_rank_num"],
    ascending=[True, True, True, True, True],
    kind="stable",
).drop(columns=["_rank_num"])

df.to_csv(p, index=False, encoding="utf-8-sig")

print("fixed draft:", p)
print("backup:", backup)
print("rows:", len(df))
