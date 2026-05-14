from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from scripts.build_modeling_episode_dataset import (
    aggregate_video_trends,
    build_modeling_episode_dataset,
    canonical_video_title,
    infer_project_episode,
)


class ModelingEpisodeDatasetTests(unittest.TestCase):
    def test_build_dataset_merges_mappings_trends_and_scripts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            normalized_dir = Path(temp_dir)
            script_dir = normalized_dir / "episode_scripts"
            script_dir.mkdir()
            xiaoyinu_dir = script_dir / "xiaoyinu"
            xiaoyinu_dir.mkdir()

            (script_dir / "SJS_01.txt").write_text("△开场\n判官：开审。\n悬念收束。", encoding="utf-8")
            (xiaoyinu_dir / "小医奴_01.txt").write_text("△街口\n小医奴：救人要紧。\n转身离开。", encoding="utf-8")

            pd.DataFrame(
                [
                    {
                        "video_title": "SJS_01",
                        "episode_no": 1,
                        "script_file": "episode_scripts/SJS_01.txt",
                        "script_episode_title": "冥府审计师 第1集",
                        "source_project": "冥府审计师",
                        "note": "",
                    },
                    {
                        "video_title": "SJS_02",
                        "episode_no": 2,
                        "script_file": "episode_scripts/missing.txt",
                        "script_episode_title": "冥府审计师 第2集",
                        "source_project": "冥府审计师",
                        "note": "missing script",
                    },
                ]
            ).to_csv(normalized_dir / "video_script_mapping.csv", index=False)
            pd.DataFrame(
                [
                    {
                        "video_title": "小医奴01",
                        "episode_no": 1,
                        "script_file": "episode_scripts/xiaoyinu/小医奴_01.txt",
                        "script_episode_title": "小医奴 第1集",
                        "source_project": "小医奴",
                        "note": "",
                    }
                ]
            ).to_csv(normalized_dir / "video_script_mapping_xiaoyinu.csv", index=False)
            pd.DataFrame(
                [
                    {
                        "video_title": "SJS_01",
                        "date": "2026-05-12",
                        "total_views": 100,
                        "total_valid_views": 80,
                        "valid_view_rate": 0.8,
                        "avg_watch_duration": 10,
                        "avg_watch_duration_rate": 0.4,
                        "likes": 1,
                        "comments": 2,
                        "shares": 3,
                    },
                    {
                        "video_title": "SJS_01",
                        "date": "2026-05-13",
                        "total_views": 150,
                        "total_valid_views": 100,
                        "valid_view_rate": 0.6,
                        "avg_watch_duration": 12,
                        "avg_watch_duration_rate": 0.5,
                        "likes": 4,
                        "comments": 5,
                        "shares": 6,
                    },
                    {
                        "video_title": "小医奴01",
                        "date": "2026-05-13",
                        "total_views": 90,
                        "total_valid_views": 70,
                        "valid_view_rate": 0.7,
                        "avg_watch_duration": 9,
                        "avg_watch_duration_rate": 0.3,
                        "likes": 2,
                        "comments": 1,
                        "shares": 1,
                    },
                ]
            ).to_csv(normalized_dir / "video_trend_daily_stats.csv", index=False)

            result = build_modeling_episode_dataset(normalized_dir)
            mapping_all = pd.read_csv(normalized_dir / "video_script_mapping_all.csv")
            dataset = pd.read_csv(normalized_dir / "modeling_episode_dataset.csv")

            self.assertEqual(len(result.mapping_files_read), 2)
            self.assertEqual(len(mapping_all), 3)
            self.assertTrue((normalized_dir / "modeling_episode_dataset.csv").exists())
            self.assertEqual(result.video_title_count, 2)
            self.assertEqual(result.dataset_rows, 3)
            self.assertIn("小医奴", set(dataset["source_project"]))
            self.assertIn("小医奴01", set(dataset["video_title"]))

            sjs_01 = dataset.set_index("video_title").loc["SJS_01"]
            self.assertEqual(sjs_01["total_views_latest"], 150)
            self.assertEqual(sjs_01["interaction_latest"], 15)
            self.assertTrue(bool(sjs_01["has_script_text"]))
            self.assertGreater(sjs_01["script_length"], 0)
            self.assertEqual(sjs_01["line_count"], 3)
            self.assertEqual(sjs_01["dialogue_line_count"], 1)
            self.assertEqual(sjs_01["action_line_count"], 1)
            self.assertIn("判官", sjs_01["script_text"])

            sjs_02 = dataset.set_index("video_title").loc["SJS_02"]
            self.assertFalse(bool(sjs_02["has_script_text"]))
            self.assertIn("SJS_02", result.missing_script_titles)
            self.assertIn("SJS_02", result.missing_playback_titles)

            for column in [
                "is_high_valid_view_rate",
                "is_low_valid_view_rate",
                "is_high_interaction",
                "is_low_retention",
            ]:
                self.assertIn(column, dataset.columns)

    def test_auto_completes_missing_xiaoyinu_mappings_from_local_scripts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            normalized_dir = Path(temp_dir)
            xiaoyinu_dir = normalized_dir / "episode_scripts" / "xiaoyinu"
            split_dir = normalized_dir / "episode_scripts_split" / "小医奴"
            xiaoyinu_dir.mkdir(parents=True)
            split_dir.mkdir(parents=True)
            (xiaoyinu_dir / "小医奴_09.txt").write_text("△药肆\n小医奴：试药。\n转折。", encoding="utf-8")
            (split_dir / "第14集_绝域轮回.txt").write_text("△雪地\n小医奴：我回来了。", encoding="utf-8")
            (split_dir / "第15集_漫天飞雪落余烬.txt").write_text("△终局\n小医奴：余烬未冷。", encoding="utf-8")

            pd.DataFrame(
                [
                    {
                        "video_title": "SJS_01",
                        "episode_no": 1,
                        "script_file": "",
                        "script_episode_title": "冥府审计师 第1集",
                        "source_project": "冥府审计师",
                        "note": "",
                    }
                ]
            ).to_csv(normalized_dir / "video_script_mapping.csv", index=False)
            pd.DataFrame(
                [
                    {
                        "video_title": "小医奴01",
                        "episode_no": 1,
                        "script_file": "",
                        "script_episode_title": "小医奴 第1集",
                        "source_project": "小医奴",
                        "note": "",
                    }
                ]
            ).to_csv(normalized_dir / "video_script_mapping_xiaoyinu.csv", index=False)
            pd.DataFrame(
                [
                    {"video_title": "小医奴09", "date": "2026-05-13", "valid_view_rate": 0.8, "avg_watch_duration_rate": 0.5, "likes": 1, "comments": 1, "shares": 1},
                    {"video_title": "小医奴14", "date": "2026-05-13", "valid_view_rate": 0.7, "avg_watch_duration_rate": 0.4, "likes": 2, "comments": 1, "shares": 1},
                    {"video_title": "小医奴15", "date": "2026-05-13", "valid_view_rate": 0.6, "avg_watch_duration_rate": 0.3, "likes": 3, "comments": 1, "shares": 1},
                    {"video_title": "未知项目01", "date": "2026-05-13", "valid_view_rate": 0.1, "avg_watch_duration_rate": 0.1, "likes": 0, "comments": 0, "shares": 0},
                ]
            ).to_csv(normalized_dir / "video_trend_daily_stats.csv", index=False)

            result = build_modeling_episode_dataset(normalized_dir)
            mapping_all = pd.read_csv(normalized_dir / "video_script_mapping_all.csv", encoding="utf-8-sig")
            dataset = pd.read_csv(normalized_dir / "modeling_episode_dataset.csv", encoding="utf-8-sig")
            by_title = dataset.set_index("video_title")

            self.assertEqual(result.auto_completed_mapping_rows, 4)
            self.assertIn("小医奴09", set(mapping_all["video_title"]))
            self.assertIn("小医奴14", set(mapping_all["video_title"]))
            self.assertIn("小医奴15", set(mapping_all["video_title"]))
            self.assertEqual(by_title.loc["小医奴09", "source_project"], "小医奴")
            self.assertEqual(by_title.loc["小医奴14", "source_project"], "小医奴")
            self.assertEqual(by_title.loc["小医奴15", "source_project"], "小医奴")
            self.assertTrue(bool(by_title.loc["小医奴09", "has_script_text"]))
            self.assertTrue(bool(by_title.loc["小医奴14", "has_script_text"]))
            self.assertTrue(bool(by_title.loc["小医奴15", "has_script_text"]))
            self.assertGreater(by_title.loc["小医奴09", "script_length"], 0)
            self.assertIn("episode_scripts/xiaoyinu/小医奴_09.txt", by_title.loc["小医奴09", "script_file"])
            self.assertIn("episode_scripts_split/小医奴/第14集_", by_title.loc["小医奴14", "script_file"])
            self.assertEqual(by_title.loc["未知项目01", "source_project"], "未映射")
            self.assertFalse(pd.isna(by_title.loc["未知项目01", "source_project"]))
            self.assertFalse(bool(by_title.loc["未知项目01", "has_script_text"]))

    def test_infers_supported_video_title_formats(self) -> None:
        self.assertEqual(infer_project_episode("SJS_1"), ("冥府审计师", 1))
        self.assertEqual(infer_project_episode("SJS_01"), ("冥府审计师", 1))
        self.assertEqual(infer_project_episode("小医奴09"), ("小医奴", 9))
        self.assertEqual(infer_project_episode("小医奴_09"), ("小医奴", 9))
        self.assertEqual(infer_project_episode("小医奴第09集"), ("小医奴", 9))
        self.assertEqual(infer_project_episode("小医奴第九集"), ("小医奴", 9))
        self.assertEqual(canonical_video_title("Сҽū09"), "小医奴09")

    def test_aggregate_video_trends_falls_back_to_row_order_on_bad_date(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            normalized_dir = Path(temp_dir)
            pd.DataFrame(
                [
                    {"video_title": "小医奴01", "date": "bad-date", "total_views": 10},
                    {"video_title": "小医奴01", "date": "also-bad", "total_views": 20},
                ]
            ).to_csv(normalized_dir / "video_trend_daily_stats.csv", index=False)

            class Result:
                warnings: list[str] = []
                video_title_count = 0

            result = Result()
            aggregated = aggregate_video_trends(normalized_dir, result)  # type: ignore[arg-type]

            self.assertEqual(aggregated.loc[0, "video_title"], "小医奴01")
            self.assertEqual(aggregated.loc[0, "total_views_latest"], 20)
            self.assertTrue(result.warnings)


if __name__ == "__main__":
    unittest.main()
