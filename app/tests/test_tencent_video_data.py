from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from app.services.tencent_video_data.analyzer import generate_market_feedback_summary
from app.services.tencent_video_data.importer import (
    identify_file_type,
    import_tencent_video_exports,
    normalize_dataframe,
    parse_percent,
)


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
            self.assertTrue(summary["high_interaction_episodes"])
            self.assertIn(str(summary_file), result.generated_files)


if __name__ == "__main__":
    unittest.main()
