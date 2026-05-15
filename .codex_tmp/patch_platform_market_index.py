from pathlib import Path
import re

p = Path("scripts/build_platform_market_normalized.py")
text = p.read_text(encoding="utf-8")

replacements = {
    "def build_kuaishou_drama_catalog(kuaishou_dir: Path) -> pd.DataFrame:": "df",
    "def build_kuaishou_drama_daily(kuaishou_dir: Path) -> pd.DataFrame:": "df",
    "def build_kuaishou_ad_daily(kuaishou_dir: Path) -> pd.DataFrame:": "df",
    "def build_kuaishou_overall_daily(kuaishou_dir: Path) -> pd.DataFrame:": "df",
    "def build_tencent_episode_daily(tencent_dir: Path) -> pd.DataFrame:": "merged",
    "def build_tencent_drama_daily(tencent_dir: Path) -> pd.DataFrame:": "df",
    "def build_tencent_overall_daily(tencent_dir: Path) -> pd.DataFrame:": "df",
}

for func_sig, index_var in replacements.items():
    start = text.find(func_sig)
    if start == -1:
        raise SystemExit(f"找不到函数：{func_sig}")

    next_func = text.find("\ndef ", start + 1)
    if next_func == -1:
        next_func = len(text)

    block = text[start:next_func]
    old = "    out = pd.DataFrame()\n"
    new = f"    out = pd.DataFrame(index={index_var}.index)\n"

    if old not in block:
        print(f"[skip] {func_sig} 没找到 out = pd.DataFrame()")
        continue

    block = block.replace(old, new, 1)
    text = text[:start] + block + text[next_func:]

p.write_text(text, encoding="utf-8")
print("patched DataFrame index initialization")
