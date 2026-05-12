from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from app.services.input_reader import read_script_input
from app.services.json_utils import extract_json
from app.services.llm_client import LLMClient
from app.services.director_brief import append_director_brief_section
from app.services.tencent_video_data.report_integration import append_market_feedback_section


PATHS_FILE = PROJECT_ROOT / "configs" / "paths.yaml"
MODEL_FILE = PROJECT_ROOT / "configs" / "model.yaml"
RUBRIC_FILE = PROJECT_ROOT / "app" / "rubrics" / "script_text_review_rubric.yaml"
PROBLEM_TAGS_FILE = PROJECT_ROOT / "app" / "rubrics" / "problem_tags.yaml"

PARSER_PROMPT_FILE = PROJECT_ROOT / "app" / "prompts" / "01_script_content_parser.md"
SCORING_PROMPT_FILE = PROJECT_ROOT / "app" / "prompts" / "02_script_scoring.md"
REPORT_PROMPT_FILE = PROJECT_ROOT / "app" / "prompts" / "03_visual_report_generator.md"
DEFAULT_AUDIT_FOCUS = """
短剧爽剧市场适配性审核。

重点关注：
1. 前3集是否有强钩子
2. 主角目标是否足够明确
3. 是否有持续压迫和反击
4. 爽点密度是否足够
5. 反转频率是否适合短剧
6. 每集结尾是否有追更悬念
7. 情绪补偿是否及时
8. 人物关系是否有张力
9. 是否具备完播潜力
10. 是否具备评论互动和传播话题
""".strip()


def read_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def save_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def build_parser_user_prompt(script_title: str, script_text: str, audit_focus: str) -> str:
    return f"""
请解析以下剧本文本。

请严格按照以下审核视角进行解析：

audit_focus:
{audit_focus}

script_title:
{script_title}

script_text:
{script_text}
""".strip()


def build_scoring_user_prompt(
    parsed_features: Dict[str, Any],
    rubric: Dict[str, Any],
    problem_tags: Dict[str, Any],
    audit_focus: str,
) -> str:
    return f"""
请根据以下审核视角、剧本结构化解析结果、评分维度表、问题标签表，对剧本进行分项评分。

【审核视角】
{audit_focus}

评分时必须优先考虑该剧本是否适合短剧爽剧市场，而不是只判断故事是否完整。

【剧本结构化解析结果】
{json.dumps(parsed_features, ensure_ascii=False, indent=2)}

【评分维度表】
{json.dumps(rubric, ensure_ascii=False, indent=2)}

【问题标签表】
{json.dumps(problem_tags, ensure_ascii=False, indent=2)}
""".strip()


def build_report_user_prompt(
    parsed_features: Dict[str, Any],
    scoring_result: Dict[str, Any],
    audit_focus: str,
) -> str:
    return f"""
请根据以下审核视角、剧本结构化解析结果和评分结果，生成可视化分析数据与自然语言审核总结。

【审核视角】
{audit_focus}

报告必须从短剧爽剧市场适配性的角度说明：
1. 为什么这个剧本适合或不适合短剧
2. 爽点、反转、压迫、情绪补偿是否足够
3. 前期钩子和结尾悬念是否能支撑追更
4. 哪些修改最能提升完播潜力和互动潜力

【剧本结构化解析结果】
{json.dumps(parsed_features, ensure_ascii=False, indent=2)}

【评分结果】
{json.dumps(scoring_result, ensure_ascii=False, indent=2)}
""".strip()

def build_report_repair_user_prompt(
    script_title: str,
    audit_focus: str,
    parsed_features: Dict[str, Any],
    scoring_result: Dict[str, Any],
    invalid_report: Any,
    validation_error: str,
) -> str:
    return f"""
你上一次生成的可视化审核报告 JSON 不符合系统要求。

错误原因：
{validation_error}

请基于以下信息，重新生成一个完整、合法、可解析的 JSON object。

【强制要求】
1. 只能输出 JSON object
2. 禁止输出 Markdown
3. 禁止输出解释文字
4. 禁止只输出单个 episode 对象
5. 禁止只输出数组
6. 禁止只输出局部 JSON
7. 必须包含 visual_data、priority_suggestions、text_report 三个顶层字段

【visual_data 必须包含】
score_card
radar_chart
bar_chart
episode_pace_curve
emotion_curve
reversal_distribution
problem_tag_distribution

【score_card 必须包含】
script_title
total_score
level
confidence
final_recommendation

【text_report 必须包含】
summary
dimension_explanation
strengths
weaknesses
suggestions
risks
final_conclusion

【剧本标题】
{script_title}

【审核视角】
{audit_focus}

【剧本结构化解析结果】
{json.dumps(parsed_features, ensure_ascii=False, indent=2)}

【评分结果】
{json.dumps(scoring_result, ensure_ascii=False, indent=2)}

【上一次不合格的 JSON】
{json.dumps(invalid_report, ensure_ascii=False, indent=2)}
""".strip()

