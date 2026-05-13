from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from app.services.tencent_video_data.analyzer import (
    build_episode_diagnostics,
    extract_episode_no_from_title,
    generate_market_feedback_summary,
)
from app.services.tencent_video_data.importer import (
    VIDEO_TREND_DAILY_FIELDS,
    extract_video_title_from_trend_filename,
    identify_file_type,
    import_tencent_video_exports,
    normalize_dataframe,
    parse_percent,
)
from app.services.tencent_video_data.report_integration import append_market_feedback_section
from app.services.tencent_video_data.sample_builder import build_episode_samples
from app.services.tencent_video_data.script_aligner import align_episode_scripts
from app.services.tencent_video_data.text_feature_schema import (
    PLACEHOLDER_FEATURE_COLUMNS,
    build_episode_text_features,
)
from app.services.tencent_video_data.sync_service import (
    TencentVideoSyncResult,
    _download_or_snapshot,
    sync_tencent_video_exports,
)
from scripts.import_tencent_video_data import unique_paths


class TencentVideoDataTests(unittest.TestCase):
    def test_file_type_identification(self) -> None:
        self.assertEqual(identify_file_type(Path("账号趋势数据-2026.xlsx")), "account")
        self.assertEqual(identify_file_type(Path("专辑趋势数据-demo.xlsx")), "album")
        self.assertEqual(identify_file_type(Path("剧集趋势数据-demo.xlsx")), "episode")
        self.assertEqual(identify_file_type(Path("视频趋势数据-demo.xlsx")), "video")
        self.assertIsNone(identify_file_type(Path("其他数据-demo.xlsx")))

    def test_field_mapping_and_percent_parse(self) -> None:
        warnings: list[str] = []
        df = pd.DataFrame(
            {
                "时间": ["2026-05-12"],
                "标题": ["第1集"],
                "集数": [1],
                "总播放量": ["1,000"],
                "总有效播放量": [600],
                "有效播放量占比": ["35.71%"],
                "单次播放时长占比": [35.71],
            }
        )

        normalized = normalize_dataframe(df, "video", "视频趋势数据-test.xlsx", warnings)

        self.assertIn("date", normalized.columns)
        self.assertIn("title", normalized.columns)
        self.assertEqual(normalized.loc[0, "date"], "2026-05-12")
        self.assertEqual(normalized.loc[0, "total_views"], 1000)
        self.assertAlmostEqual(normalized.loc[0, "valid_view_rate"], 0.3571)
        self.assertAlmostEqual(normalized.loc[0, "avg_watch_duration_rate"], 0.3571)
        self.assertTrue(any("缺少字段" in warning for warning in warnings))

    def test_parse_percent_keeps_decimal_ratio(self) -> None:
        self.assertAlmostEqual(parse_percent("35.71%") or 0, 0.3571)
        self.assertAlmostEqual(parse_percent(35.71) or 0, 0.3571)
        self.assertAlmostEqual(parse_percent(0.3571) or 0, 0.3571)

    def test_extract_episode_no_from_sjs_title(self) -> None:
        self.assertEqual(extract_episode_no_from_title("短剧_SJS_05_正片"), 5)
        self.assertEqual(extract_episode_no_from_title("SJS_22"), 22)
        self.assertEqual(extract_episode_no_from_title("小医奴03"), 3)
        self.assertEqual(extract_episode_no_from_title("第12集"), 12)
        self.assertEqual(extract_episode_no_from_title("episode_07"), 7)

    def test_import_xlsx_and_missing_columns(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            input_dir = base / "exports"
            output_dir = base / "normalized"
            input_dir.mkdir()

            pd.DataFrame(
                {
                    "时间": ["2026-05-10", "2026-05-11"],
                    "粉丝数": [100, 120],
                    "有效播放量占比": ["50%", "60%"],
                }
            ).to_excel(input_dir / "账号趋势数据-test.xlsx", index=False)

            result = import_tencent_video_exports(input_dir, output_dir)

            output_file = output_dir / "account_daily_stats.csv"
            self.assertTrue(output_file.exists())
            self.assertEqual(len(result.read_excels), 1)
            self.assertIn(str(output_file), result.generated_files)
            self.assertTrue(any("缺少字段" in warning for warning in result.warnings))

            imported = pd.read_csv(output_file)
            self.assertEqual(list(imported["date"]), ["2026-05-10", "2026-05-11"])
            self.assertAlmostEqual(imported.loc[1, "valid_view_rate"], 0.6)

    def test_album_import_fills_missing_title_from_download_filename(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            input_dir = base / "exports"
            output_dir = base / "normalized"
            input_dir.mkdir()

            missing_title_file = input_dir / "专辑趋势数据-小医奴-20260513-103000.xlsx"
            empty_title_file = input_dir / "专辑趋势数据-冥府审判师-20260513-103500.xlsx"
            pd.DataFrame(
                {
                    "时间": ["2026-05-12"],
                    "总播放量": [1000],
                    "总在追数": [80],
                }
            ).to_excel(missing_title_file, index=False)
            pd.DataFrame(
                {
                    "时间": ["2026-05-13"],
                    "标题": [pd.NA],
                    "总播放量": [2000],
                    "总在追数": [120],
                }
            ).to_excel(empty_title_file, index=False)

            result = import_tencent_video_exports(input_dir, output_dir)
            output_file = output_dir / "album_daily_stats.csv"
            imported = pd.read_csv(output_file)

            self.assertTrue(output_file.exists())
            self.assertIn(str(missing_title_file), result.read_excels)
            self.assertIn(str(empty_title_file), result.read_excels)
            self.assertIn(str(output_file), result.generated_files)
            self.assertFalse(imported["title"].isna().any())
            self.assertEqual(
                set(imported["title"]),
                {"小医奴", "冥府审判师"},
            )
            self.assertEqual(set(imported["total_subscribers"]), {80, 120})

    def test_extract_video_title_from_trend_filename(self) -> None:
        self.assertEqual(
            extract_video_title_from_trend_filename(Path("视频趋势数据-SJS_17-20260513-103000.xlsx")),
            "SJS_17",
        )
        self.assertEqual(
            extract_video_title_from_trend_filename(Path("视频趋势数据-小医奴10-20260513-103000.xlsx")),
            "小医奴10",
        )
        self.assertIsNone(extract_video_title_from_trend_filename(Path("视频趋势数据.xlsx")))

    def test_import_video_trend_daily_exports_from_subdirectory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            input_dir = base / "exports"
            output_dir = base / "normalized"
            trend_dir = input_dir / "video_trends"
            trend_dir.mkdir(parents=True)

            pd.DataFrame(
                {
                    "时间": ["2026-05-12"],
                    "总播放量": [1000],
                    "总有效播放量": [500],
                    "有效播放量占比": ["50%"],
                    "单次播放时长": [12],
                    "单次播放时长占比": ["30%"],
                    "点赞": [10],
                    "评论": [2],
                    "分享": [1],
                }
            ).to_excel(trend_dir / "视频趋势数据-SJS_17-20260513-103000.xlsx", index=False)
            pd.DataFrame(
                {
                    "时间": ["2026-05-13"],
                    "总播放量": [2000],
                    "总有效播放量": [1200],
                    "有效播放量占比": ["60%"],
                    "单次播放时长": [15],
                    "单次播放时长占比": ["40%"],
                    "点赞": [20],
                    "评论": [3],
                    "分享": [2],
                }
            ).to_excel(trend_dir / "视频趋势数据-小医奴10-20260513-103000.xlsx", index=False)

            result = import_tencent_video_exports(input_dir, output_dir)
            output_file = output_dir / "video_trend_daily_stats.csv"
            imported = pd.read_csv(output_file)

            self.assertTrue(output_file.exists())
            self.assertIn(str(output_file), result.generated_files)
            self.assertEqual(list(imported.columns), VIDEO_TREND_DAILY_FIELDS)
            self.assertEqual(set(imported["video_title"]), {"SJS_17", "小医奴10"})
            self.assertEqual(set(imported["source_file"]), {
                "视频趋势数据-SJS_17-20260513-103000.xlsx",
                "视频趋势数据-小医奴10-20260513-103000.xlsx",
            })
            self.assertAlmostEqual(imported.loc[0, "valid_view_rate"], 0.5)
            self.assertFalse((output_dir / "video_daily_stats.csv").exists())
            self.assertFalse((output_dir / "episode_stats.csv").exists())

    def test_video_trends_subdirectory_does_not_duplicate_root_video_daily(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            input_dir = base / "exports"
            output_dir = base / "normalized"
            trend_dir = input_dir / "video_trends"
            trend_dir.mkdir(parents=True)

            pd.DataFrame(
                {
                    "时间": ["2026-05-12"],
                    "总播放量": [100],
                    "总有效播放量": [50],
                    "有效播放量占比": ["50%"],
                }
            ).to_excel(input_dir / "视频趋势数据-root.xlsx", index=False)
            pd.DataFrame(
                {
                    "时间": ["2026-05-13"],
                    "总播放量": [200],
                    "总有效播放量": [120],
                    "有效播放量占比": ["60%"],
                }
            ).to_excel(trend_dir / "视频趋势数据-SJS_17-20260513-103000.xlsx", index=False)

            import_tencent_video_exports(input_dir, output_dir)
            root_video = pd.read_csv(output_dir / "video_daily_stats.csv")
            video_trend = pd.read_csv(output_dir / "video_trend_daily_stats.csv")

            self.assertEqual(len(root_video), 1)
            self.assertEqual(root_video.loc[0, "date"], "2026-05-12")
            self.assertEqual(len(video_trend), 1)
            self.assertEqual(video_trend.loc[0, "date"], "2026-05-13")

    def test_missing_video_trends_directory_does_not_warn_or_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            input_dir = base / "exports"
            output_dir = base / "normalized"
            input_dir.mkdir()

            result = import_tencent_video_exports(input_dir, output_dir)

            self.assertEqual(result.generated_files, [])
            self.assertFalse((output_dir / "video_trend_daily_stats.csv").exists())

    def test_empty_xlsx_warning(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            input_dir = base / "exports"
            output_dir = base / "normalized"
            input_dir.mkdir()

            pd.DataFrame().to_excel(input_dir / "剧集趋势数据-empty.xlsx", index=False)

            result = import_tencent_video_exports(input_dir, output_dir)

            self.assertTrue((output_dir / "episode_stats.csv").exists())
            self.assertTrue(any("内容为空" in warning for warning in result.warnings))

    def test_summary_generation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            pd.DataFrame(
                {
                    "date": ["2026-05-10", "2026-05-11"],
                    "followers": [100, 125],
                    "total_views": [1000, 1500],
                    "total_valid_views": [600, 1000],
                    "valid_view_rate": [0.6, 0.66],
                }
            ).to_csv(output_dir / "account_daily_stats.csv", index=False)
            pd.DataFrame(
                {
                    "title": ["A", "A", "A"],
                    "episode_no": [1, 2, 3],
                    "total_views": [1000, 1500, 1600],
                    "total_valid_views": [900, 600, 580],
                    "valid_view_rate": [0.9, 0.4, 0.36],
                    "avg_watch_duration": [80, 40, 35],
                    "likes": [10, 40, 20],
                    "comments": [5, 30, 10],
                    "shares": [1, 9, 3],
                }
            ).to_csv(output_dir / "episode_stats.csv", index=False)

            result = generate_market_feedback_summary(output_dir)
            summary_file = output_dir / "market_feedback_summary.json"

            self.assertTrue(summary_file.exists())
            summary = json.loads(summary_file.read_text(encoding="utf-8"))
            self.assertIn("account_growth_summary", summary)
            self.assertIn("episode_drop_off_ranking", summary)
            self.assertTrue(summary["episode_drop_off_ranking"])
            self.assertTrue(summary["high_interaction_episodes"])
            self.assertTrue(summary["high_exposure_low_valid_episodes"])
            self.assertIn("reason", summary["high_exposure_low_valid_episodes"][0])
            self.assertIn(str(summary_file), result.generated_files)

    def test_episode_diagnostics_extracts_episode_no_and_drop_off(self) -> None:
        df = pd.DataFrame(
            {
                "title": ["SJS_04", "SJS_05", "SJS_06"],
                "episode_no": [None, None, None],
                "total_views": [1000, 700, 650],
                "total_valid_views": [800, 400, 390],
                "valid_view_rate": [0.8, 0.57, 0.6],
                "avg_watch_duration": [80, 50, 55],
                "likes": [10, 20, 15],
                "comments": [1, 2, 1],
                "shares": [1, 2, 1],
            }
        )

        diagnostics = build_episode_diagnostics(df)

        self.assertTrue(diagnostics["drop_off_ranking"])
        self.assertEqual(diagnostics["drop_off_ranking"][0]["episode_no"], 5)
        self.assertGreater(diagnostics["drop_off_ranking"][0]["valid_views_drop_rate"], 0)

    def test_low_view_high_share_is_filtered_out(self) -> None:
        df = pd.DataFrame(
            {
                "title": ["SJS_01", "SJS_02", "SJS_03"],
                "episode_no": [None, None, None],
                "total_views": [1200, 1000, 20],
                "total_valid_views": [900, 700, 10],
                "valid_view_rate": [0.75, 0.7, 0.5],
                "avg_watch_duration": [80, 70, 20],
                "likes": [10, 20, 1],
                "comments": [2, 3, 0],
                "shares": [3, 4, 999],
            }
        )

        diagnostics = build_episode_diagnostics(df)
        share_titles = {item["title"] for item in diagnostics["high_share_episodes"]}

        self.assertNotIn("SJS_03", share_titles)
        self.assertIn("SJS_02", share_titles)

    def test_high_exposure_low_valid_has_reason(self) -> None:
        df = pd.DataFrame(
            {
                "title": ["SJS_01", "SJS_02", "SJS_03"],
                "episode_no": [None, None, None],
                "total_views": [1000, 1500, 1600],
                "total_valid_views": [900, 600, 580],
                "valid_view_rate": [0.9, 0.4, 0.36],
                "avg_watch_duration": [80, 40, 35],
                "likes": [10, 40, 20],
                "comments": [5, 30, 10],
                "shares": [1, 9, 3],
            }
        )

        diagnostics = build_episode_diagnostics(df)

        self.assertTrue(diagnostics["high_exposure_low_valid"])
        self.assertEqual(
            diagnostics["high_exposure_low_valid"][0]["reason"],
            "播放量高于中位数，但有效播放率低于中位数",
        )

    def test_report_contains_market_feedback_section_when_summary_exists(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            summary_path = Path(temp_dir) / "market_feedback_summary.json"
            summary_path.write_text(
                json.dumps(
                    {
                        "account_growth_summary": {
                            "diagnosis": ["粉丝数最新值为 125，较首条记录变化 25。"],
                            "valid_view_rate": {"median": 0.62},
                        },
                        "album_performance_summary": {
                            "diagnosis": ["总有效播放量中位数为 800.00。"],
                        },
                        "high_exposure_low_valid_episodes": [
                            {
                                "title": "SJS_05",
                                "episode_no": 5,
                                "total_views": 1500,
                                "valid_view_rate": 0.36,
                                "reason": "播放量高于中位数，但有效播放率低于中位数",
                            }
                        ],
                        "episode_drop_off_ranking": [
                            {
                                "title": "SJS_06",
                                "episode_no": 6,
                                "views_drop_rate": 0.2,
                                "valid_views_drop_rate": 0.3,
                            }
                        ],
                        "high_interaction_episodes": [
                            {
                                "title": "SJS_07",
                                "episode_no": 7,
                                "total_views": 1800,
                                "interaction_score": 70,
                            }
                        ],
                        "high_share_episodes": [
                            {
                                "title": "SJS_08",
                                "episode_no": 8,
                                "total_views": 1900,
                                "shares": 12,
                            }
                        ],
                        "script_review_suggestions": ["高曝光但有效播放偏低的集数，建议复盘前30秒。"],
                        "diagnostic_note": "本摘要仅作为复盘辅助依据，不代表因果结论。",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            report = append_market_feedback_section("# 原审核报告\n\n正文。", summary_path)

            self.assertIn("腾讯视频平台反馈分析", report)
            self.assertIn("账号整体趋势", report)
            self.assertIn("专辑表现", report)
            self.assertIn("高曝光低有效播放集数", report)
            self.assertIn("剧集掉点排行", report)
            self.assertIn("高互动/高分享集数", report)
            self.assertIn("剧本复盘建议", report)
            self.assertIn("数据提示", report)
            self.assertIn("建议复盘", report)
            self.assertIn("可能需要检查", report)
            self.assertIn("前30秒", report)
            self.assertLess(report.index("账号整体趋势"), report.index("专辑表现"))
            self.assertLess(report.index("专辑表现"), report.index("剧集掉点排行"))
            self.assertLess(report.index("剧集掉点排行"), report.index("高曝光低有效播放集数"))
            self.assertLess(report.index("高曝光低有效播放集数"), report.index("高互动/高分享集数"))
            self.assertLess(report.index("高互动/高分享集数"), report.index("剧本复盘建议"))
            self.assertNotIn("None", report)
            self.assertNotIn("null", report)

    def test_report_without_market_summary_keeps_original_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_summary = Path(temp_dir) / "missing.json"
            original_report = "# 原审核报告\n\n中文正文正常。"

            report = append_market_feedback_section(original_report, missing_summary)

            self.assertEqual(report, original_report)
            self.assertIn("中文正文正常", report)

    def test_report_generates_without_director_form_data(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            summary_path = Path(temp_dir) / "market_feedback_summary.json"
            summary_path.write_text(
                json.dumps(
                    {
                        "account_growth_summary": {
                            "diagnosis": ["数据提示：账号趋势可作为辅助参考。"],
                        },
                        "album_performance_summary": {
                            "diagnosis": ["数据提示：专辑表现建议结合文本审核复盘。"],
                        },
                        "episode_drop_off_ranking": [],
                        "high_exposure_low_valid_episodes": [],
                        "high_interaction_episodes": [],
                        "high_share_episodes": [],
                        "script_review_suggestions": ["建议复盘上一集结尾钩子和本集开场承接。"],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            report_without_director_form = "# 原审核报告\n\n没有导演表单数据。"

            report = append_market_feedback_section(report_without_director_form, summary_path)

            self.assertIn("腾讯视频平台反馈分析", report)
            self.assertIn("剧本复盘建议", report)
            self.assertIn("没有导演表单数据", report)
            self.assertNotIn("导演表单缺失", report)

    def test_market_feedback_report_keeps_chinese_readable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            summary_path = Path(temp_dir) / "market_feedback_summary.json"
            summary_path.write_text(
                json.dumps(
                    {
                        "account_growth_summary": {
                            "diagnosis": ["账号有效播放率中位数为 60%。"],
                        },
                        "album_performance_summary": {},
                        "script_review_suggestions": ["建议复盘标题封面预期与剧情承接。"],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            report = append_market_feedback_section("# 审核报告", summary_path)

            self.assertIn("账号有效播放率", report)
            self.assertIn("标题封面预期", report)
            self.assertNotIn("\\u", report)

    def test_build_episode_samples_merges_labels(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            normalized_dir = Path(temp_dir)
            pd.DataFrame(
                {
                    "title": ["SJS_05", "小医奴03", "第12集"],
                    "episode_no": [None, None, None],
                    "total_views": [1500, 1000, 800],
                    "total_valid_views": [500, 700, 600],
                    "valid_view_rate": [0.33, 0.7, 0.75],
                    "likes": [20, 30, 40],
                    "comments": [2, 3, 4],
                    "shares": [1, 2, 3],
                }
            ).to_csv(normalized_dir / "episode_stats.csv", index=False)
            (normalized_dir / "market_feedback_summary.json").write_text(
                json.dumps(
                    {
                        "high_exposure_low_valid_episodes": [
                            {"title": "SJS_05", "episode_no": 5},
                        ],
                        "episode_drop_off_ranking": [
                            {"title": "小医奴03"},
                        ],
                        "high_interaction_episodes": [
                            {"title": "第12集"},
                        ],
                        "high_share_episodes": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            result = build_episode_samples(normalized_dir)
            output_file = normalized_dir / "episode_samples.csv"
            samples = pd.read_csv(output_file, keep_default_na=False)

            self.assertTrue(output_file.exists())
            self.assertIn(str(output_file), result.generated_files)
            self.assertIn("script_text", samples.columns)
            self.assertTrue((samples["script_text"] == "").all())

            by_episode = samples.set_index("episode_no")
            self.assertTrue(bool(by_episode.loc[5, "is_high_exposure_low_valid"]))
            self.assertTrue(bool(by_episode.loc[3, "is_drop_off_episode"]))
            self.assertTrue(bool(by_episode.loc[12, "is_high_interaction"]))
            self.assertFalse(bool(by_episode.loc[5, "is_high_share"]))
            self.assertEqual(int(by_episode.loc[5].name), 5)

    def test_align_episode_scripts_from_supported_filenames(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            normalized_dir = base / "normalized"
            script_dir = base / "episode_scripts"
            normalized_dir.mkdir()
            script_dir.mkdir()
            pd.DataFrame(
                {
                    "episode_no": [3, 5, 7, 12],
                    "episode_title": ["小医奴03", "SJS_05", "episode_07", "第12集"],
                    "total_views": [100, 200, 300, 400],
                    "total_valid_views": [80, 160, 240, 320],
                    "valid_view_rate": [0.8, 0.8, 0.8, 0.8],
                    "likes": [1, 2, 3, 4],
                    "comments": [0, 1, 1, 2],
                    "shares": [0, 1, 1, 2],
                    "is_high_exposure_low_valid": [False, False, False, False],
                    "is_drop_off_episode": [False, False, False, False],
                    "is_high_interaction": [False, False, False, False],
                    "is_high_share": [False, False, False, False],
                    "script_text": ["", "", "", ""],
                }
            ).to_csv(normalized_dir / "episode_samples.csv", index=False)
            (script_dir / "SJS_05.txt").write_text("第五集剧本文本", encoding="utf-8")
            (script_dir / "小医奴03.txt").write_text("第三集剧本文本", encoding="utf-8")
            (script_dir / "episode_07.txt").write_text("第七集剧本文本", encoding="utf-8")
            (script_dir / "第12集.txt").write_text("第十二集剧本文本", encoding="utf-8")

            result = align_episode_scripts(normalized_dir, script_dir)
            samples = pd.read_csv(normalized_dir / "episode_samples.csv", keep_default_na=False)
            by_episode = samples.set_index("episode_no")

            self.assertEqual(result.aligned_count, 4)
            self.assertEqual(by_episode.loc[5, "script_text"], "第五集剧本文本")
            self.assertEqual(by_episode.loc[3, "script_text"], "第三集剧本文本")
            self.assertEqual(by_episode.loc[7, "script_text"], "第七集剧本文本")
            self.assertEqual(by_episode.loc[12, "script_text"], "第十二集剧本文本")

    def test_align_episode_scripts_strips_utf8_bom(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            normalized_dir = base / "normalized"
            script_dir = base / "episode_scripts"
            normalized_dir.mkdir()
            script_dir.mkdir()
            pd.DataFrame(
                {
                    "episode_no": [1],
                    "episode_title": ["SJS_01"],
                    "script_text": [""],
                }
            ).to_csv(normalized_dir / "episode_samples.csv", index=False)
            (script_dir / "SJS_01.txt").write_text("\ufeff这是第1集测试剧本文本。", encoding="utf-8")

            align_episode_scripts(normalized_dir, script_dir)
            samples = pd.read_csv(normalized_dir / "episode_samples.csv", keep_default_na=False)

            self.assertEqual(samples.loc[0, "script_text"], "这是第1集测试剧本文本。")
            self.assertNotIn("\ufeff", samples.loc[0, "script_text"])

    def test_align_episode_scripts_missing_directory_does_not_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            normalized_dir = Path(temp_dir)
            pd.DataFrame(
                {
                    "episode_no": [5],
                    "episode_title": ["SJS_05"],
                    "script_text": [""],
                }
            ).to_csv(normalized_dir / "episode_samples.csv", index=False)

            result = align_episode_scripts(normalized_dir, normalized_dir / "missing_scripts")

            self.assertEqual(result.aligned_count, 0)
            self.assertTrue(result.warnings)

    def test_unmatched_episode_script_text_remains_empty(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            normalized_dir = base / "normalized"
            script_dir = base / "episode_scripts"
            normalized_dir.mkdir()
            script_dir.mkdir()
            pd.DataFrame(
                {
                    "episode_no": [5, 6],
                    "episode_title": ["SJS_05", "SJS_06"],
                    "script_text": ["", ""],
                }
            ).to_csv(normalized_dir / "episode_samples.csv", index=False)
            (script_dir / "SJS_05.txt").write_text("第五集剧本文本", encoding="utf-8")

            align_episode_scripts(normalized_dir, script_dir)
            samples = pd.read_csv(normalized_dir / "episode_samples.csv", keep_default_na=False)
            by_episode = samples.set_index("episode_no")

            self.assertEqual(by_episode.loc[5, "script_text"], "第五集剧本文本")
            self.assertEqual(by_episode.loc[6, "script_text"], "")

    def test_build_episode_text_features_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            normalized_dir = Path(temp_dir)
            pd.DataFrame(
                {
                    "episode_no": [1, 2],
                    "episode_title": ["SJS_01", "SJS_02"],
                    "script_text": ["", "第二集剧本文本"],
                }
            ).to_csv(normalized_dir / "episode_samples.csv", index=False)

            result = build_episode_text_features(normalized_dir)
            output_file = normalized_dir / "episode_text_features.csv"
            features = pd.read_csv(output_file, keep_default_na=False)

            self.assertTrue(output_file.exists())
            self.assertIn(str(output_file), result.generated_files)
            self.assertFalse(bool(features.loc[0, "has_script_text"]))
            self.assertEqual(features.loc[0, "script_length"], 0)
            self.assertTrue(bool(features.loc[1, "has_script_text"]))
            self.assertGreater(features.loc[1, "script_length"], 0)

            for field in PLACEHOLDER_FEATURE_COLUMNS:
                self.assertIn(field, features.columns)
                self.assertTrue((features[field] == "").all())

    def test_sync_missing_auth_state_returns_warning_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            result = sync_tencent_video_exports(
                auth_state_path=base / "missing_state.json",
                output_dir=base / "exports",
            )

            self.assertEqual(result.downloaded_files, [])
            self.assertTrue(any("登录态不存在" in warning for warning in result.warnings))

    def test_sync_no_download_button_saves_snapshot_without_error(self) -> None:
        class EmptyLocator:
            def __init__(self, text: str = "") -> None:
                self.text = text

            def count(self) -> int:
                return 0

            def first(self) -> "EmptyLocator":
                return self

            def inner_text(self, timeout: int = 0) -> str:
                return self.text

        class FakePage:
            def get_by_role(self, *args: object, **kwargs: object) -> EmptyLocator:
                return EmptyLocator()

            def get_by_text(self, *args: object, **kwargs: object) -> EmptyLocator:
                return EmptyLocator()

            def locator(self, selector: str) -> EmptyLocator:
                if selector == "body":
                    return EmptyLocator("粉丝页面内容，没有下载按钮")
                return EmptyLocator()

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            result = TencentVideoSyncResult()

            _download_or_snapshot(FakePage(), output_dir, result, timeout_ms=100)

            snapshot_path = output_dir / "fans_snapshot.txt"
            self.assertTrue(snapshot_path.exists())
            self.assertIn("粉丝页面内容", snapshot_path.read_text(encoding="utf-8"))
            self.assertIn(str(snapshot_path), result.snapshot_files)
            self.assertTrue(any("未找到" in warning for warning in result.warnings))

    def test_generated_file_list_deduplicates_episode_samples(self) -> None:
        paths = [
            "data/tencent_video_normalized/episode_samples.csv",
            "data/tencent_video_normalized/market_feedback_summary.json",
            "data/tencent_video_normalized/episode_samples.csv",
        ]

        self.assertEqual(
            unique_paths(paths),
            [
                "data/tencent_video_normalized/episode_samples.csv",
                "data/tencent_video_normalized/market_feedback_summary.json",
            ],
        )


if __name__ == "__main__":
    unittest.main()
