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
    identify_file_type,
    import_tencent_video_exports,
    normalize_dataframe,
    parse_percent,
)
from app.services.tencent_video_data.report_integration import append_market_feedback_section


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
            self.assertIn("前30秒", report)
            self.assertNotIn("None", report)
            self.assertNotIn("null", report)

    def test_report_without_market_summary_keeps_original_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_summary = Path(temp_dir) / "missing.json"
            original_report = "# 原审核报告\n\n中文正文正常。"

            report = append_market_feedback_section(original_report, missing_summary)

            self.assertEqual(report, original_report)
            self.assertIn("中文正文正常", report)

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


if __name__ == "__main__":
    unittest.main()
