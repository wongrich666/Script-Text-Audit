from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any


CN_NUM = {
    "零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
}


def chinese_to_int(s: str) -> int | None:
    s = re.sub(r"\s+", "", s)
    if not s:
        return None
    if s.isdigit():
        return int(s)

    total = 0

    if "百" in s:
        left, _, right = s.partition("百")
        total += (CN_NUM.get(left, 1) if left else 1) * 100
        if right:
            total += chinese_to_int(right) or 0
        return total

    if "十" in s:
        left, _, right = s.partition("十")
        total += (CN_NUM.get(left, 1) if left else 1) * 10
        if right:
            total += CN_NUM.get(right, 0)
        return total

    value = 0
    for ch in s:
        if ch not in CN_NUM:
            return None
        value = value * 10 + CN_NUM[ch]
    return value


def read_text_auto(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\ufeff", "")
    text = text.replace("\u3000", " ")
    return text


def sanitize_filename(name: str, max_len: int = 50) -> str:
    name = re.sub(r'[\\/:*?"<>|]', "", str(name or ""))
    name = re.sub(r"\s+", "", name)
    name = name.strip(". ")
    return name[:max_len] or "未命名"


HEADER_RE = re.compile(
    r"(?P<header>"
    r"(?:第\s*(?P<num1>\d{1,3}|[零〇一二两三四五六七八九十百]+)\s*集|(?P<num2>[零〇一二两三四五六七八九十百]+)\s*集)"
    r"(?:\s*（[^）\n]{1,30}）)?"
    r"(?:\s*EPISODE\s*(?P<epnum>\d{1,3}))?"
    r"(?:\s*[：:【][^\n]{0,80})?"
    r")",
    re.IGNORECASE,
)


@dataclass
class Header:
    episode_no: int
    start: int
    end: int
    header: str
    title: str
    line_no: int
    inline: bool
    markdown_prefix: bool


def line_prefix(text: str, pos: int) -> str:
    line_start = text.rfind("\n", 0, pos) + 1
    return text[line_start:pos]


def line_no(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def is_heading_context(text: str, match: re.Match[str]) -> tuple[bool, bool, bool]:
    start = match.start("header")
    prefix = line_prefix(text, start)
    stripped = prefix.strip()

    if stripped == "":
        return True, False, False

    if re.fullmatch(r"[`#>*\-_\s]+", stripped):
        return True, False, True

    before = text[max(0, start - 8):start]
    if re.search(r'[。！？!?」』”"\）\)]\s*$', before):
        return True, True, False

    return False, False, False


def extract_title(header: str) -> str:
    m = re.search(r"【([^】]+)】", header)
    if m:
        return m.group(1).strip()
    header = re.sub(r"^\s*[`#>*\-_\s]*", "", header)
    return header.strip()


def detect_headers(text: str) -> list[Header]:
    headers: list[Header] = []
    seen_positions = set()

    for m in HEADER_RE.finditer(text):
        ok, inline, md_prefix = is_heading_context(text, m)
        if not ok:
            continue

        token = m.group("epnum") or m.group("num1") or m.group("num2")
        ep_no = chinese_to_int(token)

        if ep_no is None or ep_no <= 0 or ep_no > 300:
            continue

        start = m.start("header")
        if start in seen_positions:
            continue
        seen_positions.add(start)

        raw = m.group("header").strip()

        headers.append(
            Header(
                episode_no=ep_no,
                start=start,
                end=m.end("header"),
                header=raw,
                title=extract_title(raw),
                line_no=line_no(text, start),
                inline=inline,
                markdown_prefix=md_prefix or raw.startswith("`"),
            )
        )

    headers.sort(key=lambda h: h.start)
    return headers


def write_utf8(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.strip() + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow(row)


def split_one_file(
    path: Path,
    root: Path,
    output_root: Path,
    report_rows: list[dict[str, Any]],
    issue_rows: list[dict[str, Any]],
) -> None:
    text = clean_text(read_text_auto(path))
    rel = path.relative_to(root)
    script_title = path.parent.name if path.parent != root else path.stem
    out_dir = output_root / script_title
    out_dir.mkdir(parents=True, exist_ok=True)

    headers = detect_headers(text)

    with (out_dir / "_detected_episode_markers.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["episode_no", "line_no", "inline", "markdown_prefix", "header"])
        w.writeheader()
        for h in headers:
            w.writerow(
                {
                    "episode_no": h.episode_no,
                    "line_no": h.line_no,
                    "inline": h.inline,
                    "markdown_prefix": h.markdown_prefix,
                    "header": h.header,
                }
            )

    if not headers:
        issue_rows.append(
            {
                "source_file": str(rel),
                "script_title": script_title,
                "issue_type": "no_episode_marker",
                "severity": "error",
                "detail": "没有识别到分集标题，未切割。",
            }
        )
        return

    preamble = text[:headers[0].start].strip()
    if preamble:
        write_utf8(out_dir / "00_前置信息_人设大纲等.txt", preamble)
        issue_rows.append(
            {
                "source_file": str(rel),
                "script_title": script_title,
                "issue_type": "preamble_saved",
                "severity": "info",
                "detail": f"首个分集前有 {len(preamble)} 字，已保存为 00_前置信息_人设大纲等.txt。",
            }
        )

    nums = [h.episode_no for h in headers]

    duplicates = sorted({n for n in nums if nums.count(n) > 1})
    for n in duplicates:
        issue_rows.append(
            {
                "source_file": str(rel),
                "script_title": script_title,
                "issue_type": "duplicate_episode_no",
                "severity": "error",
                "detail": f"第 {n} 集出现多次，需要人工检查。",
            }
        )

    expected = set(range(min(nums), max(nums) + 1))
    missing = sorted(expected - set(nums))
    if missing:
        issue_rows.append(
            {
                "source_file": str(rel),
                "script_title": script_title,
                "issue_type": "missing_episode_no",
                "severity": "warning",
                "detail": "缺失集数：" + ",".join(str(x) for x in missing),
            }
        )

    for h in headers:
        if h.inline:
            issue_rows.append(
                {
                    "source_file": str(rel),
                    "script_title": script_title,
                    "issue_type": "inline_episode_marker",
                    "severity": "info",
                    "detail": f"第 {h.episode_no} 集标题在正文同一行出现，脚本已按标题位置切开。line={h.line_no} header={h.header}",
                }
            )
        if h.markdown_prefix:
            issue_rows.append(
                {
                    "source_file": str(rel),
                    "script_title": script_title,
                    "issue_type": "markdown_or_garbage_prefix",
                    "severity": "info",
                    "detail": f"第 {h.episode_no} 集标题前有反引号/Markdown/杂符，脚本已容忍。line={h.line_no} header={h.header}",
                }
            )

    for idx, h in enumerate(headers):
        next_start = headers[idx + 1].start if idx + 1 < len(headers) else len(text)
        episode_text = text[h.start:next_start].strip()

        title_part = sanitize_filename(h.title)
        out_path = out_dir / f"第{h.episode_no:02d}集_{title_part}.txt"
        write_utf8(out_path, episode_text)

        status = "ok"
        if len(episode_text) < 200:
            status = "too_short"
            issue_rows.append(
                {
                    "source_file": str(rel),
                    "script_title": script_title,
                    "issue_type": "episode_too_short",
                    "severity": "warning",
                    "detail": f"第 {h.episode_no} 集正文偏短，仅 {len(episode_text)} 字。output={out_path}",
                }
            )

        report_rows.append(
            {
                "source_file": str(rel),
                "script_title": script_title,
                "episode_no": h.episode_no,
                "line_no": h.line_no,
                "title": h.title,
                "char_count": len(episode_text),
                "status": status,
                "inline": h.inline,
                "markdown_prefix": h.markdown_prefix,
                "header": h.header,
                "output_file": str(out_path),
            }
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/episode_scripts")
    parser.add_argument("--output", default="data/episode_scripts_split")
    parser.add_argument("--clean-output", action="store_true")
    args = parser.parse_args()

    root = Path(args.input)
    output_root = Path(args.output)

    if args.clean_output and output_root.exists():
        shutil.rmtree(output_root)

    files = sorted([p for p in root.rglob("*.txt") if p.is_file()])

    report_rows: list[dict[str, Any]] = []
    issue_rows: list[dict[str, Any]] = []

    if not files:
        issue_rows.append(
            {
                "source_file": "",
                "script_title": "",
                "issue_type": "no_txt_files",
                "severity": "error",
                "detail": f"输入目录没有找到 txt 文件：{root}",
            }
        )

    for path in files:
        print(f"[split] {path}")
        split_one_file(path, root, output_root, report_rows, issue_rows)

    write_csv(
        output_root / "_episode_split_report.csv",
        report_rows,
        [
            "source_file",
            "script_title",
            "episode_no",
            "line_no",
            "title",
            "char_count",
            "status",
            "inline",
            "markdown_prefix",
            "header",
            "output_file",
        ],
    )

    write_csv(
        output_root / "_episode_split_issues.csv",
        issue_rows,
        ["source_file", "script_title", "issue_type", "severity", "detail"],
    )

    summary = {
        "input": str(root),
        "output": str(output_root),
        "txt_file_count": len(files),
        "episode_count": len(report_rows),
        "issue_count": len(issue_rows),
        "episodes_by_script": {},
        "issues_by_type": {},
    }

    for row in report_rows:
        summary["episodes_by_script"].setdefault(row["script_title"], 0)
        summary["episodes_by_script"][row["script_title"]] += 1

    for row in issue_rows:
        summary["issues_by_type"].setdefault(row["issue_type"], 0)
        summary["issues_by_type"][row["issue_type"]] += 1

    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "_episode_split_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("")
    print("[split] 完成")
    print(f"[split] txt 文件数：{len(files)}")
    print(f"[split] 切出分集数：{len(report_rows)}")
    print(f"[split] 问题/提示数：{len(issue_rows)}")
    print(f"[split] 输出目录：{output_root}")
    print(f"[split] 报告：{output_root / '_episode_split_report.csv'}")
    print(f"[split] 问题：{output_root / '_episode_split_issues.csv'}")


if __name__ == "__main__":
    main()
