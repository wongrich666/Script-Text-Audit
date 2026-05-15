from pathlib import Path

p = Path("scripts/import_juchacha_ranking_images.py")
text = p.read_text(encoding="utf-8")

text = text.replace(
    "from datetime import datetime\n",
    "from datetime import datetime, timedelta\n",
    1,
)

insert_after = '''def parse_image_meta(path: Path) -> ImageMeta:
    """
    推荐文件名：
    2026-05-14_快手_热播日榜_01.png
    2026-05-13_红果_热播日榜.png
    """
    stem = path.stem.strip()

    date = ""
    rest = stem

    m = re.match(r"^(20\\d{2})[-_.年]?(\\d{1,2})[-_.月]?(\\d{1,2})[日]?[_\\-\\s]*(.*)$", stem)
    if m:
        y, mo, d, rest = m.groups()
        date = f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"

    parts = [p.strip() for p in re.split(r"_+", rest) if p.strip()]

    page_no = "1"
    if parts and re.fullmatch(r"\\d{1,3}", parts[-1]):
        page_no = parts[-1]
        parts = parts[:-1]

    platform = parts[0] if parts else "unknown_platform"
    ranking_name = "_".join(parts[1:]) if len(parts) > 1 else "unknown_ranking"

    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    return ImageMeta(date, platform, ranking_name, page_no)
'''

helper = r'''

def parse_date_arg(value: str, image_files: list[Path]) -> str | None:
    value = clean_text(value).lower()

    if value in {"", "latest"}:
        dates = []
        for image_path in image_files:
            meta = parse_image_meta(image_path)
            if re.fullmatch(r"20\d{2}-\d{2}-\d{2}", meta.ranking_date):
                dates.append(meta.ranking_date)
        return max(dates) if dates else None

    if value == "all":
        return None

    if value == "today":
        return datetime.now().strftime("%Y-%m-%d")

    if value == "yesterday":
        return (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    if re.fullmatch(r"20\d{2}-\d{2}-\d{2}", value):
        return value

    raise ValueError(
        f"--date 参数不合法：{value}。可用：latest / all / today / yesterday / YYYY-MM-DD"
    )


def processed_keys_from_final(final_path: Path) -> set[tuple[str, str, str, str]]:
    if not final_path.exists():
        return set()

    try:
        df = pd.read_csv(final_path, encoding="utf-8-sig", dtype=str).fillna("")
    except UnicodeDecodeError:
        df = pd.read_csv(final_path, encoding="utf-8", dtype=str).fillna("")

    required = ["ranking_date", "ranking_platform", "ranking_name", "page_no"]
    for col in required:
        if col not in df.columns:
            return set()

    keys = set()
    for _, row in df.iterrows():
        keys.add(
            (
                clean_text(row.get("ranking_date", "")),
                clean_text(row.get("ranking_platform", "")),
                clean_text(row.get("ranking_name", "")),
                clean_text(row.get("page_no", "")) or "1",
            )
        )

    return keys


def select_images_to_process(
    image_files: list[Path],
    date_arg: str,
    final_path: Path,
    include_existing: bool,
) -> tuple[list[Path], dict[str, Any]]:
    target_date = parse_date_arg(date_arg, image_files)
    processed_keys = processed_keys_from_final(final_path) if not include_existing else set()

    selected: list[Path] = []
    skipped_by_date: list[str] = []
    skipped_existing: list[str] = []

    for image_path in image_files:
        meta = parse_image_meta(image_path)

        if target_date is not None and meta.ranking_date != target_date:
            skipped_by_date.append(str(image_path))
            continue

        key = (
            meta.ranking_date,
            meta.ranking_platform,
            meta.ranking_name,
            meta.page_no,
        )

        if key in processed_keys:
            skipped_existing.append(str(image_path))
            continue

        selected.append(image_path)

    info = {
        "date_arg": date_arg,
        "target_date": target_date or "all",
        "input_image_count": len(image_files),
        "selected_image_count": len(selected),
        "skipped_by_date_count": len(skipped_by_date),
        "skipped_existing_count": len(skipped_existing),
        "skipped_by_date": skipped_by_date,
        "skipped_existing": skipped_existing,
    }

    return selected, info
'''

if insert_after not in text:
    raise SystemExit("找不到 parse_image_meta 函数块，补丁停止。")

text = text.replace(insert_after, insert_after + helper, 1)

old_args = '''    parser.add_argument("--input", default="data/external_benchmark/juchacha_images/raw")
    parser.add_argument("--output", default="data/external_benchmark/juchacha_normalized")
    parser.add_argument("--raw-output", default="data/external_benchmark/juchacha_raw_ocr")
    args = parser.parse_args()
'''

