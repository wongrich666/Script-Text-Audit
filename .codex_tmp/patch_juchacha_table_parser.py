from pathlib import Path

p = Path("scripts/import_juchacha_ranking_images.py")
text = p.read_text(encoding="utf-8")

# 1. 扩展 DRAFT_COLUMNS
old = '''DRAFT_COLUMNS = [
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
'''
new = '''DRAFT_COLUMNS = [
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
'''
if old not in text:
    raise SystemExit("找不到 DRAFT_COLUMNS 原始块")
text = text.replace(old, new, 1)

# 2. 替换 parse_image_meta
start = text.index("def parse_image_meta")
end = text.index("\ndef normalize_box", start)

new_parse_image_meta = r'''def parse_image_meta(path: Path) -> ImageMeta:
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
'''
text = text[:start] + new_parse_image_meta + "\n" + text[end + 1:]

# 3. 插入表格坐标解析函数
insert_at = text.index("\ndef write_csv", text.index("def parse_visual_rows_to_rankings"))

table_parser = r'''
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
'''
text = text[:insert_at] + "\n\n" + table_parser + text[insert_at:]

# 4. main 中改用 parse_table_rows_to_rankings
old = '''        visual_rows = group_ocr_lines_to_visual_rows(lines)
        draft_rows = parse_visual_rows_to_rankings(visual_rows, meta, rel_image, batch_id)
        all_draft_rows.extend(draft_rows)
'''
new = '''        draft_rows = parse_table_rows_to_rankings(lines, meta, rel_image, batch_id)
        all_draft_rows.extend(draft_rows)
'''
if old not in text:
    raise SystemExit("找不到 visual_rows 解析块")
text = text.replace(old, new, 1)

p.write_text(text, encoding="utf-8")
print("patched juchacha image importer with coordinate table parser")
