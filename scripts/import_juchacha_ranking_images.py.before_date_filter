from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


SOURCE_NAME = "剧查查"


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


DRAFT_COLUMNS = [
    "source_name",
    "ranking_date",
    "ranking_platform",
    "ranking_name",
    "page_no",
    "rank",
    "drama_title",
    "episode_count",
    "theater_name",
    "producer_name",
    "play_increment_text",
    "total_play_text",
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


OCR_LINE_COLUMNS = [
    "source_image",
    "ranking_date",
    "ranking_platform",
    "ranking_name",
    "page_no",
    "line_no",
    "text",
    "confidence",
    "x1",
    "y1",
    "x2",
    "y2",
    "cx",
    "cy",
    "raw_box",
    "import_batch_id",
]


@dataclass
class ImageMeta:
    ranking_date: str
    ranking_platform: str
    ranking_name: str
    page_no: str


def now_batch_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    text = text.replace("\u00a0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_image_meta(path: Path) -> ImageMeta:
    """
    推荐文件名：
    2026-05-14_快手_热播日榜_01.png
    2026-05-13_红果_热播日榜.png
    """
    stem = path.stem.strip()

    date = ""
    rest = stem

    m = re.match(r"^(20\d{2})[-_.年]?(\d{1,2})[-_.月]?(\d{1,2})[日]?[_\-\s]*(.*)$", stem)
    if m:
        y, mo, d, rest = m.groups()
        date = f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"

    parts = [p.strip() for p in re.split(r"_+", rest) if p.strip()]

    page_no = "1"
    if parts and re.fullmatch(r"\d{1,3}", parts[-1]):
        page_no = parts[-1]
        parts = parts[:-1]

    platform = parts[0] if parts else "unknown_platform"
    ranking_name = "_".join(parts[1:]) if len(parts) > 1 else "unknown_ranking"

    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    return ImageMeta(date, platform, ranking_name, page_no)

def normalize_box(box: Any) -> tuple[float, float, float, float, float, float]:
    """
    RapidOCR box 通常是四点坐标：
    [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
    """
    try:
        xs = [float(p[0]) for p in box]
        ys = [float(p[1]) for p in box]
        x1, x2 = min(xs), max(xs)
        y1, y2 = min(ys), max(ys)
        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2
        return x1, y1, x2, y2, cx, cy
    except Exception:
        return 0, 0, 0, 0, 0, 0


def run_ocr(image_path: Path) -> list[dict[str, Any]]:
    try:
        from rapidocr_onnxruntime import RapidOCR
    except Exception as exc:
        raise RuntimeError(
            "未安装 rapidocr_onnxruntime。请先运行：python -m pip install rapidocr-onnxruntime"
        ) from exc

    engine = RapidOCR()
    result, _ = engine(str(image_path))

    rows: list[dict[str, Any]] = []
    if not result:
        return rows

    for idx, item in enumerate(result, start=1):
        try:
            box = item[0]
            text = clean_text(item[1])
            conf = float(item[2]) if len(item) >= 3 else ""
        except Exception:
            continue

        if not text:
            continue

        x1, y1, x2, y2, cx, cy = normalize_box(box)
        rows.append(
            {
                "line_no": idx,
                "text": text,
                "confidence": conf,
                "x1": round(x1, 2),
                "y1": round(y1, 2),
                "x2": round(x2, 2),
                "y2": round(y2, 2),
                "cx": round(cx, 2),
                "cy": round(cy, 2),
                "raw_box": json.dumps(box, ensure_ascii=False),
            }
        )

    return rows


def group_ocr_lines_to_visual_rows(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not lines:
        return []

    sorted_lines = sorted(lines, key=lambda r: (float(r.get("cy", 0)), float(r.get("x1", 0))))
    heights = [
        max(1.0, float(r.get("y2", 0)) - float(r.get("y1", 0)))
        for r in sorted_lines
    ]
    avg_height = sum(heights) / len(heights)
    threshold = max(14.0, avg_height * 0.8)

    groups: list[list[dict[str, Any]]] = []

    for line in sorted_lines:
        cy = float(line.get("cy", 0))
        placed = False
        for group in groups:
            group_cy = sum(float(x.get("cy", 0)) for x in group) / len(group)
            if abs(cy - group_cy) <= threshold:
                group.append(line)
                placed = True
                break
        if not placed:
            groups.append([line])

    visual_rows = []
    for group in groups:
        group = sorted(group, key=lambda r: float(r.get("x1", 0)))
        text = " ".join(clean_text(x.get("text", "")) for x in group if clean_text(x.get("text", "")))
        confs = [
            float(x.get("confidence", 0))
            for x in group
            if str(x.get("confidence", "")).strip() != ""
        ]
        avg_conf = sum(confs) / len(confs) if confs else ""
        visual_rows.append(
            {
                "row_text": clean_text(text),
                "ocr_confidence": round(avg_conf, 4) if avg_conf != "" else "",
                "lines": group,
            }
        )

    return visual_rows


def is_noise_row(text: str) -> bool:
    text = clean_text(text)
    if not text:
        return True
    noise_words = [
        "微信", "搜索", "取消", "返回", "分享", "保存", "导出", "日榜", "周榜", "月榜",
        "剧查查", "榜单", "排名", "热度", "更新时间", "数据说明"
    ]
    if text in noise_words:
        return True
    if len(text) <= 1:
        return True
    return False


def extract_rank(text: str) -> str:
    text = clean_text(text)
    m = re.match(r"^(?:TOP\s*)?(\d{1,3})(?:\s|\.|、|：|:|-|$)", text, flags=re.I)
    if m:
        n = int(m.group(1))
        if 1 <= n <= 300:
            return str(n)

    tokens = re.findall(r"\b\d{1,3}\b", text)
    for t in tokens[:2]:
        n = int(t)
        if 1 <= n <= 300:
            return str(n)

    return ""


def extract_heat_text(text: str) -> str:
    text = clean_text(text)
    patterns = [
        r"\d+(?:\.\d+)?\s*[万亿]\s*(?:热度|播放|在追|追更|人气|指数)?",
        r"\d+(?:\.\d+)?\s*(?:热度|播放|在追|追更|人气|指数)",
    ]
    for pattern in patterns:
        matches = re.findall(pattern, text)
        if matches:
            return clean_text(matches[-1])
    return ""


def guess_title(text: str, rank: str, heat_text: str) -> str:
    work = clean_text(text)
    if rank:
        work = re.sub(rf"^(?:TOP\s*)?{re.escape(rank)}(?:\s|\.|、|：|:|-)*", "", work, flags=re.I)
    if heat_text:
        work = work.replace(heat_text, " ")

    work = re.sub(r"\d+(?:\.\d+)?\s*[万亿]?\s*(?:热度|播放|在追|追更|人气|指数)?", " ", work)
    work = re.sub(r"\s+", " ", work).strip()

    # 去掉常见标签，但保留原始 row_text 给人工复核
    for token in ["热播", "飙升", "新剧", "完结", "连载", "短剧", "IAA", "付费"]:
        if work.startswith(token + " "):
            work = work[len(token):].strip()

    # 如果剩下太长，取前半段作为候选剧名
    parts = re.split(r"\s{1,}|[|｜]", work)
    parts = [p.strip() for p in parts if p.strip()]
    if not parts:
        return ""

    # 避免把纯数字/指标当标题
    candidates = [
        p for p in parts
        if not re.fullmatch(r"\d+(?:\.\d+)?[万亿]?", p)
        and len(p) >= 2
    ]
    return candidates[0] if candidates else parts[0]


def parse_visual_rows_to_rankings(
    visual_rows: list[dict[str, Any]],
    meta: ImageMeta,
    source_image: str,
    batch_id: str,
) -> list[dict[str, Any]]:
    out = []

    for row in visual_rows:
        text = clean_text(row.get("row_text", ""))
        if is_noise_row(text):
            continue

        rank = extract_rank(text)
        if not rank:
            continue

        heat_text = extract_heat_text(text)
        title = guess_title(text, rank, heat_text)

        if not title:
            continue

        out.append(
            {
                "source_name": SOURCE_NAME,
                "ranking_date": meta.ranking_date,
                "ranking_platform": meta.ranking_platform,
                "ranking_name": meta.ranking_name,
                "page_no": meta.page_no,
                "rank": rank,
                "drama_title": title,
                "heat_text": heat_text,
                "genre_or_tag": "",
                "publisher_or_account": "",
                "row_text": text,
                "source_image": source_image,
                "ocr_confidence": row.get("ocr_confidence", ""),
                "review_status": "pending",
                "note": "ocr_draft_need_review",
                "import_batch_id": batch_id,
            }
        )

    return out




def is_metric_value(text: str) -> bool:
    text = clean_text(text)
    return bool(re.fullmatch(r"\d+(?:\.\d+)?\s*[wW万亿]", text))


def clean_title_token(text: str) -> str:
    text = clean_text(text)
    text = text.replace("NEW", "").replace("(NEW", "").replace("（NEW", "")
    text = text.replace("首", "").strip()
    return clean_text(text)


def detect_table_header_y(lines: list[dict[str, Any]]) -> float:
    header_keywords = {"排名", "剧名", "集数", "剧场号", "承制方", "播放增量", "播放总量", "热度"}
    candidates = [
        float(line.get("cy", 0))
        for line in lines
        if clean_text(line.get("text", "")) in header_keywords
    ]
    if candidates:
        return sum(candidates) / len(candidates)
    return 300.0


def detect_table_bottom_y(lines: list[dict[str, Any]]) -> float:
    footer_patterns = ["剧查查，做短剧", "数据说明", "官方客服微信", "剧查查小程序"]
    ys = []
    for line in lines:
        text = clean_text(line.get("text", ""))
        if any(p in text for p in footer_patterns):
            ys.append(float(line.get("y1", 0)))
    if ys:
        return min(ys) - 20
    if lines:
        return max(float(line.get("y2", 0)) for line in lines) + 1
    return 99999.0


def group_table_lines_by_row(lines: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    if not lines:
        return []

    header_y = detect_table_header_y(lines)
    bottom_y = detect_table_bottom_y(lines)

    data_lines = [
        line for line in lines
        if float(line.get("cy", 0)) > header_y + 20
        and float(line.get("cy", 0)) < bottom_y
    ]

    data_lines = sorted(data_lines, key=lambda r: (float(r.get("cy", 0)), float(r.get("x1", 0))))

    groups: list[list[dict[str, Any]]] = []
    for line in data_lines:
        cy = float(line.get("cy", 0))
        placed = False
        for group in groups:
            group_cy = sum(float(x.get("cy", 0)) for x in group) / len(group)
            if abs(cy - group_cy) <= 18:
                group.append(line)
                placed = True
                break
        if not placed:
            groups.append([line])

    return [sorted(group, key=lambda r: float(r.get("x1", 0))) for group in groups]


def join_col(group: list[dict[str, Any]], min_cx: float, max_cx: float) -> str:
    parts = [
        clean_text(line.get("text", ""))
        for line in group
        if min_cx <= float(line.get("cx", 0)) <= max_cx
    ]
    return clean_text(" ".join(p for p in parts if p))


def parse_table_rows_to_rankings(
    lines: list[dict[str, Any]],
    meta: ImageMeta,
    source_image: str,
    batch_id: str,
) -> list[dict[str, Any]]:
    groups = group_table_lines_by_row(lines)
    rows: list[dict[str, Any]] = []

    for row_index, group in enumerate(groups, start=1):
        row_text = clean_text(" / ".join(clean_text(x.get("text", "")) for x in group if clean_text(x.get("text", ""))))
        if not row_text:
            continue

        # 标准 DataEye 榜单列位置，按你这批图的 900px 宽版式设计。
        rank_text = join_col(group, 0, 95)
        title = clean_title_token(join_col(group, 95, 330))
        episode_count = join_col(group, 330, 410)
        theater_name = join_col(group, 410, 585)
        producer_name = join_col(group, 585, 705)
        metric_tokens = [
            clean_text(line.get("text", ""))
            for line in group
            if 700 <= float(line.get("cx", 0)) <= 900
            and is_metric_value(clean_text(line.get("text", "")))
        ]

        if not title:
            continue

        # 顶部奖牌行 OCR 通常没有 1/2/3，直接用行序补排名。
        m = re.search(r"\d{1,3}", rank_text)
        rank = int(m.group()) if m and 1 <= int(m.group()) <= 300 else row_index

        play_increment_text = metric_tokens[0] if len(metric_tokens) >= 1 else ""
        total_play_text = metric_tokens[1] if len(metric_tokens) >= 2 else ""
        heat_text = total_play_text or play_increment_text

        # 红果榜没有“剧场号”列，episode_count 有时会被放进 theater_name 区域。
        if meta.ranking_platform == "红果":
            if not episode_count and theater_name and re.fullmatch(r"\d{1,4}", theater_name):
                episode_count, theater_name = theater_name, ""
            if producer_name == "待确认":
                producer_name = ""

        publisher_or_account = producer_name or theater_name

        confs = [
            float(line.get("confidence", 0))
            for line in group
            if str(line.get("confidence", "")).strip() != ""
        ]
        avg_conf = round(sum(confs) / len(confs), 4) if confs else ""

        rows.append(
            {
                "source_name": SOURCE_NAME,
                "ranking_date": meta.ranking_date,
                "ranking_platform": meta.ranking_platform,
                "ranking_name": meta.ranking_name,
                "page_no": meta.page_no,
                "rank": rank,
                "drama_title": title,
                "episode_count": episode_count,
                "theater_name": theater_name,
                "producer_name": producer_name,
                "play_increment_text": play_increment_text,
                "total_play_text": total_play_text,
                "heat_text": heat_text,
                "genre_or_tag": "",
                "publisher_or_account": publisher_or_account,
                "row_text": row_text,
                "source_image": source_image,
                "ocr_confidence": avg_conf,
                "review_status": "pending",
                "note": "ocr_table_draft_need_review",
                "import_batch_id": batch_id,
            }
        )

    # 正常一张图是 30 行，超过时保留前 30 行，避免页脚误入。
    rows = sorted(rows, key=lambda r: int(r["rank"]))
    if len(rows) > 30:
        rows = rows[:30]

    return rows

def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in columns})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/external_benchmark/juchacha_images/raw")
    parser.add_argument("--output", default="data/external_benchmark/juchacha_normalized")
    parser.add_argument("--raw-output", default="data/external_benchmark/juchacha_raw_ocr")
    args = parser.parse_args()

    input_dir = Path(args.input)
    output_dir = Path(args.output)
    raw_output_dir = Path(args.raw_output)

    output_dir.mkdir(parents=True, exist_ok=True)
    raw_output_dir.mkdir(parents=True, exist_ok=True)

    batch_id = now_batch_id()

    image_files = sorted(
        p for p in input_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES
    )

    all_draft_rows: list[dict[str, Any]] = []
    all_ocr_lines: list[dict[str, Any]] = []
    warnings: list[str] = []

    for image_path in image_files:
        print(f"[juchacha] OCR: {image_path}")
        meta = parse_image_meta(image_path)
        rel_image = str(image_path.as_posix())

        try:
            lines = run_ocr(image_path)
        except Exception as exc:
            warnings.append(f"{image_path}: OCR失败：{exc}")
            continue

        for line in lines:
            full_line = {
                "source_image": rel_image,
                "ranking_date": meta.ranking_date,
                "ranking_platform": meta.ranking_platform,
                "ranking_name": meta.ranking_name,
                "page_no": meta.page_no,
                "import_batch_id": batch_id,
                **line,
            }
            all_ocr_lines.append(full_line)

        draft_rows = parse_table_rows_to_rankings(lines, meta, rel_image, batch_id)
        all_draft_rows.extend(draft_rows)

        if not draft_rows:
            warnings.append(f"{image_path}: 未解析出榜单行，请查看 raw OCR。")

    draft_path = output_dir / "juchacha_rankings_draft.csv"
    ocr_lines_path = raw_output_dir / "juchacha_ocr_lines.csv"
    summary_path = output_dir / "juchacha_import_summary.json"

    write_csv(draft_path, all_draft_rows, DRAFT_COLUMNS)
    write_csv(ocr_lines_path, all_ocr_lines, OCR_LINE_COLUMNS)

    summary = {
        "source_name": SOURCE_NAME,
        "import_batch_id": batch_id,
        "input_dir": str(input_dir),
        "image_count": len(image_files),
        "ocr_line_count": len(all_ocr_lines),
        "draft_row_count": len(all_draft_rows),
        "draft_output": str(draft_path),
        "ocr_lines_output": str(ocr_lines_path),
        "warnings": warnings,
    }

    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("")
    print("[juchacha] 导入完成")
    print(f"[juchacha] 图片数：{len(image_files)}")
    print(f"[juchacha] OCR 行数：{len(all_ocr_lines)}")
    print(f"[juchacha] 草稿榜单行数：{len(all_draft_rows)}")
    print(f"[juchacha] 草稿输出：{draft_path}")
    print(f"[juchacha] OCR 原始行输出：{ocr_lines_path}")
    print(f"[juchacha] summary：{summary_path}")

    if warnings:
        print("[juchacha] Warnings:")
        for w in warnings:
            print(f"- {w}")


if __name__ == "__main__":
    main()