new_args = '''    parser.add_argument("--input", default="data/external_benchmark/juchacha_images/raw")
    parser.add_argument("--output", default="data/external_benchmark/juchacha_normalized")
    parser.add_argument("--raw-output", default="data/external_benchmark/juchacha_raw_ocr")
    parser.add_argument(
        "--date",
        default="latest",
        help="处理日期：latest / all / today / yesterday / YYYY-MM-DD。默认 latest，只处理 raw 目录里最新榜单日期。",
    )
    parser.add_argument(
        "--final",
        default="",
        help="正式榜单表路径，用于判断是否重复处理。默认 output/juchacha_rankings.csv。",
    )
    parser.add_argument(
        "--include-existing",
        action="store_true",
        help="默认跳过正式表里已存在的同日期/平台/榜单/页码图片；加此参数会强制重新 OCR。",
    )
    args = parser.parse_args()
'''

if old_args not in text:
    raise SystemExit("找不到 argparse 参数块，补丁停止。")

text = text.replace(old_args, new_args, 1)

old_image_files = '''    image_files = sorted(
        p for p in input_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES
    )

    all_draft_rows: list[dict[str, Any]] = []
    all_ocr_lines: list[dict[str, Any]] = []
    warnings: list[str] = []
'''

new_image_files = '''    all_image_files = sorted(
        p for p in input_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES
    )

    final_path = Path(args.final) if args.final else output_dir / "juchacha_rankings.csv"

    image_files, selection_info = select_images_to_process(
        all_image_files,
        args.date,
        final_path,
        args.include_existing,
    )

    all_draft_rows: list[dict[str, Any]] = []
    all_ocr_lines: list[dict[str, Any]] = []
    warnings: list[str] = []

    if not image_files:
        summary_path = output_dir / "juchacha_import_summary.json"
        summary = {
            "source_name": SOURCE_NAME,
            "import_batch_id": batch_id,
            "input_dir": str(input_dir),
            "image_count": 0,
            "ocr_line_count": 0,
            "draft_row_count": 0,
            "draft_output": str(output_dir / "juchacha_rankings_draft.csv"),
            "ocr_lines_output": str(raw_output_dir / "juchacha_ocr_lines.csv"),
            "final_path_for_skip_check": str(final_path),
            "selection": selection_info,
            "warnings": ["没有需要处理的新图片。旧 draft 文件不会被覆盖。"],
        }
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

        print("[juchacha] 没有需要处理的新图片。")
        print(f"[juchacha] date_arg: {args.date}")
        print(f"[juchacha] target_date: {selection_info.get('target_date')}")
        print(f"[juchacha] input_image_count: {selection_info.get('input_image_count')}")
        print(f"[juchacha] skipped_by_date_count: {selection_info.get('skipped_by_date_count')}")
        print(f"[juchacha] skipped_existing_count: {selection_info.get('skipped_existing_count')}")
        print(f"[juchacha] summary：{summary_path}")
        return
'''

if old_image_files not in text:
    raise SystemExit("找不到 image_files 初始化块，补丁停止。")

text = text.replace(old_image_files, new_image_files, 1)

old_summary = '''        "input_dir": str(input_dir),
        "image_count": len(image_files),
        "ocr_line_count": len(all_ocr_lines),
'''

new_summary = '''        "input_dir": str(input_dir),
        "image_count": len(image_files),
        "all_image_count": len(all_image_files),
        "ocr_line_count": len(all_ocr_lines),
'''

if old_summary not in text:
    raise SystemExit("找不到 summary 第一段，补丁停止。")

text = text.replace(old_summary, new_summary, 1)

old_summary2 = '''        "ocr_lines_output": str(ocr_lines_path),
        "warnings": warnings,
'''

new_summary2 = '''        "ocr_lines_output": str(ocr_lines_path),
        "final_path_for_skip_check": str(final_path),
        "selection": selection_info,
        "warnings": warnings,
'''

if old_summary2 not in text:
    raise SystemExit("找不到 summary 第二段，补丁停止。")

text = text.replace(old_summary2, new_summary2, 1)

old_print = '''    print(f"[juchacha] 图片数：{len(image_files)}")
    print(f"[juchacha] OCR 行数：{len(all_ocr_lines)}")
'''

new_print = '''    print(f"[juchacha] 全部图片数：{len(all_image_files)}")
    print(f"[juchacha] 本次处理图片数：{len(image_files)}")
    print(f"[juchacha] date_arg：{args.date}")
    print(f"[juchacha] target_date：{selection_info.get('target_date')}")
    print(f"[juchacha] 跳过旧日期图片数：{selection_info.get('skipped_by_date_count')}")
    print(f"[juchacha] 跳过已入正式表图片数：{selection_info.get('skipped_existing_count')}")
    print(f"[juchacha] OCR 行数：{len(all_ocr_lines)}")
'''

if old_print not in text:
    raise SystemExit("找不到 print 图片数块，补丁停止。")

text = text.replace(old_print, new_print, 1)

p.write_text(text, encoding="utf-8")
print("patched import_juchacha_ranking_images.py with date filter and skip existing")
