from pathlib import Path
import importlib.util
import sys

import pandas as pd


def load_module():
    module_path = Path("scripts/import_juchacha_ranking_images.py")
    module_name = "import_juchacha_ranking_images"

    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)

    assert spec is not None
    assert spec.loader is not None

    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_parse_image_meta_from_standard_filename():
    mod = load_module()

    meta = mod.parse_image_meta(Path("2026-05-13_快手_热播日榜.png"))

    assert meta.ranking_date == "2026-05-13"
    assert meta.ranking_platform == "快手"
    assert meta.ranking_name == "热播日榜"
    assert meta.page_no == "1"


def test_parse_image_meta_from_standard_filename_with_page():
    mod = load_module()

    meta = mod.parse_image_meta(Path("2026-05-13_红果_热播日榜_02.png"))

    assert meta.ranking_date == "2026-05-13"
    assert meta.ranking_platform == "红果"
    assert meta.ranking_name == "热播日榜"
    assert meta.page_no == "02"


def test_select_latest_images_and_skip_existing(tmp_path):
    mod = load_module()

    raw = tmp_path / "raw"
    raw.mkdir()

    old_img = raw / "2026-05-12_快手_热播日榜.png"
    latest_img = raw / "2026-05-13_快手_热播日榜.png"
    latest_img_2 = raw / "2026-05-13_抖音_热播日榜.png"

    old_img.write_text("fake", encoding="utf-8")
    latest_img.write_text("fake", encoding="utf-8")
    latest_img_2.write_text("fake", encoding="utf-8")

    selected, info = mod.select_images_to_process(
        [old_img, latest_img, latest_img_2],
        "latest",
        tmp_path / "missing_final.csv",
        include_existing=False,
    )

    assert set(p.name for p in selected) == {
        "2026-05-13_快手_热播日榜.png",
        "2026-05-13_抖音_热播日榜.png",
    }
    assert info["target_date"] == "2026-05-13"
    assert info["skipped_by_date_count"] == 1


def test_select_images_skips_existing_final_rows(tmp_path):
    mod = load_module()

    raw = tmp_path / "raw"
    raw.mkdir()

    img = raw / "2026-05-13_快手_热播日榜.png"
    img.write_text("fake", encoding="utf-8")

    final = tmp_path / "juchacha_rankings.csv"
    pd.DataFrame(
        [
            {
                "ranking_date": "2026-05-13",
                "ranking_platform": "快手",
                "ranking_name": "热播日榜",
                "page_no": "1",
                "rank": "1",
                "drama_title": "测试剧",
            }
        ]
    ).to_csv(final, index=False, encoding="utf-8-sig")

    selected, info = mod.select_images_to_process(
        [img],
        "latest",
        final,
        include_existing=False,
    )

    assert selected == []
    assert info["skipped_existing_count"] == 1

    selected_force, _ = mod.select_images_to_process(
        [img],
        "latest",
        final,
        include_existing=True,
    )

    assert selected_force == [img]