def normalize_visual_report(data: Any) -> Dict[str, Any]:
    """
    兼容 LLM 偶尔把 visual report 包成数组的情况。

    正常期望：
    {
      "visual_data": {...},
      "priority_suggestions": {...},
      "text_report": {...}
    }

    兼容：
    [
      {
        "visual_data": {...},
        "priority_suggestions": {...},
        "text_report": {...}
      }
    ]

    也兼容：
    [
      {"visual_data": {...}},
      {"priority_suggestions": {...}},
      {"text_report": {...}}
    ]
    """

    if isinstance(data, dict):
        return data

    if isinstance(data, list):
        if len(data) == 1 and isinstance(data[0], dict):
            return data[0]

        merged: Dict[str, Any] = {}
        for item in data:
            if isinstance(item, dict):
                merged.update(item)

        if merged:
            return merged

        raise ValueError("visual_report 是数组，但数组内没有可合并的对象。")

    raise TypeError(f"visual_report 类型错误，期望 dict 或 list，实际为：{type(data)}")


def validate_visual_report_schema(report: Dict[str, Any]) -> None:
    """
    校验第三步生成的可视化报告是否完整。

    作用：
    1. 防止模型只返回 episode_pace_curve 的某一项
    2. 防止缺少 total_score / level / confidence 的坏报告进入网页
    3. 让错误在运行时暴露，而不是保存成空白网页结果
    """

    if not isinstance(report, dict):
        raise ValueError("visual_report 必须是 JSON object")

    visual_data = report.get("visual_data")
    if not isinstance(visual_data, dict):
        raise ValueError("visual_report 缺少 visual_data 对象")

    score_card = visual_data.get("score_card")
    if not isinstance(score_card, dict):
        raise ValueError("visual_report 缺少 visual_data.score_card 对象")

    required_score_fields = [
        "script_title",
        "total_score",
        "level",
        "confidence",
        "final_recommendation",
    ]

    missing_score_fields = [
        field
        for field in required_score_fields
        if score_card.get(field) in (None, "")
    ]

    if missing_score_fields:
        raise ValueError(
            f"visual_report 的 score_card 字段不完整：{missing_score_fields}"
        )

    required_visual_arrays = [
        "radar_chart",
        "bar_chart",
        "episode_pace_curve",
        "emotion_curve",
        "problem_tag_distribution",
    ]

    missing_visual_arrays = [
        field
        for field in required_visual_arrays
        if not isinstance(visual_data.get(field), list)
    ]

    if missing_visual_arrays:
        raise ValueError(
            f"visual_report 缺少可视化数组字段：{missing_visual_arrays}"
        )

    text_report = report.get("text_report")
    if not isinstance(text_report, dict):
        raise ValueError("visual_report 缺少 text_report 对象")

    if not text_report.get("summary"):
        raise ValueError("visual_report 缺少 text_report.summary")

    if not isinstance(text_report.get("dimension_explanation"), list):
        raise ValueError("visual_report 缺少 text_report.dimension_explanation 数组")


