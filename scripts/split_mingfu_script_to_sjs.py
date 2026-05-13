from pathlib import Path
import re
import csv
import sys

SRC = Path("data/episode_scripts/冥府审计师.txt")
OUT_DIR = Path("data/episode_scripts")
MAP_PATH = Path("data/tencent_video_normalized/video_script_mapping.csv")
SETTING_PATH = OUT_DIR / "冥府审计师_项目设定.txt"

def read_text_auto(path: Path) -> str:
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    raise RuntimeError(f"无法识别文本编码：{path}")

def main() -> int:
    if not SRC.exists():
        print(f"找不到输入文件：{SRC}")
        print("请确认完整剧本文件已经放在 data/episode_scripts/冥府审计师.txt")
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    MAP_PATH.parent.mkdir(parents=True, exist_ok=True)

    text = read_text_auto(SRC)
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    pattern = re.compile(r"(?m)^第\s*(\d+)\s*集\s*[：:]\s*【([^】]+)】[^\n]*")
    matches = list(pattern.finditer(text))

    print("识别到分集数:", len(matches))
    if len(matches) != 27:
        print("识别到的分集标题如下：")
        for m in matches:
            print(f"第 {int(m.group(1)):02d} 集：{m.group(2).strip()}")
        print("分集数不是 27，已停止，避免错误切割。")
        return 2

    project_setting = text[:matches[0].start()].strip() + "\n"
    SETTING_PATH.write_text(project_setting, encoding="utf-8")

    rows = []
    lengths = []
    for idx, m in enumerate(matches):
        episode_no = int(m.group(1))
        title = m.group(2).strip()
        start = m.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        content = text[start:end].strip() + "\n"

        sjs = f"SJS_{episode_no:02d}"
        script_file = OUT_DIR / f"{sjs}.txt"
        script_file.write_text(content, encoding="utf-8")

        lengths.append((sjs, len(content), title))
        rows.append({
            "video_title": sjs,
            "episode_no": episode_no,
            "script_file": str(script_file).replace("\\", "/"),
            "script_episode_title": title,
            "source_project": "冥府审计师",
            "note": "auto_split_from_full_script",
        })

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

    expected = [f"SJS_{i:02d}.txt" for i in range(1, 28)]
    missing = [name for name in expected if not (OUT_DIR / name).exists()]

    print("输出 SJS 文件数:", len(list(OUT_DIR.glob("SJS_*.txt"))))
    print("缺失:", missing)
    print("项目设定文件:", SETTING_PATH)
    print("映射表:", MAP_PATH)
    print("每集字数：")
    for sjs, n, title in lengths:
        print(f"{sjs} {n} {title}")

    if missing:
        print("存在缺失 SJS 文件，请检查。")
        return 3

    print("切割完成。")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
