from __future__ import annotations
import bleach
import markdown
import html
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import yaml
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, RedirectResponse


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PATHS_FILE = PROJECT_ROOT / "configs" / "paths.yaml"

app = FastAPI(title="Script Text Audit Review UI")


def read_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_paths() -> Dict[str, Any]:
    return read_yaml(PATHS_FILE)


def get_visual_report_files() -> List[Path]:
    paths = get_paths()
    visual_dir = Path(paths["visual_data_dir"])
    if not visual_dir.exists():
        return []
    return sorted(
        visual_dir.glob("*_visual_report.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


def extract_script_id(path: Path) -> str:
    name = path.name
    return name.removesuffix("_visual_report.json")


def load_visual_report(script_id: str) -> Dict[str, Any]:
    paths = get_paths()
    visual_path = Path(paths["visual_data_dir"]) / f"{script_id}_visual_report.json"
    return read_json(visual_path)


def load_raw_script(script_id: str) -> Dict[str, Any]:
    paths = get_paths()
    raw_path = Path(paths["raw_scripts_dir"]) / f"{script_id}.json"
    if raw_path.exists():
        return read_json(raw_path)
    return {}


def load_markdown_report(script_id: str) -> str:
    paths = get_paths()
    report_path = Path(paths["reports_dir"]) / f"{script_id}_report.md"
    if report_path.exists():
        return report_path.read_text(encoding="utf-8")
    return ""


def parse_json_list(value: str) -> List[Any]:
    try:
        parsed = json.loads(value or "[]")
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def parse_json_string_list(value: str) -> List[str]:
    items: List[str] = []
    for item in parse_json_list(value):
        text = str(item).strip()
        if text:
            items.append(text)
    return items


def normalize_score(value: Any, default: int = 60) -> int:
    try:
        score = int(round(float(value)))
    except (TypeError, ValueError):
        return default
    return max(0, min(100, score))


def normalize_suggestion_score(value: Any) -> int:
    try:
        score = int(round(float(value)))
    except (TypeError, ValueError):
        return 0
    return max(0, min(10, score))


def collect_problem_tags(visual_data: Dict[str, Any]) -> List[str]:
    tags: List[str] = []
    for item in visual_data.get("problem_tag_distribution", []) or []:
        if isinstance(item, dict):
            tag = item.get("tag", "")
        else:
            tag = item
        tag_text = str(tag).strip()
        if tag_text and tag_text not in tags:
            tags.append(tag_text)
    return tags


def collect_problem_tag_items(visual_data: Dict[str, Any]) -> List[Dict[str, str]]:
    tag_items: List[Dict[str, str]] = []
    for item in visual_data.get("problem_tag_distribution", []) or []:
        if isinstance(item, dict):
            tag = str(item.get("tag", "")).strip()
            level = str(item.get("level", "")).strip()
        else:
            tag = str(item).strip()
            level = ""
        if tag:
            tag_items.append({"tag": tag, "level": level})
    return tag_items


def collect_suggestions(visual_report: Dict[str, Any]) -> List[Dict[str, str]]:
    suggestions: List[Dict[str, str]] = []
    priority_suggestions = visual_report.get("priority_suggestions") or {}
    if isinstance(priority_suggestions, dict):
        priority_order = ["high", "medium", "low", "严重", "中等", "轻度"]
        ordered_priorities = [p for p in priority_order if p in priority_suggestions]
        ordered_priorities.extend(p for p in priority_suggestions.keys() if p not in ordered_priorities)
        for priority in ordered_priorities:
            items = priority_suggestions.get(priority, []) or []
            if isinstance(items, str):
                items = [items]
            for item in items:
                suggestion_text = item.get("suggestion", "") if isinstance(item, dict) else item
                suggestion_text = str(suggestion_text).strip()
                if suggestion_text:
                    suggestions.append({"priority": str(priority), "suggestion": suggestion_text})

    if not suggestions:
        fallback = (visual_report.get("text_report") or {}).get("suggestions", []) or []
        if isinstance(fallback, str):
            fallback = [fallback]
        for item in fallback:
            suggestion_text = item.get("suggestion", "") if isinstance(item, dict) else item
            suggestion_text = str(suggestion_text).strip()
            if suggestion_text:
                suggestions.append({"priority": "unknown", "suggestion": suggestion_text})
    return suggestions


def display_priority_label(priority: str) -> str:
    priority_map = {
        "high": "严重",
        "medium": "中等",
        "low": "轻度",
        "严重": "严重",
        "中等": "中等",
        "轻度": "轻度",
        "unknown": "未标注",
    }
    return priority_map.get(str(priority), str(priority))


def move_to_trash(path: Path, trash_root: Path, script_id: str) -> None:
    if not path.exists():
        return

    target_dir = trash_root / script_id
    target_dir.mkdir(parents=True, exist_ok=True)

    target_path = target_dir / path.name

    if target_path.exists():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target_path = target_dir / f"{path.stem}_{stamp}{path.suffix}"

    shutil.move(str(path), str(target_path))


def archive_review_artifacts(script_id: str) -> list[str]:
    paths = get_paths()
    trash_root = Path(paths["data_root"]) / "trash"

    candidates = [
        Path(paths["raw_scripts_dir"]) / f"{script_id}.json",
        Path(paths["parsed_features_dir"]) / f"{script_id}_features.json",
        Path(paths["scoring_results_dir"]) / f"{script_id}_scores.json",
        Path(paths["visual_data_dir"]) / f"{script_id}_visual_report.json",
        Path(paths["reports_dir"]) / f"{script_id}_report.md",
        Path(paths["training_samples_dir"]) / f"{script_id}_training_sample.json",
    ]

    debug_dir = Path(paths["data_root"]) / "debug_llm_responses"
    if debug_dir.exists():
        candidates.extend(debug_dir.glob(f"{script_id}_*"))

    feedback_dir = Path(paths.get("human_feedback_dir", Path(paths["data_root"]) / "human_feedback"))
    if feedback_dir.exists():
        candidates.extend(feedback_dir.glob(f"{script_id}_*_feedback.json"))

    moved: list[str] = []

    for path in candidates:
        if path.exists():
            move_to_trash(path, trash_root, script_id)
            moved.append(str(path))

    return moved

def render_markdown(markdown_text: str) -> str:
    raw_html = markdown.markdown(
        markdown_text or "",
        extensions=[
            "extra",
            "tables",
            "nl2br",
            "sane_lists",
        ],
    )

    allowed_tags = [
        "h1", "h2", "h3", "h4", "h5", "h6",
        "p", "br", "hr",
        "strong", "em", "b", "i",
        "ul", "ol", "li",
        "blockquote",
        "code", "pre",
        "table", "thead", "tbody", "tr", "th", "td",
        "a",
    ]

    allowed_attributes = {
        "a": ["href", "title", "target", "rel"],
    }

    return bleach.clean(
        raw_html,
        tags=allowed_tags,
        attributes=allowed_attributes,
        strip=True,
    )

def page_layout(title: str, body: str) -> str:
    return f"""
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>{html.escape(title)}</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
      margin: 0;
      background: #f6f7f9;
      color: #222;
    }}
    header {{
      background: #111827;
      color: white;
      padding: 18px 32px;
    }}
    main {{
      max-width: 1200px;
      margin: 24px auto;
      padding: 0 24px 48px;
    }}
    .card {{
      background: white;
      border-radius: 14px;
      padding: 20px;
      margin-bottom: 18px;
      box-shadow: 0 4px 14px rgba(0,0,0,0.06);
    }}
    .grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 18px;
    }}
    .muted {{
      color: #666;
      font-size: 14px;
    }}
    a {{
      color: #2563eb;
      text-decoration: none;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin-top: 12px;
    }}
    th, td {{
      border-bottom: 1px solid #eee;
      padding: 10px;
      text-align: left;
      vertical-align: top;
    }}
    th {{
      background: #fafafa;
    }}
    .score {{
      font-size: 38px;
      font-weight: 700;
    }}
    .bar-wrap {{
      height: 12px;
      background: #e5e7eb;
      border-radius: 999px;
      overflow: hidden;
      margin-top: 6px;
    }}
    .bar {{
      height: 12px;
      background: #2563eb;
    }}
    .tag {{
      display: inline-block;
      padding: 5px 9px;
      border-radius: 999px;
      background: #eef2ff;
      margin: 4px 4px 4px 0;
      font-size: 13px;
    }}
    .feedback-section {{
      border-top: 1px solid #e5e7eb;
      padding-top: 16px;
      margin-top: 18px;
    }}
    .machine-score-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      margin: 12px 0;
    }}
    .machine-score-row span {{
      background: #f3f4f6;
      border-radius: 8px;
      padding: 8px 10px;
    }}
    .radio-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
      gap: 8px;
      margin: 8px 0 10px;
    }}
    .radio-grid label {{
      margin: 0;
      font-weight: 500;
      border: 1px solid #e5e7eb;
      border-radius: 8px;
      padding: 9px 10px;
      background: #fff;
    }}
    .radio-grid input {{
      width: auto;
      margin-right: 6px;
    }}
    input[type="range"] {{
      padding: 0;
    }}
    .range-row {{
      display: grid;
      grid-template-columns: 1fr 56px;
      gap: 12px;
      align-items: center;
    }}
    .range-value {{
      font-weight: 700;
      text-align: center;
      background: #f3f4f6;
      border-radius: 8px;
      padding: 8px;
    }}
    .toggle-button {{
      margin: 4px 6px 4px 0;
      background: #2563eb;
      border: 1px solid #2563eb;
      border-radius: 999px;
      padding: 8px 12px;
      color: white;
      transition: background 0.15s ease, color 0.15s ease, border-color 0.15s ease;
    }}
    .toggle-button.rejected,
    .toggle-button:not(.selected) {{
      background: #f3f4f6;
      color: #6b7280;
      border-color: #d1d5db;
    }}
    .suggestion-card {{
      border: 1px solid #e5e7eb;
      border-radius: 8px;
      padding: 12px;
      margin: 10px 0;
      background: #fff;
    }}
    .suggestion-card p {{
      margin: 8px 0;
    }}
    .priority-badge {{
      display: inline-block;
      font-size: 12px;
      color: #374151;
      background: #f3f4f6;
      border-radius: 999px;
      padding: 3px 8px;
      margin-bottom: 6px;
    }}
    .ranking-list {{
      background: #f9fafb;
      border: 1px solid #e5e7eb;
      border-radius: 8px;
      padding: 10px;
      min-height: 20px;
    }}
    .chip-input-wrap {{
      border: 1px solid #d1d5db;
      border-radius: 8px;
      background: #fff;
      padding: 8px;
    }}
    .chip-list {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 8px;
    }}
    .chip {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      background: #eef2ff;
      color: #1d4ed8;
      border-radius: 999px;
      padding: 6px 10px;
      font-size: 13px;
    }}
    .chip-remove {{
      border: none;
      background: transparent;
      color: #1d4ed8;
      cursor: pointer;
      margin: 0;
      padding: 0;
      font-size: 14px;
      line-height: 1;
    }}
    .chip-input {{
      border: none;
      padding: 4px 2px;
      outline: none;
      width: 100%;
    }}
    .form-intro {{
      background: #f9fafb;
      border: 1px solid #e5e7eb;
      border-radius: 8px;
      padding: 12px 14px;
      line-height: 1.7;
      margin-bottom: 16px;
    }}
    .field-note {{
      color: #6b7280;
      font-size: 13px;
      margin-top: 6px;
    }}
    .form-error {{
      display: none;
      margin-top: 14px;
      color: #b91c1c;
      background: #fef2f2;
      border: 1px solid #fecaca;
      border-radius: 8px;
      padding: 10px 12px;
    }}
    textarea, input, select {{
      width: 100%;
      box-sizing: border-box;
      padding: 10px;
      border: 1px solid #d1d5db;
      border-radius: 8px;
      font-size: 14px;
      background: white;
    }}
    label {{
      font-weight: 600;
      display: block;
      margin: 12px 0 6px;
    }}
    button {{
      margin-top: 16px;
      background: #111827;
      color: white;
      border: none;
      border-radius: 8px;
      padding: 11px 18px;
      cursor: pointer;
    }}
    pre {{
      white-space: pre-wrap;
      word-break: break-word;
      background: #f3f4f6;
      padding: 14px;
      border-radius: 10px;
      max-height: 520px;
      overflow: auto;
    }}
  </style>
</head>
<body>
  <header>
    <h2>纯文本剧本审核分析系统</h2>
    <div class="muted">本地原型：查看审核结果并收集轻量反馈</div>
  </header>
  <main>
    {body}
  </main>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    files = get_visual_report_files()

    rows = []
    for path in files:
        script_id = extract_script_id(path)
        try:
            report = read_json(path)
            score_card = report.get("visual_data", {}).get("score_card", {})
            title = score_card.get("script_title") or script_id
            score = score_card.get("total_score", "")
            level = score_card.get("level", "")
            confidence = score_card.get("confidence", "")
        except Exception:
            title = script_id
            score = ""
            level = ""
            confidence = ""

        rows.append(
            f"""
            <tr>
              <td><a href="/review/{html.escape(script_id)}">{html.escape(title)}</a></td>
              <td>{html.escape(str(score))}</td>
              <td>{html.escape(str(level))}</td>
              <td>{html.escape(str(confidence))}</td>
              <td class="muted">{html.escape(script_id)}</td>
              <td>
                <a href="/review/{html.escape(script_id)}">查看审核 / 填写反馈</a>
                <form method="post" action="/delete/{html.escape(script_id)}" style="display:inline;"
                      onsubmit="return confirm('确定要归档删除这个审核结果吗？相关报告、可视化数据和反馈都会移到 trash。');">
                  <button type="submit" style="background:#b91c1c;margin-left:8px;">删除</button>
                </form>
              </td>
            </tr>
            """
        )

    body = f"""
    <div class="card">
      <h3>审核结果列表</h3>
      <p class="muted">这里读取的是 E 盘 visual_data 目录里已经生成的审核结果。</p>
      <table>
        <thead>
          <tr>
            <th>剧本</th>
            <th>总分</th>
            <th>等级</th>
            <th>置信度</th>
            <th>script_id</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          {''.join(rows) if rows else '<tr><td colspan="6">暂无审核结果。</td></tr>'}
        </tbody>
      </table>
    </div>
    """
    return HTMLResponse(page_layout("审核结果列表", body))


@app.get("/review/{script_id}", response_class=HTMLResponse)
def review_detail(script_id: str) -> HTMLResponse:
    visual_report = load_visual_report(script_id)
    raw_script = load_raw_script(script_id)
    markdown_report = load_markdown_report(script_id)
    rendered_markdown_report = render_markdown(markdown_report)

    visual_data = visual_report.get("visual_data", {})
    score_card = visual_data.get("score_card", {})
    text_report = visual_report.get("text_report", {})

    script_title = score_card.get("script_title") or raw_script.get("script_title") or script_id
    total_score = score_card.get("total_score", "")
    level = score_card.get("level", "")
    confidence = score_card.get("confidence", "")
    final_recommendation = score_card.get("final_recommendation", "")

    radar_rows = []
    for item in visual_data.get("radar_chart", []):
        dim = item.get("dimension", "")
        score = item.get("score", 0)
        radar_rows.append(
            f"""
            <tr>
              <td>{html.escape(str(dim))}</td>
              <td>{html.escape(str(score))}</td>
              <td>
                <div class="bar-wrap"><div class="bar" style="width:{max(0, min(100, int(score or 0)))}%"></div></div>
              </td>
            </tr>
            """
        )

    problem_tag_items = collect_problem_tag_items(visual_data)
    problem_tags_html = "".join(
        f'<span class="tag">{html.escape(item["tag"])}'
        f'{" / " + html.escape(item["level"]) if item["level"] else ""}</span>'
        for item in problem_tag_items
    )

    suggestion_groups: Dict[str, List[str]] = {}
    for item in collect_suggestions(visual_report):
        suggestion_groups.setdefault(item["priority"], []).append(item["suggestion"])
    priority_labels = {
        "high": "high",
        "medium": "medium",
        "low": "low",
        "严重": "严重",
        "中等": "中等",
        "轻度": "轻度",
        "unknown": "未标注",
    }
    suggestion_html = ""
    for priority, items in suggestion_groups.items():
        suggestion_html += f"<h4>{html.escape(priority_labels.get(priority, priority))}</h4><ul>"
        for item in items:
            suggestion_html += f"<li>{html.escape(str(item))}</li>"
        suggestion_html += "</ul>"
    if not suggestion_html:
        suggestion_html = '<p class="muted">暂无修改建议。</p>'

    raw_script_text = raw_script.get("script_text", "")
    director_score_default = normalize_score(total_score, default=60)
    feedback_problem_tags = collect_problem_tags(visual_data)
    problem_tag_buttons_html = "".join(
        f'<button type="button" class="toggle-button selected problem-tag-button" '
        f'data-tag="{html.escape(tag, quote=True)}">{html.escape(tag)}</button>'
        for tag in feedback_problem_tags
    )
    suggestion_review_items = collect_suggestions(visual_report)
    suggestion_cards_html = ""
    for index, item in enumerate(suggestion_review_items):
        priority_label = display_priority_label(item["priority"])
        suggestion_cards_html += f"""
        <div class="suggestion-card" data-suggestion-index="{index}">
          <span class="priority-badge">{html.escape(priority_label)}</span>
          <p>{html.escape(item['suggestion'])}</p>
          <div class="range-row">
            <input type="range" min="0" max="10" value="5" class="suggestion-score"
                   data-priority="{html.escape(item['priority'], quote=True)}"
                   data-suggestion="{html.escape(item['suggestion'], quote=True)}">
            <span class="range-value">5</span>
          </div>
          <p class="muted">0 = 没有帮助　5 = 有一定参考价值　10 = 非常有用，建议优先执行</p>
        </div>
        """
    potential_options = [
        "完播潜力",
        "互动潜力",
        "题材潜力",
        "人物潜力",
        "情绪爽感潜力",
        "反转传播潜力",
        "CP讨论潜力",
        "制作落地潜力",
        "修改提升潜力",
        "暂时看不到明显潜力",
    ]
    potential_buttons_html = "".join(
        f'<button type="button" class="toggle-button potential-button" '
        f'data-potential="{html.escape(option, quote=True)}">{html.escape(option)}</button>'
        for option in potential_options
    )

    body = f"""
    <p><a href="/">← 返回列表</a></p>

    <div class="card">
      <h3>{html.escape(str(script_title))}</h3>
      <div class="score">{html.escape(str(total_score))}</div>
      <p>等级：{html.escape(str(level))}　置信度：{html.escape(str(confidence))}</p>
      <p>{html.escape(str(final_recommendation))}</p>
    </div>

    <div class="grid">
      <div class="card">
        <h3>分项评分</h3>
        <table>
          <thead>
            <tr><th>维度</th><th>分数</th><th>可视化</th></tr>
          </thead>
          <tbody>
            {''.join(radar_rows)}
          </tbody>
        </table>
      </div>

      <div class="card">
        <h3>问题标签</h3>
        {problem_tags_html or '<p class="muted">暂无问题标签。</p>'}

        <h3>修改建议</h3>
        {suggestion_html}
      </div>
    </div>

    <div class="grid">
      <div class="card">
        <h3>系统总结</h3>
        <p>{html.escape(str(text_report.get("summary", "")))}</p>

        <h4>主要优势</h4>
        <ul>
          {''.join(f"<li>{html.escape(str(x))}</li>" for x in text_report.get("strengths", []))}
        </ul>

        <h4>主要问题</h4>
        <ul>
          {''.join(f"<li>{html.escape(str(x))}</li>" for x in text_report.get("weaknesses", []))}
        </ul>

        <h4>风险提示</h4>
        <ul>
          {''.join(f"<li>{html.escape(str(x))}</li>" for x in text_report.get("risks", []))}
        </ul>
      </div>

      <div class="card">
        <h3>原始剧本文本</h3>
        <pre>{html.escape(raw_script_text[:8000])}</pre>
      </div>
    </div>

    <div class="card">
      <h3>审核报告</h3>
      <div class="markdown-body">
        {rendered_markdown_report}
      </div>
    </div>

    <div class="card">
      <h3>人工反馈表</h3>
      <div class="form-intro">
        请根据页面中的机器审核结果填写反馈，不需要填写姓名。重点判断：总分是否合理、问题标签是否准确、修改建议是否有用、剧本是否建议进入下一轮。所有反馈只用于校准机器审核系统。
      </div>
      <form id="feedback-form" method="post" action="/feedback/{html.escape(script_id)}">
        <div class="feedback-section">
          <h4>总分判断</h4>
          <div class="machine-score-row">
            <span>机器总分：{html.escape(str(total_score))}</span>
            <span>机器等级：{html.escape(str(level))}</span>
          </div>

          <label>系统总分是否合理？</label>
          <div class="radio-grid">
            <label><input type="radio" name="score_judgement" value="completely_reasonable" required>完全合理</label>
            <label><input type="radio" name="score_judgement" value="basically_reasonable">基本合理</label>
            <label><input type="radio" name="score_judgement" value="too_high">偏高</label>
            <label><input type="radio" name="score_judgement" value="too_low">偏低</label>
            <label><input type="radio" name="score_judgement" value="unreasonable">完全不合理</label>
          </div>

          <label>导演建议分数</label>
          <div class="range-row">
            <input id="director-score" name="director_score" type="range" min="0" max="100" value="{director_score_default}" required>
            <span id="director-score-value" class="range-value">{director_score_default}</span>
          </div>
          <p class="field-note">默认值会优先读取机器总分；如果机器总分缺失，则默认为 60。</p>

          <label>总分判断理由</label>
          <textarea name="score_reason" rows="4" required placeholder="请说明你对总分的判断理由，例如：系统高估了反转设计、低估了人物关系张力、整体判断基本符合实际等。"></textarea>
        </div>

        <div class="feedback-section">
          <h4>问题标签判断</h4>
          <p class="muted">默认高亮代表保留该标签。点击标签后变灰，表示你认为该标签不准确，不应保留。</p>
          <div id="problem-tag-buttons">
            {problem_tag_buttons_html or '<p class="muted">当前报告没有可判断的问题标签。</p>'}
          </div>
          <input type="hidden" name="accepted_tags_json" id="accepted-tags-json">
          <input type="hidden" name="rejected_tags_json" id="rejected-tags-json">

          <label>你认为还应该补充哪些问题标签？</label>
          <div class="chip-input-wrap">
            <div id="added-tag-chip-list" class="chip-list"></div>
            <input type="text" id="added-tag-input" class="chip-input" placeholder="请以“/”作为标签分隔，例如：/CP张力不足/人物目标不清">
          </div>
          <input type="hidden" name="added_problem_tags" id="added-problem-tags">
        </div>

        <div class="feedback-section">
          <h4>修改建议有用度</h4>
          {suggestion_cards_html or '<p class="muted">当前报告没有可评分的修改建议。</p>'}
          <input type="hidden" name="suggestion_scores_json" id="suggestion-scores-json">
        </div>

        <div class="feedback-section">
          <h4>剧本整体潜力</h4>
          <div id="potential-buttons">
            {potential_buttons_html}
          </div>
          <p class="ranking-list">已选择潜力排序：<span id="potential-ranking-text">暂无</span></p>
          <input type="hidden" name="potential_ranking_json" id="potential-ranking-json">
        </div>

        <div class="feedback-section">
          <h4>是否建议进入下一轮</h4>
          <div class="radio-grid">
            <label><input type="radio" name="next_round_decision" value="no_revision_next_round" required>无需修改可以进入</label>
            <label><input type="radio" name="next_round_decision" value="revise_not_recommended">需要修改不建议进入</label>
            <label><input type="radio" name="next_round_decision" value="major_revision_stop">需要大改不要进入</label>
          </div>
        </div>

        <div class="feedback-section">
          <h4>人工说明</h4>
          <label>机器判断中准确或不准确的地方</label>
          <textarea name="accuracy_comment" rows="4" required placeholder="请说明机器判断中准确或不准确的地方。即使你认为基本合理，也可以写：分数、标签和建议基本符合实际。"></textarea>

          <label>补充意见</label>
          <textarea name="additional_comment" rows="5" required placeholder="请补充机器没有覆盖到的判断，例如题材风险、受众匹配、制作难度、人物问题、节奏问题等。"></textarea>
        </div>

        <div id="form-error" class="form-error"></div>
        <button type="submit">提交反馈</button>
      </form>
      <script>
        (function() {{
          var directorScore = document.getElementById("director-score");
          var directorScoreValue = document.getElementById("director-score-value");
          var acceptedTagsInput = document.getElementById("accepted-tags-json");
          var rejectedTagsInput = document.getElementById("rejected-tags-json");
          var suggestionScoresInput = document.getElementById("suggestion-scores-json");
          var potentialRankingInput = document.getElementById("potential-ranking-json");
          var potentialRankingText = document.getElementById("potential-ranking-text");
          var addedTagInput = document.getElementById("added-tag-input");
          var addedTagChipList = document.getElementById("added-tag-chip-list");
          var addedProblemTagsInput = document.getElementById("added-problem-tags");
          var formError = document.getElementById("form-error");
          var potentialRanking = [];
          var addedTags = [];

          function syncDirectorScore() {{
            directorScoreValue.textContent = directorScore.value;
          }}

          function syncTags() {{
            var accepted = [];
            var rejected = [];
            document.querySelectorAll(".problem-tag-button").forEach(function(button) {{
              if (button.classList.contains("rejected")) {{
                rejected.push(button.dataset.tag);
              }} else {{
                accepted.push(button.dataset.tag);
              }}
            }});
            acceptedTagsInput.value = JSON.stringify(accepted);
            rejectedTagsInput.value = JSON.stringify(rejected);
          }}

          function syncSuggestions() {{
            var scores = [];
            document.querySelectorAll(".suggestion-score").forEach(function(slider) {{
              var valueNode = slider.parentElement.querySelector(".range-value");
              valueNode.textContent = slider.value;
              scores.push({{
                priority: slider.dataset.priority,
                suggestion: slider.dataset.suggestion,
                score: Number(slider.value)
              }});
            }});
            suggestionScoresInput.value = JSON.stringify(scores);
          }}

          function syncPotentialRanking() {{
            potentialRankingInput.value = JSON.stringify(potentialRanking);
            if (potentialRanking.length === 0) {{
              potentialRankingText.textContent = "暂无";
              return;
            }}
            potentialRankingText.textContent = potentialRanking
              .map(function(item, index) {{ return (index + 1) + ". " + item; }})
              .join("  ");
          }}

          function syncAddedTags() {{
            addedProblemTagsInput.value = addedTags.length > 0 ? "/" + addedTags.join("/") : "";
            addedTagChipList.innerHTML = "";
            addedTags.forEach(function(tag, index) {{
              var chip = document.createElement("span");
              chip.className = "chip";
              chip.textContent = tag;

              var removeButton = document.createElement("button");
              removeButton.type = "button";
              removeButton.className = "chip-remove";
              removeButton.textContent = "×";
              removeButton.setAttribute("aria-label", "删除标签");
              removeButton.addEventListener("click", function() {{
                addedTags.splice(index, 1);
                syncAddedTags();
              }});

              chip.appendChild(removeButton);
              addedTagChipList.appendChild(chip);
            }});
          }}

          function commitAddedTag(rawValue) {{
            var tag = (rawValue || "").trim();
            if (!tag) {{
              return;
            }}
            if (!addedTags.includes(tag)) {{
              addedTags.push(tag);
            }}
            syncAddedTags();
          }}

          function validateForm() {{
            var missing = [];
            if (!document.querySelector('input[name="score_judgement"]:checked')) {{
              missing.push("请选择系统总分是否合理");
            }}
            if (!directorScore.value) {{
              missing.push("请填写导演建议分数");
            }}
            if (!document.querySelector('textarea[name="score_reason"]').value.trim()) {{
              missing.push("请填写总分判断理由");
            }}
            if (!document.querySelector('input[name="next_round_decision"]:checked')) {{
              missing.push("请选择是否建议进入下一轮");
            }}
            if (!document.querySelector('textarea[name="accuracy_comment"]').value.trim()) {{
              missing.push("请填写机器判断中准确或不准确的地方");
            }}
            if (!document.querySelector('textarea[name="additional_comment"]').value.trim()) {{
              missing.push("请填写补充意见");
            }}
            if (missing.length > 0) {{
              formError.style.display = "block";
              formError.textContent = missing.join("；");
              return false;
            }}
            formError.style.display = "none";
            formError.textContent = "";
            return true;
          }}

          directorScore.addEventListener("input", syncDirectorScore);
          addedTagInput.addEventListener("input", function() {{
            var parts = addedTagInput.value.split("/");
            if (parts.length > 1) {{
              for (var i = 0; i < parts.length - 1; i += 1) {{
                commitAddedTag(parts[i]);
              }}
              addedTagInput.value = parts[parts.length - 1];
            }}
          }});
          addedTagInput.addEventListener("keydown", function(event) {{
            if (event.key === "Enter") {{
              event.preventDefault();
              commitAddedTag(addedTagInput.value);
              addedTagInput.value = "";
            }} else if (event.key === "Backspace" && !addedTagInput.value && addedTags.length > 0) {{
              addedTags.pop();
              syncAddedTags();
            }}
          }});
          addedTagInput.addEventListener("blur", function() {{
            commitAddedTag(addedTagInput.value);
            addedTagInput.value = "";
          }});
          document.querySelectorAll(".problem-tag-button").forEach(function(button) {{
            button.addEventListener("click", function() {{
              button.classList.toggle("selected");
              button.classList.toggle("rejected");
              syncTags();
            }});
          }});
          document.querySelectorAll(".suggestion-score").forEach(function(slider) {{
            slider.addEventListener("input", syncSuggestions);
          }});
          document.querySelectorAll(".potential-button").forEach(function(button) {{
            button.addEventListener("click", function() {{
              var value = button.dataset.potential;
              var index = potentialRanking.indexOf(value);
              if (index >= 0) {{
                potentialRanking.splice(index, 1);
                button.classList.remove("selected");
              }} else {{
                potentialRanking.push(value);
                button.classList.add("selected");
              }}
              syncPotentialRanking();
            }});
          }});
          document.getElementById("feedback-form").addEventListener("submit", function(event) {{
            syncTags();
            syncSuggestions();
            syncPotentialRanking();
            if (addedTagInput.value.trim()) {{
              commitAddedTag(addedTagInput.value);
              addedTagInput.value = "";
            }}
            if (!validateForm()) {{
              event.preventDefault();
            }}
          }});

          syncDirectorScore();
          syncTags();
          syncSuggestions();
          syncPotentialRanking();
          syncAddedTags();
        }})();
      </script>
    </div>
    """
    return HTMLResponse(page_layout(str(script_title), body))


@app.post("/feedback/{script_id}")
def submit_feedback(
    script_id: str,
    score_judgement: str = Form(""),
    director_score: int = Form(60),
    score_reason: str = Form(""),
    accepted_tags_json: str = Form("[]"),
    rejected_tags_json: str = Form("[]"),
    added_problem_tags: str = Form(""),
    suggestion_scores_json: str = Form("[]"),
    potential_ranking_json: str = Form("[]"),
    next_round_decision: str = Form(""),
    accuracy_comment: str = Form(""),
    additional_comment: str = Form(""),
) -> RedirectResponse:
    paths = get_paths()
    visual_report = load_visual_report(script_id)
    score_card = visual_report.get("visual_data", {}).get("score_card", {})
    suggestion_scores = []
    for item in parse_json_list(suggestion_scores_json):
        if not isinstance(item, dict):
            continue
        suggestion_text = str(item.get("suggestion", "")).strip()
        if not suggestion_text:
            continue
        suggestion_scores.append(
            {
                "priority": str(item.get("priority", "")),
                "suggestion": suggestion_text,
                "score": normalize_suggestion_score(item.get("score", 0)),
            }
        )

    feedback = {
        "script_id": script_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "score_review": {
            "machine_score": score_card.get("total_score"),
            "machine_level": score_card.get("level"),
            "score_judgement": score_judgement,
            "director_score": normalize_score(director_score),
            "score_reason": score_reason,
        },
        "problem_tag_review": {
            "accepted_tags": parse_json_string_list(accepted_tags_json),
            "rejected_tags": parse_json_string_list(rejected_tags_json),
            "added_tags": added_problem_tags.strip(),
        },
        "suggestion_review": {
            "suggestion_scores": suggestion_scores,
        },
        "potential_review": {
            "potential_ranking": parse_json_string_list(potential_ranking_json),
        },
        "next_round_decision": next_round_decision.strip(),
        "accuracy_comment": accuracy_comment.strip(),
        "additional_comment": additional_comment.strip(),
    }

    feedback_dir = Path(paths["human_feedback_dir"])
    feedback_path = feedback_dir / f"{script_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_feedback.json"
    save_json(feedback_path, feedback)

    return RedirectResponse(url=f"/review/{script_id}", status_code=303)

@app.post("/delete/{script_id}")
def delete_review(script_id: str) -> RedirectResponse:
    archive_review_artifacts(script_id)
    return RedirectResponse(url="/", status_code=303)