def build_markdown_report(visual_report: Any) -> str:
    visual_report = normalize_visual_report(visual_report)

    text_report = visual_report.get("text_report", {})
    visual_data = visual_report.get("visual_data", {})
    score_card = visual_data.get("score_card", {})

    lines = [
        f"# 剧本审核报告：{score_card.get('script_title', '')}",
        "",
        "## 一、综合结论",
        "",
        str(text_report.get("summary", "")),
        "",
        f"- 综合评分：{score_card.get('total_score', '')} / 100",
        f"- 审核等级：{score_card.get('level', '')}",
        f"- 置信度：{score_card.get('confidence', '')}",
        f"- 最终建议：{score_card.get('final_recommendation', '')}",
        "",
        "## 二、分项评分说明",
        "",
    ]

    for item in text_report.get("dimension_explanation", []):
        lines.append(f"- {item}")

    lines.extend(["", "## 三、主要优势", ""])
    for item in text_report.get("strengths", []):
        lines.append(f"- {item}")

    lines.extend(["", "## 四、主要问题", ""])
    for item in text_report.get("weaknesses", []):
        lines.append(f"- {item}")

    lines.extend(["", "## 五、修改建议", ""])
    for item in text_report.get("suggestions", []):
        lines.append(f"- {item}")

    lines.extend(["", "## 六、风险提示", ""])
    for item in text_report.get("risks", []):
        lines.append(f"- {item}")

    lines.extend(["", "## 七、审核结论", ""])
    lines.append(str(text_report.get("final_conclusion", "")))

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="剧本文本文件路径")
    parser.add_argument("--title", required=True, help="剧本标题")
    parser.add_argument(
        "--focus",
        default=DEFAULT_AUDIT_FOCUS,
        help="审核视角，默认是短剧爽剧市场适配性审核",
    )
    args = parser.parse_args()


    input_path = Path(args.input)
    script_title = args.title
    script_text = read_script_input(input_path)
    audit_focus = args.focus

    paths = read_yaml(PATHS_FILE)
    model_config = read_yaml(MODEL_FILE)
    rubric = read_yaml(RUBRIC_FILE)
    problem_tags = read_yaml(PROBLEM_TAGS_FILE)

    llm = LLMClient.from_config(model_config)

    script_id = f"llm_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

    raw_script_record = {
        "script_id": script_id,
        "script_title": script_title,
        "source_file": str(input_path),
        "script_text": script_text,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "audit_focus": audit_focus,
    }

    print("Step 1/3: parsing script content...")
    parser_system_prompt = read_text(PARSER_PROMPT_FILE)
    parser_user_prompt = build_parser_user_prompt(script_title, script_text, audit_focus)
    parser_response = llm.chat(parser_system_prompt, parser_user_prompt)
    parsed_features = extract_json(parser_response)

    print("Step 2/3: scoring script...")
    scoring_system_prompt = read_text(SCORING_PROMPT_FILE)
    scoring_user_prompt = build_scoring_user_prompt(
        parsed_features,
        rubric,
        problem_tags,
        audit_focus,
    )
    scoring_response = llm.chat(scoring_system_prompt, scoring_user_prompt)
    scoring_result = extract_json(scoring_response)

    print("Step 3/3: generating visual report...")
    report_system_prompt = read_text(REPORT_PROMPT_FILE)
    report_user_prompt = build_report_user_prompt(
        parsed_features,
        scoring_result,
        audit_focus,
    )
    report_response = llm.chat(report_system_prompt, report_user_prompt)

    debug_dir = Path(paths["data_root"]) / "debug_llm_responses"
    debug_dir.mkdir(parents=True, exist_ok=True)
    save_text(debug_dir / f"{script_id}_03_report_raw.txt", report_response)

    raw_visual_report = extract_json(report_response)
    visual_report = normalize_visual_report(raw_visual_report)

    visual_report.setdefault("visual_data", {})
    visual_report["visual_data"].setdefault("score_card", {})
    visual_report["visual_data"]["score_card"].setdefault("script_title", script_title)

    try:
        validate_visual_report_schema(visual_report)
    except Exception as exc:
        print(f"Visual report schema invalid, trying repair once: {exc}")

        repair_user_prompt = build_report_repair_user_prompt(
            script_title=script_title,
            audit_focus=audit_focus,
            parsed_features=parsed_features,
            scoring_result=scoring_result,
            invalid_report=visual_report,
            validation_error=str(exc),
        )

        repair_response = llm.chat(report_system_prompt, repair_user_prompt)
        save_text(debug_dir / f"{script_id}_03_report_repair_raw.txt", repair_response)

        repaired_raw_visual_report = extract_json(repair_response)
        visual_report = normalize_visual_report(repaired_raw_visual_report)

        visual_report.setdefault("visual_data", {})
        visual_report["visual_data"].setdefault("score_card", {})
        visual_report["visual_data"]["score_card"].setdefault("script_title", script_title)

        validate_visual_report_schema(visual_report)

    markdown_report = append_market_feedback_section(
        build_markdown_report(visual_report),
        PROJECT_ROOT / "data" / "tencent_video_normalized" / "market_feedback_summary.json",
    )
    markdown_report = append_director_brief_section(
        markdown_report,
        PROJECT_ROOT / "data" / "director_brief" / "director_brief.json",
    )

    save_json(Path(paths["raw_scripts_dir"]) / f"{script_id}.json", raw_script_record)
    save_json(Path(paths["parsed_features_dir"]) / f"{script_id}_features.json", parsed_features)
    save_json(Path(paths["scoring_results_dir"]) / f"{script_id}_scores.json", scoring_result)
    save_json(Path(paths["visual_data_dir"]) / f"{script_id}_visual_report.json", visual_report)
    save_text(Path(paths["reports_dir"]) / f"{script_id}_report.md", markdown_report)

    training_sample = {
        "script_id": script_id,
        "audit_focus": audit_focus,
        "raw_script": raw_script_record,
        "parsed_features": parsed_features,
        "scoring_result": scoring_result,
        "visual_report": visual_report,
        "markdown_report": markdown_report,
    }

    save_json(Path(paths["training_samples_dir"]) / f"{script_id}_training_sample.json", training_sample)

    print("LLM review completed.")
    print(f"script_id: {script_id}")
    print(f"report: {Path(paths['reports_dir']) / f'{script_id}_report.md'}")
    print(f"visual_data: {Path(paths['visual_data_dir']) / f'{script_id}_visual_report.json'}")


if __name__ == "__main__":
    main()
