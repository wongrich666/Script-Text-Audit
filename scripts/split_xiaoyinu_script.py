from pathlib import Path
import re
import csv

SRC = Path("data/episode_scripts/小医奴.txt")
OUT_DIR = Path("data/episode_scripts/xiaoyinu")
MAP_PATH = Path("data/tencent_video_normalized/video_script_mapping_xiaoyinu.csv")

CN_NUM = {
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
    "十一": 11, "十二": 12, "十三": 13, "十四": 14, "十五": 15,
    "十六": 16, "十七": 17, "十八": 18, "十九": 19, "二十": 20,
    "二十一": 21, "二十二": 22, "二十三": 23, "二十四": 24, "二十五": 25,
    "二十六": 26, "二十七": 27, "二十八": 28, "二十九": 29, "三十": 30,
}

def read_text_auto(path: Path) -> str:
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            pass
    raise RuntimeError(f"无法识别文本编码：{path}")

def episode_no(raw: str) -> int:
    raw = raw.strip()
    if raw.isdigit():
        return int(raw)
    if raw in CN_NUM:
        return CN_NUM[raw]
    if raw.startswith("十") and len(raw) == 2:
        return 10 + CN_NUM[raw[1]]
    if "十" in raw:
        left, right = raw.split("十", 1)
        return CN_NUM[left] * 10 + (CN_NUM[right] if right else 0)
    raise ValueError(f"无法解析集数：{raw}")

def clean_content(s: str) -> str:
    lines = []
    for line in s.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        t = line.strip()
        if t == "星动数娱":
            continue
        if t.startswith("### Part"):
            continue
        if t.startswith("````") or t.startswith("```"):
            continue
        lines.append(line)
    return "\n".join(lines).strip() + "\n"

def main() -> int:
    if not SRC.exists():
        print(f"找不到输入文件：{SRC}")
        return 1

    text = read_text_auto(SRC).replace("\r\n", "\n").replace("\r", "\n")

    pattern = re.compile(
        r"(?m)^第\s*([一二三四五六七八九十百零〇0-9]+)\s*集\s*[：:]\s*【([^】]+)】[^\n]*"
    )
    matches = list(pattern.finditer(text))

    print("识别到分集数:", len(matches))
    if not matches:
        print("没有识别到分集标题，请检查标题格式。")
        return 2

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    MAP_PATH.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    lengths = []

    for idx, m in enumerate(matches):
        no = episode_no(m.group(1))
        title = m.group(2).strip()
        start = m.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        content = clean_content(text[start:end])

        script_name = f"小医奴_{no:02d}.txt"
        script_file = OUT_DIR / script_name
        script_file.write_text(content, encoding="utf-8")

        video_title = f"小医奴{no:02d}"
        rows.append({
            "video_title": video_title,
            "episode_no": no,
            "script_file": str(script_file).replace("\\", "/"),
            "script_episode_title": title,
            "source_project": "小医奴",
            "note": "auto_split_from_full_script",
        })
        lengths.append((script_name, len(content), title))

    rows.sort(key=lambda x: int(x["episode_no"]))

    with MAP_PATH.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "video_title",
                "episode_no",
                "script_file",
                "script_episode_title",
                "source_project",
                "note",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    print("输出目录:", OUT_DIR)
    print("映射表:", MAP_PATH)
    print("输出文件数:", len(list(OUT_DIR.glob("小医奴_*.txt"))))
    print("每集字数:")
    for name, n, title in lengths:
        print(name, n, title)

    expected = {f"小医奴_{i:02d}.txt" for i in range(1, len(matches) + 1)}
    actual = {p.name for p in OUT_DIR.glob("小医奴_*.txt")}
    missing = sorted(expected - actual)
    print("缺失:", missing)

    if missing:
        return 3

    print("小医奴切割完成。")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
