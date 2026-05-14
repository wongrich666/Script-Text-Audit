from pathlib import Path
import importlib.util
import sys

import pandas as pd


def load_module():
    module_path = Path("scripts/build_platform_market_normalized.py")
    module_name = "build_platform_market_normalized"

    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)

    assert spec is not None
    assert spec.loader is not None

    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def write_csv(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8-sig")


def test_build_platform_market_normalized_outputs_core_tables(tmp_path):
    mod = load_module()

    tencent = tmp_path / "tencent"
    kuaishou = tmp_path / "kuaishou"
    output = tmp_path / "platform"

    write_csv(
        tencent / "video_trend_daily_stats.csv",
        [
            {
                "date": "2026-05-01",
                "video_title": "SJS_01",
                "total_views": 100,
                "total_valid_views": 10,
                "valid_view_rate": 0.1,
                "avg_watch_duration": 5,
                "avg_watch_duration_rate": 0.2,
                "likes": 1,
                "comments": 2,
                "shares": 3,
            }
        ],
    )
    write_csv(
        tencent / "video_script_mapping_all.csv",
        [
            {
                "video_title": "SJS_01",
                "source_project": "冥府审计师",
                "episode_no": 1,
                "script_file": "data/episode_scripts/SJS_01.txt",
                "script_episode_title": "棺中清算",
                "note": "",
            }
        ],
    )
    write_csv(
        tencent / "account_daily_stats.csv",
        [
            {
                "date": "2026-05-01",
                "total_views": 100,
                "total_valid_views": 10,
                "likes": 1,
                "comments": 2,
                "shares": 3,
            }
        ],
    )

    write_csv(
        kuaishou / "kuaishou_drama_catalog.csv",
        [
            {
                "platform_drama_id": "ks_1",
                "raw_title": "男团王子",
                "canonical_title": "男团王子",
                "script_id": "script_1",
                "script_title": "男团王子",
                "match_status": "matched",
                "match_confidence": 1.0,
                "source_file": "短剧数据.csv",
            }
        ],
    )
    write_csv(
        kuaishou / "kuaishou_drama_daily_stats.csv",
        [
            {
                "date": "2026-05-01",
                "platform_drama_id": "ks_1",
                "raw_title": "男团王子",
                "canonical_title": "男团王子",
                "script_id": "script_1",
                "script_title": "男团王子",
                "match_status": "matched",
                "match_confidence": 1.0,
                "play_count": 200,
                "like_count": 20,
            }
        ],
    )
    write_csv(
        kuaishou / "kuaishou_ad_account_daily_stats.csv",
        [
            {
                "date": "2026-05-01",
                "ad_account_id": "ad_1",
                "ad_account_name": "0507-男团王子",
                "extracted_title": "男团王子",
                "script_id": "script_1",
                "script_title": "男团王子",
                "match_status": "matched",
                "match_confidence": 1.0,
                "impressions": 1000,
                "spend": 50,
                "valid_play_count": 100,
                "iaa_ltv": 0.3,
                "iaa_roi": 1.2,
            }
        ],
    )
    write_csv(
        kuaishou / "kuaishou_overall_daily_stats.csv",
        [
            {
                "date": "2026-05-01",
                "play_count": 200,
                "paid_amount": 10,
                "ad_spend": 5,
                "global_roi": 2.0,
                "iaa_ltv_with_rebate": 0.2,
                "iaa_roi_with_rebate": 1.3,
                "source_file": "核心数据.csv",
            }
        ],
    )

    outputs = mod.build_platform_market_normalized(tencent, kuaishou, output)

    expected_files = [
        "platform_drama_catalog.csv",
        "platform_drama_daily_stats.csv",
        "platform_episode_daily_stats.csv",
        "platform_ad_account_daily_stats.csv",
        "platform_overall_daily_stats.csv",
        "script_platform_mapping.csv",
        "market_feedback_summary.json",
    ]

    for filename in expected_files:
        assert (output / filename).exists(), filename

    assert len(outputs["platform_drama_catalog.csv"]) == 1
    assert len(outputs["platform_episode_daily_stats.csv"]) == 1
    assert len(outputs["platform_ad_account_daily_stats.csv"]) == 1
    assert len(outputs["script_platform_mapping.csv"]) == 2

    episode = pd.read_csv(output / "platform_episode_daily_stats.csv", encoding="utf-8-sig")
    assert episode.loc[0, "platform"] == "tencent_video"
    assert episode.loc[0, "video_title"] == "SJS_01"
    assert episode.loc[0, "source_project"] == "冥府审计师"

    ad = pd.read_csv(output / "platform_ad_account_daily_stats.csv", encoding="utf-8-sig")
    assert ad.loc[0, "platform"] == "kuaishou"
    assert ad.loc[0, "ad_account_name"] == "0507-男团王子"

    overall = pd.read_csv(output / "platform_overall_daily_stats.csv", encoding="utf-8-sig")
    assert set(overall["platform"]) == {"tencent_video", "kuaishou"}


def test_build_platform_market_normalized_handles_missing_inputs(tmp_path):
    mod = load_module()

    output = tmp_path / "platform"
    outputs = mod.build_platform_market_normalized(
        tmp_path / "missing_tencent",
        tmp_path / "missing_kuaishou",
        output,
    )

    assert outputs["platform_drama_catalog.csv"].empty
    assert outputs["platform_episode_daily_stats.csv"].empty
    assert (output / "market_feedback_summary.json").exists()
