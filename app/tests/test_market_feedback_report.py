from pathlib import Path
import importlib.util
import sys

import pandas as pd


def load_module():
    module_path = Path("scripts/build_market_feedback_report.py")
    module_name = "build_market_feedback_report"

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


def test_build_market_feedback_report_outputs_json_and_markdown(tmp_path):
    mod = load_module()
    platform = tmp_path / "platform"

    write_csv(
        platform / "script_platform_mapping.csv",
        [
            {
                "platform": "tencent_video",
                "video_title": "SJS_01",
                "source_project": "冥府审计师",
                "script_title": "冥府审计师",
                "match_status": "matched",
                "note": "",
                "source_table": "video_script_mapping_all.csv",
            },
            {
                "platform": "kuaishou",
                "raw_title": "缺失剧",
                "script_title": "",
                "match_status": "script_file_missing",
                "note": "no_good_script_match",
                "source_table": "kuaishou_drama_catalog.csv",
            },
        ],
    )

    write_csv(
        platform / "platform_episode_daily_stats.csv",
        [
            {
                "platform": "tencent_video",
                "date": "2026-05-01",
                "source_project": "冥府审计师",
                "video_title": "SJS_01",
                "episode_no": 1,
                "play_count": 100,
                "valid_play_count": 10,
                "valid_view_rate": 0.1,
                "avg_watch_duration_rate": 0.2,
                "like_count": 1,
                "comment_count": 2,
                "share_count": 3,
            },
            {
                "platform": "tencent_video",
                "date": "2026-05-02",
                "source_project": "冥府审计师",
                "video_title": "SJS_01",
                "episode_no": 1,
                "play_count": 200,
                "valid_play_count": 40,
                "valid_view_rate": 0.2,
                "avg_watch_duration_rate": 0.3,
                "like_count": 3,
                "comment_count": 2,
                "share_count": 1,
            },
        ],
    )

    write_csv(
        platform / "platform_ad_account_daily_stats.csv",
        [
            {
                "platform": "kuaishou",
                "date": "2026-05-01",
                "ad_account_name": "泛账户",
                "extracted_title": "",
                "script_title": "",
                "match_status": "account_name_generic",
                "match_confidence": 0,
                "spend": 100,
            },
            {
                "platform": "kuaishou",
                "date": "2026-05-02",
                "ad_account_name": "泛账户",
                "extracted_title": "",
                "script_title": "",
                "match_status": "account_name_generic",
                "match_confidence": 0,
                "spend": 50,
            },
        ],
    )

    write_csv(
        platform / "platform_overall_daily_stats.csv",
        [
            {
                "platform": "tencent_video",
                "date": "2026-05-01",
                "play_count": 100,
                "valid_play_count": 10,
            },
            {
                "platform": "kuaishou",
                "date": "2026-05-01",
                "play_count": 200,
                "paid_amount": 10,
                "ad_spend": 5,
                "global_roi": 2,
                "iaa_ltv": 0.2,
                "iaa_roi": 1.3,
            },
        ],
    )

    report = mod.build_market_feedback_report(platform)

    assert (platform / "market_feedback_report.json").exists()
    assert (platform / "market_feedback_report.md").exists()

    assert report["mapping"]["rows"] == 2
    assert report["mapping"]["issue_rows"] == 1
    assert report["episode_performance"]["unique_videos"] == 1
    assert report["ad_account_review"]["issue_rows"] == 2
    assert report["ad_account_review"]["issue_accounts"] == 1

    md = (platform / "market_feedback_report.md").read_text(encoding="utf-8")
    assert "跨平台市场反馈复盘报告" in md
    assert "快手广告账户复核" in md
    assert "腾讯单集表现" in md


def test_build_market_feedback_report_handles_empty_input(tmp_path):
    mod = load_module()
    platform = tmp_path / "empty"

    report = mod.build_market_feedback_report(platform)

    assert report["mapping"]["rows"] == 0
    assert report["episode_performance"]["rows"] == 0
    assert report["ad_account_review"]["rows"] == 0
    assert (platform / "market_feedback_report.json").exists()
    assert (platform / "market_feedback_report.md").exists()
