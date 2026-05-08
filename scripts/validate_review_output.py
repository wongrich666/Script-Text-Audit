from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REQUIRED_TOP_LEVEL_KEYS = [
    "visual_data",
    "priority_suggestions",
    "text_report",
]

REQUIRED_VISUAL_DATA_KEYS = [
    "score_card",
    "radar_chart",
    "bar_chart",
    "episode_pace_curve",
    "emotion_curve",
    "reversal_distribution",
    "problem_tag_distribution",
]

REQUIRED_SCORE_CARD_KEYS = [
    "total_score",
    "level",
    "confidence",
    "final_recommendation",
]

REQUIRED_TEXT_REPORT_KEYS = [
    "summary",
    "dimension_explanation",
    "strengths",
    "weaknesses",
    "suggestions",
    "risks",
    "final_conclusion",
]


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def require_keys(obj: dict, keys: list[str], path: str, errors: list[str]) -> None:
    for key in keys:
        if key not in obj:
            errors.append(f"缺少字段：{path}.{key}")


def validate_visual_report(data: dict) -> list[str]:
    errors: list[str] = []

    require_keys(data, REQUIRED_TOP_LEVEL_KEYS, "root", errors)

    visual_data = data.get("visual_data", {})
    if not isinstance(visual_data, dict):
        errors.append("root.visual_data 必须是对象")
        return errors

    require_keys(visual_data, REQUIRED_VISUAL_DATA_KEYS, "root.visual_data", errors)

    score_card = visual_data.get("score_card", {})
    if not isinstance(score_card, dict):
        errors.append("root.visual_data.score_card 必须是对象")
    else:
        require_keys(
            score_card,
            REQUIRED_SCORE_CARD_KEYS,
            "root.visual_data.score_card",
            errors,
        )

    text_report = data.get("text_report", {})
    if not isinstance(text_report, dict):
        errors.append("root.text_report 必须是对象")
    else:
        require_keys(text_report, REQUIRED_TEXT_REPORT_KEYS, "root.text_report", errors)

    radar_chart = visual_data.get("radar_chart", [])
    if not isinstance(radar_chart, list) or not radar_chart:
        errors.append("root.visual_data.radar_chart 必须是非空数组")

    bar_chart = visual_data.get("bar_chart", [])
    if not isinstance(bar_chart, list) or not bar_chart:
        errors.append("root.visual_data.bar_chart 必须是非空数组")

    episode_pace_curve = visual_data.get("episode_pace_curve", [])
    if not isinstance(episode_pace_curve, list):
        errors.append("root.visual_data.episode_pace_curve 必须是数组")

    emotion_curve = visual_data.get("emotion_curve", [])
    if not isinstance(emotion_curve, list):
        errors.append("root.visual_data.emotion_curve 必须是数组")

    return errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="visual_report.json 文件路径")
    args = parser.parse_args()

    path = Path(args.input)
    data = load_json(path)

    errors = validate_visual_report(data)

    if errors:
        print("校验失败：")
        for error in errors:
            print(f"- {error}")
        raise SystemExit(1)

    print("校验通过。")
    print(f"file: {path}")


if __name__ == "__main__":
    main()
