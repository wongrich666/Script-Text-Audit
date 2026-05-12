from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from app.services.director_brief import append_director_brief_section
from app.services.tencent_video_data.report_integration import append_market_feedback_section

PATHS_FILE = PROJECT_ROOT / "configs" / "paths.yaml"
RUBRIC_FILE = PROJECT_ROOT / "app" / "rubrics" / "script_text_review_rubric.yaml"
PROBLEM_TAGS_FILE = PROJECT_ROOT / "app" / "rubrics" / "problem_tags.yaml"


DEMO_SCRIPT = """
剧名：《她从废墟里归来》

类型：重生复仇短剧

故事梗概：
女主林晚曾是豪门养女，被未婚夫和养妹联手陷害，失去家产和名誉，最终惨死雨夜。
重生后，她回到订婚宴当天，决定不再隐忍，先揭穿养妹伪善面目，再夺回母亲留下的公司股权。
男主顾沉是冷峻律师，表面与林晚利益合作，实际一直在调查林家旧案。
反派养妹林悦擅长伪装柔弱，未婚夫沈舟则利用林晚获取商业资源。
全剧围绕林晚复仇、夺权、查明母亲死亡真相展开。

分集大纲：
第1集：林晚重生回到订婚宴，发现沈舟和林悦正在设计让她当众出丑。她临场反击，播放录音让林悦露出破绽。
第2集：林悦装病博取同情，沈舟指责林晚冷血。林晚故意退让，引出沈舟转移资产的证据。
第3集：顾沉出现，提出帮助林晚打股权官司。结尾林晚发现母亲死亡当天，顾沉也在现场。
第4集：林晚开始调查母亲遗物，发现一份被隐藏的股份转让协议。
第5集：林悦安排媒体抹黑林晚，林晚陷入舆论危机。
第6集：林晚反击媒体，但剧情主要集中在解释过去公司斗争，冲突略弱。
第7集：沈舟试图求和，林晚识破他的真实目的。
第8集：顾沉查到林母死亡与沈家有关，林晚决定公开旧案。
第9集：林悦身份反转，她并非林家亲生女，而是沈家安插进来的棋子。
第10集：林晚在股东大会上公开证据，夺回公司控制权。
第11集：沈舟狗急跳墙绑架林晚，顾沉救下她。
第12集：林晚公开真相，林悦和沈舟受到惩罚，林晚重新掌控人生。
"""


