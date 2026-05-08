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


from app.services.json_utils import extract_json
from app.services.llm_client import LLMClient


PATHS_FILE = PROJECT_ROOT / "configs" / "paths.yaml"
MODEL_FILE = PROJECT_ROOT / "configs" / "model.yaml"
RUBRIC_FILE = PROJECT_ROOT / "app" / "rubrics" / "script_text_review_rubric.yaml"
PROBLEM_TAGS_FILE = PROJECT_ROOT / "app" / "rubrics" / "problem_tags.yaml"

PARSER_PROMPT_FILE = PROJECT_ROOT / "app" / "prompts" / "01_script_content_parser.md"
SCORING_PROMPT_FILE = PROJECT_ROOT / "app" / "prompts" / "02_script_scoring.md"
REPORT_PROMPT_FILE = PROJECT_ROOT / "app" / "prompts" / "03_visual_report_generator.md"


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


def build_parser_user_prompt(script_title: str, script_text: str) -> str:
    return f"""
请解析以下剧本文本。

script_title:
{script_title}

script_text:
{script_text}
""".strip()


def build_scoring_user_prompt(
    parsed_features: Dict[str, Any],
    rubric: Dict[str, Any],
    problem_tags: Dict[str, Any],
) -> str:
    return f"""
请根据以下剧本结构化解析结果、评分维度表、问题标签表，对剧本进行分项评分。

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
) -> str:
    return f"""
请根据以下剧本结构化解析结果和评分结果，生成可视化分析数据与自然语言审核总结。

【剧本结构化解析结果】
{json.dumps(parsed_features, ensure_ascii=False, indent=2)}

【评分结果】
{json.dumps(scoring_result, ensure_ascii=False, indent=2)}
""".strip()


def build_markdown_report(visual_report: Dict[str, Any]) -> str:
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
    args = parser.parse_args()

    input_path = Path(args.input)
    script_title = args.title
    script_text = read_text(input_path)

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
    }

    print("Step 1/3: parsing script content...")
    parser_system_prompt = read_text(PARSER_PROMPT_FILE)
    parser_user_prompt = build_parser_user_prompt(script_title, script_text)
    parser_response = llm.chat(parser_system_prompt, parser_user_prompt)
    parsed_features = extract_json(parser_response)

    print("Step 2/3: scoring script...")
    scoring_system_prompt = read_text(SCORING_PROMPT_FILE)
    scoring_user_prompt = build_scoring_user_prompt(parsed_features, rubric, problem_tags)
    scoring_response = llm.chat(scoring_system_prompt, scoring_user_prompt)
    scoring_result = extract_json(scoring_response)

    print("Step 3/3: generating visual report...")
    report_system_prompt = read_text(REPORT_PROMPT_FILE)
    report_user_prompt = build_report_user_prompt(parsed_features, scoring_result)
    report_response = llm.chat(report_system_prompt, report_user_prompt)
    visual_report = extract_json(report_response)

    markdown_report = build_markdown_report(visual_report)

    save_json(Path(paths["raw_scripts_dir"]) / f"{script_id}.json", raw_script_record)
    save_json(Path(paths["parsed_features_dir"]) / f"{script_id}_features.json", parsed_features)
    save_json(Path(paths["scoring_results_dir"]) / f"{script_id}_scores.json", scoring_result)
    save_json(Path(paths["visual_data_dir"]) / f"{script_id}_visual_report.json", visual_report)
    save_text(Path(paths["reports_dir"]) / f"{script_id}_report.md", markdown_report)

    training_sample = {
        "script_id": script_id,
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