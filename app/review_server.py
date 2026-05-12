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

    problem_tags_html = ""
    for item in visual_data.get("problem_tag_distribution", []):
        tag = item.get("tag", "")
        level_value = item.get("level", "")
        problem_tags_html += f'<span class="tag">{html.escape(str(tag))} / {html.escape(str(level_value))}</span>'

    suggestions = visual_report.get("priority_suggestions", {})
    suggestion_html = ""
    for priority in ["high", "medium", "low"]:
        items = suggestions.get(priority, [])
        suggestion_html += f"<h4>{priority}</h4><ul>"
        for item in items:
            suggestion_html += f"<li>{html.escape(str(item))}</li>"
        suggestion_html += "</ul>"

    raw_script_text = raw_script.get("script_text", "")

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
      <h3>轻量反馈表单</h3>
      <form method="post" action="/feedback/{html.escape(script_id)}">
        <label>评价人</label>
        <input name="reviewer" placeholder="可填姓名或角色，例如：内容编辑A">

        <label>你觉得系统总分是否合理？</label>
        <select name="score_judgement">
          <option value="accurate">基本合理</option>
          <option value="too_high">偏高</option>
          <option value="too_low">偏低</option>
          <option value="unknown">不确定</option>
        </select>

        <label>你觉得问题标签是否准确？</label>
        <select name="tag_judgement">
          <option value="mostly_correct">大部分准确</option>
          <option value="partly_correct">部分准确</option>
          <option value="mostly_wrong">大部分不准确</option>
          <option value="unknown">不确定</option>
        </select>

        <label>你觉得修改建议是否有用？</label>
        <select name="suggestion_judgement">
          <option value="useful">有用</option>
          <option value="partly_useful">部分有用</option>
          <option value="not_useful">没什么用</option>
          <option value="unknown">不确定</option>
        </select>

        <label>你认为这个剧本整体潜力是？</label>
        <select name="potential_level">
          <option value="high">高</option>
          <option value="medium_high">中高</option>
          <option value="medium">中</option>
          <option value="medium_low">中低</option>
          <option value="low">低</option>
          <option value="unknown">不确定</option>
        </select>

        <label>是否建议进入下一轮？</label>
        <select name="final_decision">
          <option value="promote">建议推进</option>
          <option value="revise_then_promote">建议修改后推进</option>
          <option value="major_revision">建议大改</option>
          <option value="hold">暂缓</option>
          <option value="unknown">不确定</option>
        </select>

        <label>哪些地方不准确？可选填</label>
        <textarea name="inaccuracy_note" rows="4"></textarea>

        <label>补充意见，可选填</label>
        <textarea name="final_comment" rows="5"></textarea>

        <button type="submit">提交反馈</button>
      </form>
    </div>
    """
    return HTMLResponse(page_layout(str(script_title), body))


@app.post("/feedback/{script_id}")
def submit_feedback(
    script_id: str,
    reviewer: str = Form(""),
    score_judgement: str = Form("unknown"),
    tag_judgement: str = Form("unknown"),
    suggestion_judgement: str = Form("unknown"),
    potential_level: str = Form("unknown"),
    final_decision: str = Form("unknown"),
    inaccuracy_note: str = Form(""),
    final_comment: str = Form(""),
) -> RedirectResponse:
    paths = get_paths()
    visual_report = load_visual_report(script_id)
    score_card = visual_report.get("visual_data", {}).get("score_card", {})

    feedback = {
        "script_id": script_id,
        "script_title": score_card.get("script_title", ""),
        "review_time": datetime.now().isoformat(timespec="seconds"),
        "reviewer": reviewer,
        "model_total_score": score_card.get("total_score"),
        "model_level": score_card.get("level"),
        "light_manual_feedback": {
            "score_judgement": score_judgement,
            "tag_judgement": tag_judgement,
            "suggestion_judgement": suggestion_judgement,
            "potential_level": potential_level,
            "final_decision": final_decision,
            "inaccuracy_note": inaccuracy_note,
            "final_comment": final_comment,
        },
    }

    feedback_dir = Path(paths["human_feedback_dir"])
    feedback_path = feedback_dir / f"{script_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_feedback.json"
    save_json(feedback_path, feedback)

    return RedirectResponse(url=f"/review/{script_id}", status_code=303)

@app.post("/delete/{script_id}")
def delete_review(script_id: str) -> RedirectResponse:
    archive_review_artifacts(script_id)
    return RedirectResponse(url="/", status_code=303)
