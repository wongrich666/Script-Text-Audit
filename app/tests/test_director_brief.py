from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.services.director_brief import append_director_brief_section, load_director_brief


class DirectorBriefTests(unittest.TestCase):
    def test_report_contains_director_brief_section_when_file_exists(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            brief_path = Path(temp_dir) / "director_brief.json"
            brief_path.write_text(
                json.dumps(
                    {
                        "project_name": "小医奴",
                        "genre": "古装甜宠",
                        "target_audience": "女性短剧用户",
                        "platform_goal": "提升完播率",
                        "core_selling_points": ["强反转", "情绪补偿"],
                        "director_focus": "关注前三集钩子。",
                        "review_priorities": ["节奏", "人物动机"],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            report = append_director_brief_section("# 原审核报告\n\n正文。", brief_path)

            self.assertIn("导演目标匹配度分析", report)
            self.assertIn("项目名称：小医奴", report)
            self.assertIn("题材类型：古装甜宠", report)
            self.assertIn("核心卖点：强反转、情绪补偿", report)
            self.assertIn("审核优先级：节奏、人物动机", report)

    def test_report_without_director_brief_keeps_original_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_path = Path(temp_dir) / "director_brief.json"
            original_report = "# 原审核报告\n\n纯文本审核正常。"

            report = append_director_brief_section(original_report, missing_path)

            self.assertEqual(report, original_report)
            self.assertIn("纯文本审核正常", report)

    def test_invalid_json_does_not_break_main_flow(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            brief_path = Path(temp_dir) / "director_brief.json"
            brief_path.write_text("{invalid json", encoding="utf-8")
            warnings: list[str] = []

            brief = load_director_brief(brief_path, warnings=warnings)
            report = append_director_brief_section("# 原审核报告", brief_path, warnings=warnings)

            self.assertIsNone(brief)
            self.assertEqual(report, "# 原审核报告")
            self.assertTrue(any("JSON 格式错误" in warning for warning in warnings))

    def test_director_brief_chinese_is_readable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            brief_path = Path(temp_dir) / "director_brief.json"
            brief_path.write_text(
                json.dumps(
                    {
                        "project_name": "她从废墟里归来",
                        "genre": "重生复仇",
                        "target_audience": "喜欢强爽点的短剧用户",
                        "platform_goal": "提升互动讨论",
                        "director_focus": "重点看女主目标和反派压迫。",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            report = append_director_brief_section("# 审核报告", brief_path)

            self.assertIn("她从废墟里归来", report)
            self.assertIn("重生复仇", report)
            self.assertNotIn("\\u", report)


if __name__ == "__main__":
    unittest.main()