def read_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_json(path: Path, data: Dict[str, Any] | List[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def save_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def normalize_score(score: float, max_score: float) -> int:
    if max_score <= 0:
        return 0
    return round(score / max_score * 100)


def mock_parse_script(script_title: str, script_text: str) -> Dict[str, Any]:
    """第一版本地模拟解析。后续这里替换为真实 LLM 内容解析调用。"""

    return {
        "script_title": script_title,
        "genre_tags": ["重生", "复仇", "豪门", "逆袭"],
        "core_premise": "女主惨死后重生回到订婚宴当天，利用前世记忆揭穿养妹与未婚夫阴谋，夺回家产并查明母亲死亡真相。",
        "main_character": {
            "name": "林晚",
            "identity": "豪门养女 / 重生复仇女主",
            "goal": "揭穿养妹和未婚夫阴谋，夺回母亲留下的公司股权，查清母亲死亡真相。",
            "motivation": "前世被陷害致死，重生后不再隐忍。",
            "weakness": "前期容易被舆论和亲情关系牵制。",
            "growth_arc": "从被动受害者转变为主动布局、掌控局势的复仇者。"
        },
        "antagonist_or_pressure": {
            "name": "林悦、沈舟",
            "type": "伪善养妹 + 利益型未婚夫",
            "pressure_method": "舆论抹黑、商业夺权、情感操控、身份欺骗。",
            "motivation": "争夺林家资源和公司利益。",
            "conflict_with_protagonist": "围绕婚约、股权、家族真相和母亲死亡旧案展开。"
        },
        "character_relationships": [
            "林晚与林悦：养姐妹关系，表面亲近，实则长期竞争和陷害。",
            "林晚与沈舟：未婚夫妻关系，实为利益利用。",
            "林晚与顾沉：合作关系，后续可能发展为信任关系。"
        ],
        "core_conflict": "女主重生后与养妹、未婚夫围绕家产、名誉、股权和旧案真相展开对抗。",
        "opening_hook": {
            "summary": "女主重生回到订婚宴，当场反击陷害。",
            "strength_estimate": 85,
            "problems": ["订婚宴反击具备钩子，但第一集可进一步强化更强的生死记忆刺激。"]
        },
        "episode_analysis": [
            {
                "episode": 1,
                "main_event": "女主重生并在订婚宴反击。",
                "conflict": "林悦和沈舟设计女主出丑。",
                "emotional_point": "重生、复仇、当众反击。",
                "reversal": "女主从被害者变成反击者。",
                "cliffhanger": "林悦露出破绽。",
                "risk": ""
            },
            {
                "episode": 2,
                "main_event": "林悦装病，林晚引出沈舟资产证据。",
                "conflict": "林晚被指责冷血。",
                "emotional_point": "憋屈后反制。",
                "reversal": "退让其实是布局。",
                "cliffhanger": "沈舟转移资产证据出现。",
                "risk": ""
            },
            {
                "episode": 3,
                "main_event": "顾沉出现并提出合作。",
                "conflict": "林晚开始面对股权官司。",
                "emotional_point": "合作与怀疑并存。",
                "reversal": "顾沉与林母死亡现场有关。",
                "cliffhanger": "顾沉旧案关联暴露。",
                "risk": ""
            },
            {
                "episode": 4,
                "main_event": "林晚调查母亲遗物。",
                "conflict": "隐藏股份协议浮出水面。",
                "emotional_point": "真相推进。",
                "reversal": "母亲遗物暗藏关键证据。",
                "cliffhanger": "股份转让协议被发现。",
                "risk": ""
            },
            {
                "episode": 5,
                "main_event": "林悦安排媒体抹黑林晚。",
                "conflict": "林晚陷入舆论危机。",
                "emotional_point": "压迫、愤怒。",
                "reversal": "",
                "cliffhanger": "舆论危机升级。",
                "risk": "反转不足。"
            },
            {
                "episode": 6,
                "main_event": "林晚反击媒体。",
                "conflict": "公司旧斗争被解释。",
                "emotional_point": "信息揭露。",
                "reversal": "",
                "cliffhanger": "",
                "risk": "解释性内容偏多，冲突偏弱。"
            },
            {
                "episode": 7,
                "main_event": "沈舟求和，林晚识破目的。",
                "conflict": "情感操控与反操控。",
                "emotional_point": "识破、反击。",
                "reversal": "沈舟求和是假。",
                "cliffhanger": "沈舟目的暴露。",
                "risk": ""
            },
            {
                "episode": 8,
                "main_event": "顾沉查到林母死亡与沈家有关。",
                "conflict": "旧案逼近真相。",
                "emotional_point": "震惊、愤怒。",
                "reversal": "沈家卷入旧案。",
                "cliffhanger": "林晚决定公开旧案。",
                "risk": ""
            },
            {
                "episode": 9,
                "main_event": "林悦身份反转。",
                "conflict": "林悦真实身份暴露。",
                "emotional_point": "强反转。",
                "reversal": "林悦不是林家亲生女，而是沈家棋子。",
                "cliffhanger": "沈家阴谋扩大。",
                "risk": ""
            },
            {
                "episode": 10,
                "main_event": "林晚股东大会公开证据。",
                "conflict": "公司控制权争夺。",
                "emotional_point": "爽点释放。",
                "reversal": "林晚夺回公司控制权。",
                "cliffhanger": "沈舟败局初现。",
                "risk": ""
            },
            {
                "episode": 11,
                "main_event": "沈舟绑架林晚，顾沉救人。",
                "conflict": "沈舟极端反扑。",
                "emotional_point": "危险、救援。",
                "reversal": "",
                "cliffhanger": "最终真相即将公开。",
                "risk": "绑架桥段略常规。"
            },
            {
                "episode": 12,
                "main_event": "林晚公开真相，完成复仇。",
                "conflict": "最终清算。",
                "emotional_point": "惩罚、补偿、完成。",
                "reversal": "",
                "cliffhanger": "",
                "risk": ""
            }
        ],
        "plot_features": {
            "conflict_density": "前3集较强，第5-6集略降，第8-10集重新增强。",
            "reversal_points": [
                {"episode": 1, "type": "局势反转", "description": "女主当众反击陷害。", "strength": 80},
                {"episode": 3, "type": "认知反转", "description": "顾沉与林母死亡现场有关。", "strength": 75},
                {"episode": 9, "type": "身份反转", "description": "林悦并非林家亲生女，而是沈家棋子。", "strength": 90},
                {"episode": 10, "type": "利益反转", "description": "林晚夺回公司控制权。", "strength": 85}
            ],
            "emotional_curve_summary": "前期复仇爽感较强，中段第5-6集压迫和解释增加，后期第9-10集爽点释放明显。",
            "cliffhanger_quality": "前三集和第9集较强，第6集较弱。",
            "main_plot_progress": "主线较清楚，但中段部分集数推进效率下降。"
        },
        "emotion_features": {
            "爽感": "第1集、第9集、第10集较强。",
            "虐感": "前世惨死设定和第5集舆论危机提供一定虐感。",
            "憋屈感": "第2集、第5集有明显憋屈。",
            "反击感": "第1集、第2集、第10集较强。",
            "期待感": "旧案真相和顾沉身份关系提供期待。",
            "情绪补偿": "后期补偿较强，中段补偿略不及时。"
        },
        "dialogue_features": {
            "style": "偏短剧化，具备对抗感。",
            "strengths": ["人物关系清晰", "冲突场景容易形成强台词"],
            "problems": ["第6集可能解释性对白过多", "部分旧案信息适合通过行动推进"],
            "short_drama_suitability": "中高"
        },
        "pace_features": {
            "opening_pace": "较快",
            "middle_pace": "第5-6集略慢",
            "ending_pace": "较集中，复仇完成明确",
            "main_problem": "中段解释性信息较多，反转密度下降。"
        },
        "production_features": {
            "scene_complexity": "中等，主要集中在订婚宴、公司、媒体危机、股东大会等场景。",
            "character_count_estimate": "主要角色约5-7人。",
            "shooting_difficulty": "中等，适合短剧生产。"
        },
        "risks": [
            "中段拖沓风险",
            "反派动机需要进一步强化",
            "部分桥段同质化风险"
        ]
    }


def mock_score_script(
    parsed: Dict[str, Any],
    rubric: Dict[str, Any],
    problem_tags: Dict[str, Any],
) -> Dict[str, Any]:
    """第一版本地模拟评分。后续这里替换为真实 LLM 分项评分调用。"""

    raw_scores = {
        "genre_clarity": 7,
        "opening_hook": 10,
        "protagonist_goal": 9,
        "relationship_tension": 7,
        "conflict_strength": 8,
        "reversal_design": 8,
        "emotional_drive": 8,
        "pace_control": 7,
        "dialogue_quality": 6,
        "completion_potential": 7,
        "interaction_potential": 4,
        "revision_value": 8,
    }

    reasons = {
        "genre_clarity": "重生复仇、豪门逆袭类型明确，受众识别成本低。",
        "opening_hook": "订婚宴重生反击具备强开局，但前世惨死刺激还可以前置强化。",
        "protagonist_goal": "主角目标清楚，包括复仇、夺权和查明母亲死亡真相。",
        "relationship_tension": "养妹、未婚夫、律师男主之间关系有冲突和悬念。",
        "conflict_strength": "前期和后期冲突较强，中段第5-6集略偏解释。",
        "reversal_design": "第1、3、9、10集均有反转，其中第9集身份反转较强。",
        "emotional_drive": "复仇爽点明确，憋屈和反击有基本节奏。",
        "pace_control": "整体节奏可用，但第5-6集中段存在拖沓风险。",
        "dialogue_quality": "具备短剧对抗台词空间，但旧案解释部分可能偏说明。",
        "completion_potential": "每集追看动力基本成立，第6集钩子偏弱。",
        "interaction_potential": "林悦身份反转和复仇线有讨论点，但CP与争议话题可继续增强。",
        "revision_value": "底层设定完整，主要问题可通过局部优化改善。"
    }

    suggestions = {
        "genre_clarity": "保留重生复仇主类型，同时强化与普通豪门复仇剧的差异点。",
        "opening_hook": "第一集前30秒强化前世惨死记忆与订婚宴危机的连接。",
        "protagonist_goal": "在前三集持续提醒主角阶段目标，避免目标被支线稀释。",
        "relationship_tension": "增加顾沉与林晚之间的利益试探和信任冲突。",
        "conflict_strength": "第5-6集减少解释，增加反派主动压迫事件。",
        "reversal_design": "在第6集增加一次小反转，避免中段平缓。",
        "emotional_drive": "缩短憋屈持续时间，增加阶段性反击和补偿。",
        "pace_control": "压缩公司旧案解释，把信息放入冲突场景中呈现。",
        "dialogue_quality": "减少说明性对白，增加对抗性短句和人物态度表达。",
        "completion_potential": "强化第6集结尾钩子，让观众期待第7集反制。",
        "interaction_potential": "增加容易引发讨论的角色选择、身份秘密或道德困境。",
        "revision_value": "优先优化中段节奏、反派动机和第6集钩子。"
    }

    dimension_scores = []
    total_score = 0

    for dim in rubric["dimensions"]:
        key = dim["key"]
        score = raw_scores.get(key, 0)
        max_score = dim["max_score"]
        total_score += score
        dimension_scores.append(
            {
                "key": key,
                "name": dim["name"],
                "score": score,
                "max_score": max_score,
                "reason": reasons.get(key, ""),
                "evidence": parsed.get("core_conflict", ""),
                "suggestion": suggestions.get(key, "")
            }
        )

    selected_problem_tags = [
        {
            "key": "s轻度_middle",
            "name": "中段拖沓",
            "level": "严重",
            "description": "第5-6集主线推进效率下降，解释性内容增加。",
            "evidence": "第6集主要集中在解释过去公司斗争，冲突略弱。",
            "suggestion": "将旧案信息放入对抗事件中呈现，并增加一次中段反转。"
        },
        {
            "key": "weak_antagonist_motivation",
            "name": "反派动机不足",
            "level": "中等",
            "description": "反派压迫行为明确，但利益动机还可以进一步具体化。",
            "evidence": "林悦和沈舟争夺资源，但具体利益链条可再加强。",
            "suggestion": "补充林悦和沈舟必须打压林晚的具体利益原因。"
        },
        {
            "key": "excessive_exposition",
            "name": "台词解释过多",
            "level": "中等",
            "description": "旧案和公司斗争信息可能依赖解释性对白。",
            "evidence": "第6集剧情主要集中在解释过去公司斗争。",
            "suggestion": "减少口头说明，用证据、行动和冲突推进信息揭露。"
        }
    ]

    level = "中高" if total_score >= 75 else "中"
    confidence = "中"
    final_recommendation = "建议重点修改后继续推进"

    return {
        "summary": {
            "script_title": parsed["script_title"],
            "total_score": total_score,
            "level": level,
            "confidence": confidence,
            "final_recommendation": final_recommendation
        },
        "dimension_scores": dimension_scores,
        "problem_tags": selected_problem_tags,
        "strengths": [
            "题材类型明确，符合短剧复仇逆袭受众预期。",
            "主角目标清楚，复仇、夺权和查案三条动力线较稳定。",
            "第1集订婚宴反击和第9集身份反转具备较强爽点。"
        ],
        "weaknesses": [
            "第5-6集中段存在节奏下滑。",
            "反派动机可以进一步具体化。",
            "部分旧案信息可能过度依赖解释性对白。"
        ],
        "risk_flags": [
            "中段拖沓风险",
            "反派动机不足风险",
            "同质化风险"
        ],
        "priority_suggestions": {
            "严重": [
                "优化第5-6集主线推进，减少解释性内容。",
                "为第6集增加一次小反转或强钩子。"
            ],
            "中等": [
                "补充林悦和沈舟的具体利益动机。",
                "增加顾沉与林晚的信任冲突。"
            ],
            "轻度": [
                "优化旧案说明部分台词。",
                "增加1-2句更具传播性的短剧金句。"
            ]
        }
    }


def build_visual_report(parsed: Dict[str, Any], scoring: Dict[str, Any]) -> Dict[str, Any]:
    """生成前端可视化数据和文本报告。"""

    radar_chart = []
    bar_chart = []

    for item in scoring["dimension_scores"]:
        normalized = normalize_score(item["score"], item["max_score"])
        radar_chart.append(
            {
                "dimension": item["name"],
                "score": normalized,
                "max_score": 100
            }
        )
        bar_chart.append(
            {
                "dimension": item["name"],
                "score": normalized,
                "max_score": 100
            }
        )

    episode_pace_curve = []
    emotion_curve = []

    for ep in parsed["episode_analysis"]:
        episode = ep["episode"]
        risk = ep.get("risk") or ""
        has_reversal = bool(ep.get("reversal"))

        conflict_strength = 70
        pace_score = 70
        emotion_intensity = 70
        hook_strength = 70
        main_plot_progress = 70

        if episode in [1, 2, 3, 9, 10]:
            conflict_strength += 15
            hook_strength += 15
            emotion_intensity += 10

        if episode in [5, 6]:
            pace_score -= 20
            main_plot_progress -= 15
            hook_strength -= 10

        if has_reversal:
            hook_strength += 10
            emotion_intensity += 10

        if "解释" in risk or "冲突偏弱" in risk:
            pace_score -= 10

        episode_pace_curve.append(
            {
                "episode": episode,
                "conflict_strength": max(0, min(100, conflict_strength)),
                "pace_score": max(0, min(100, pace_score)),
                "emotion_intensity": max(0, min(100, emotion_intensity)),
                "hook_strength": max(0, min(100, hook_strength)),
                "main_plot_progress": max(0, min(100, main_plot_progress)),
            }
        )

        emotion_curve.append(
            {
                "episode": episode,
                "爽感": 80 if episode in [1, 2, 9, 10, 12] else 55,
                "虐感": 75 if episode in [1, 5, 11] else 45,
                "憋屈感": 75 if episode in [2, 5, 6] else 40,
                "反击感": 85 if episode in [1, 2, 7, 10, 12] else 50,
                "期待感": 85 if episode in [3, 8, 9] else 60,
            }
        )

    problem_tag_distribution = []
    for tag in scoring["problem_tags"]:
        problem_tag_distribution.append(
            {
                "tag": tag["name"],
                "count": 1,
                "level": tag["level"]
            }
        )

    reversal_distribution = parsed["plot_features"]["reversal_points"]

    report = {
        "visual_data": {
            "score_card": scoring["summary"],
            "radar_chart": radar_chart,
            "bar_chart": bar_chart,
            "episode_pace_curve": episode_pace_curve,
            "emotion_curve": emotion_curve,
            "reversal_distribution": reversal_distribution,
            "problem_tag_distribution": problem_tag_distribution
        },
        "priority_suggestions": scoring["priority_suggestions"],
        "text_report": {
            "summary": (
                f"该剧本综合评分为 {scoring['summary']['total_score']} 分，"
                f"审核等级为{scoring['summary']['level']}。整体题材明确，主角目标清楚，"
                "前期复仇钩子和后期身份反转具备较强短剧吸引力。主要问题集中在中段节奏、"
                "反派动机和解释性台词。"
            ),
            "dimension_explanation": [
                f"{item['name']}：{item['score']}/{item['max_score']}。{item['reason']}"
                for item in scoring["dimension_scores"]
            ],
            "strengths": scoring["strengths"],
            "weaknesses": scoring["weaknesses"],
            "suggestions": (
                scoring["priority_suggestions"]["严重"]
                + scoring["priority_suggestions"]["中等"]
                + scoring["priority_suggestions"]["轻度"]
            ),
            "risks": scoring["risk_flags"],
            "final_conclusion": scoring["summary"]["final_recommendation"]
        }
    }

    return report


def build_markdown_report(report: Dict[str, Any]) -> str:
    text_report = report["text_report"]
    score_card = report["visual_data"]["score_card"]

    lines = [
        f"# 剧本审核报告：{score_card['script_title']}",
        "",
        "## 一、综合结论",
        "",
        text_report["summary"],
        "",
        f"- 综合评分：{score_card['total_score']} / 100",
        f"- 审核等级：{score_card['level']}",
        f"- 置信度：{score_card['confidence']}",
        f"- 最终建议：{score_card['final_recommendation']}",
        "",
        "## 二、分项评分说明",
        ""
    ]

    for item in text_report["dimension_explanation"]:
        lines.append(f"- {item}")

    lines.extend(["", "## 三、主要优势", ""])
    for item in text_report["strengths"]:
        lines.append(f"- {item}")

    lines.extend(["", "## 四、主要问题", ""])
    for item in text_report["weaknesses"]:
        lines.append(f"- {item}")

    lines.extend(["", "## 五、修改建议", ""])
    for item in text_report["suggestions"]:
        lines.append(f"- {item}")

    lines.extend(["", "## 六、风险提示", ""])
    for item in text_report["risks"]:
        lines.append(f"- {item}")

    lines.extend(["", "## 七、审核结论", "", text_report["final_conclusion"]])

    return "\n".join(lines)


def main() -> None:
    paths = read_yaml(PATHS_FILE)
    rubric = read_yaml(RUBRIC_FILE)
    problem_tags = read_yaml(PROBLEM_TAGS_FILE)

    script_id = f"demo_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    script_title = "她从废墟里归来"

    raw_script_record = {
        "script_id": script_id,
        "script_title": script_title,
        "script_text": DEMO_SCRIPT.strip(),
        "created_at": datetime.now().isoformat(timespec="seconds")
    }

    parsed = mock_parse_script(script_title, DEMO_SCRIPT)
    scoring = mock_score_script(parsed, rubric, problem_tags)
    visual_report = build_visual_report(parsed, scoring)
    markdown_report = append_market_feedback_section(
        build_markdown_report(visual_report),
        PROJECT_ROOT / "data" / "tencent_video_normalized" / "market_feedback_summary.json",
    )
    markdown_report = append_director_brief_section(
        markdown_report,
        PROJECT_ROOT / "data" / "director_brief" / "director_brief.json",
    )

    raw_scripts_dir = Path(paths["raw_scripts_dir"])
    parsed_features_dir = Path(paths["parsed_features_dir"])
    scoring_results_dir = Path(paths["scoring_results_dir"])
    visual_data_dir = Path(paths["visual_data_dir"])
    reports_dir = Path(paths["reports_dir"])
    training_samples_dir = Path(paths["training_samples_dir"])

    save_json(raw_scripts_dir / f"{script_id}.json", raw_script_record)
    save_json(parsed_features_dir / f"{script_id}_features.json", parsed)
    save_json(scoring_results_dir / f"{script_id}_scores.json", scoring)
    save_json(visual_data_dir / f"{script_id}_visual_report.json", visual_report)
    save_text(reports_dir / f"{script_id}_report.md", markdown_report)

    training_sample = {
        "script_id": script_id,
        "raw_script": raw_script_record,
        "parsed_features": parsed,
        "scoring_result": scoring,
        "visual_report": visual_report,
        "markdown_report": markdown_report
    }
    save_json(training_samples_dir / f"{script_id}_training_sample.json", training_sample)

    print("Demo review completed.")
    print(f"script_id: {script_id}")
    print(f"total_score: {scoring['summary']['total_score']}")
    print(f"level: {scoring['summary']['level']}")
    print(f"report: {reports_dir / f'{script_id}_report.md'}")
    print(f"visual_data: {visual_data_dir / f'{script_id}_visual_report.json'}")


if __name__ == "__main__":
    main()
