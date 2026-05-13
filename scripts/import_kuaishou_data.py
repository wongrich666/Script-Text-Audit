from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import pandas as pd


PLATFORM = "kuaishou"


def is_old_excel_binary(path: Path) -> bool:
    try:
        with path.open("rb") as f:
            head = f.read(8)
        return head == bytes.fromhex("D0 CF 11 E0 A1 B1 1A E1")
    except OSError:
        return False


def read_any_table(path: Path) -> list[pd.DataFrame]:
    """
    快手导出的文件可能扩展名是 .csv，但实际内容是旧版 Excel。
    所以这里按文件头判断，而不是按扩展名判断。
    """
    frames: list[pd.DataFrame] = []

    if is_old_excel_binary(path):
        xls = pd.ExcelFile(path, engine="xlrd")
        for sheet in xls.sheet_names:
            df = pd.read_excel(path, sheet_name=sheet, engine="xlrd")
            df = clean_dataframe(df)
            if not df.empty:
                df["source_file"] = path.name
                df["source_sheet"] = sheet
                frames.append(df)
        return frames

    encodings = ["utf-8-sig", "utf-8", "gb18030", "gbk"]
    last_error: Exception | None = None

    for enc in encodings:
        try:
            df = pd.read_csv(path, encoding=enc)
            df = clean_dataframe(df)
            if not df.empty:
                df["source_file"] = path.name
                df["source_sheet"] = ""
                frames.append(df)
            return frames
        except Exception as exc:
            last_error = exc

    raise RuntimeError(f"无法读取文件：{path}，最后错误：{last_error}")


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().replace("\ufeff", "") for c in df.columns]
    df = df.dropna(how="all")
    return df


def normalize_title(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() == "nan":
        return ""

    text = text.replace("：", ":")
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[《》【】\[\]（）()「」『』“”\"'、，,。.!！?？:：;；\-—_/\\|]", "", text)

    noise_words = [
        "短剧",
        "全集",
        "全剧",
        "完整版",
        "竖屏",
        "漫剧",
        "iaa",
        "IAA",
        "快手",
        "投放",
        "广告",
    ]
    for word in noise_words:
        text = text.replace(word, "")

    return text.lower()


def make_script_id(path: Path) -> str:
    raw = str(path.as_posix()).encode("utf-8")
    return "script_" + hashlib.md5(raw).hexdigest()[:12]


def make_content_hash(path: Path) -> str:
    try:
        raw = path.read_bytes()
        return hashlib.md5(raw).hexdigest()
    except Exception:
        return ""


def build_script_registry(episode_scripts_dir: Path) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    if not episode_scripts_dir.exists():
        return pd.DataFrame(
            columns=[
                "script_id",
                "canonical_title",
                "title_norm",
                "aliases",
                "script_path",
                "episode_count",
                "content_hash",
            ]
        )

    patterns = ["*.txt", "*.md", "*.docx"]
    files: list[Path] = []
    for pattern in patterns:
        files.extend(episode_scripts_dir.rglob(pattern))

    for path in sorted(files):
        title = path.stem.strip()
        title_norm = normalize_title(title)
        rows.append(
            {
                "script_id": make_script_id(path),
                "canonical_title": title,
                "title_norm": title_norm,
                "aliases": "",
                "script_path": str(path),
                "episode_count": "",
                "content_hash": make_content_hash(path),
            }
        )

    return pd.DataFrame(
        rows,
        columns=[
            "script_id",
            "canonical_title",
            "title_norm",
            "aliases",
            "script_path",
            "episode_count",
            "content_hash",
        ],
    )


def classify_table(df: pd.DataFrame) -> str:
    cols = set(df.columns)

    if {"短剧ID", "短剧名称"}.issubset(cols):
        return "drama_catalog"

    if "短剧名称" in cols and ("付费金额" in cols or "全域ROI" in cols or "消耗" in cols):
        return "drama_daily"

    has_date = "日期" in cols
    has_drama_entity = "短剧名称" in cols
    has_ad_entity = "广告账户名称" in cols or "广告账户" in cols
    overall_markers = {
        "视频-播放量",
        "视频-点赞量",
        "视频-评论量",
        "视频-收藏量",
        "付费人数",
        "付费订单数",
        "付费金额（元）",
        "付费金额(元)",
        "消耗（元）",
        "消耗(元)",
        "消耗（ 元）",
        "全域ROI",
        "商业化ROI",
        "IAA广告含返货LTV(元)",
        "IAA广告含返货变现ROI",
        "IAA广告不含返货LTV(元)",
        "IAA广告不含返货变现ROI",
    }

    if has_date and not has_drama_entity and not has_ad_entity and (cols & overall_markers):
        return "overall_daily"

    if "广告账户名称" in cols or "广告账户" in cols or "花费（元）" in cols or "花费(元)" in cols:
        return "ad_account_daily"

    if "日期" in cols and ("播放量" in cols or "视频播放数" in cols or "消耗" in cols):
        return "core_daily"

    return "unknown"

def safe_get(row: pd.Series, *names: str) -> Any:
    for name in names:
        if name in row.index:
            value = row.get(name)
            if pd.notna(value):
                return value
    return ""


def to_number(value: Any) -> Any:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return ""
    text = text.replace(",", "").replace("%", "")
    try:
        return float(text)
    except Exception:
        return value


def extract_title_from_account_name(account_name: Any, known_titles: list[str]) -> tuple[str, str]:
    """
    从广告账户名称里尽量抽剧名。
    不强行猜，遇到泛称就标 generic。
    """
    text = str(account_name or "").strip()
    if not text or text.lower() == "nan":
        return "", "empty"

    norm_account = normalize_title(text)
    if not norm_account:
        return "", "empty"

    generic_tokens = ["漫剧", "短剧", "iaa", "IAA", "序列号"]
    has_generic = any(token.lower() in text.lower() for token in generic_tokens)

    best_title = ""
    best_len = 0

    for title in known_titles:
        title_norm = normalize_title(title)
        if title_norm and title_norm in norm_account and len(title_norm) > best_len:
            best_title = title
            best_len = len(title_norm)

    if best_title:
        return best_title, "contains_known_title"

    # 粗略拆分：0509-人名-剧名-iaa-62
    parts = [p.strip() for p in re.split(r"[-_]", text) if p.strip()]
    candidates = []
    for part in parts:
        part_norm = normalize_title(part)
        if len(part_norm) >= 4 and not re.fullmatch(r"\d+", part_norm):
            if part_norm not in {"iaa", "短剧", "漫剧"}:
                candidates.append(part)

    if candidates:
        # 只取最长候选，不自动确认为 matched，后续仍需模糊匹配。
        return max(candidates, key=lambda x: len(normalize_title(x))), "heuristic_segment"

    if has_generic:
        return "", "generic_account_name"

    return "", "unknown"


@dataclass
class MatchResult:
    script_id: str
    script_title: str
    match_status: str
    match_method: str
    match_confidence: float
    review_required: bool
    reason: str


def match_title_to_script(raw_title: Any, script_registry: pd.DataFrame) -> MatchResult:
    title = str(raw_title or "").strip()
    title_norm = normalize_title(title)

    if not title_norm:
        return MatchResult("", "", "unmatched", "none", 0.0, True, "empty_title")

    if script_registry.empty:
        return MatchResult("", "", "script_file_missing", "none", 0.0, True, "no_script_registry")

    # 1. 归一化后精确匹配
    exact = script_registry[script_registry["title_norm"] == title_norm]
    if len(exact) == 1:
        row = exact.iloc[0]
        return MatchResult(
            row["script_id"],
            row["canonical_title"],
            "matched",
            "normalized_title_exact",
            1.0,
            False,
            "",
        )

    if len(exact) > 1:
        row = exact.iloc[0]
        return MatchResult(
            row["script_id"],
            row["canonical_title"],
            "ambiguous_match",
            "normalized_title_exact",
            1.0,
            True,
            "multiple_scripts_same_title_norm",
        )

    # 2. 包含关系
    contains_candidates = []
    for _, row in script_registry.iterrows():
        s_norm = str(row.get("title_norm") or "")
        if not s_norm:
            continue
        if s_norm in title_norm or title_norm in s_norm:
            score = min(len(title_norm), len(s_norm)) / max(len(title_norm), len(s_norm))
            contains_candidates.append((score, row))

    if contains_candidates:
        contains_candidates.sort(key=lambda x: x[0], reverse=True)
        score, row = contains_candidates[0]
        status = "matched" if score >= 0.92 else "needs_review"
        return MatchResult(
            row["script_id"],
            row["canonical_title"],
            status,
            "title_contains",
            round(float(score), 4),
            status != "matched",
            "" if status == "matched" else "partial_title_match",
        )

    # 3. 模糊匹配
    best_score = 0.0
    best_row = None
    for _, row in script_registry.iterrows():
        s_norm = str(row.get("title_norm") or "")
        if not s_norm:
            continue
        score = SequenceMatcher(None, title_norm, s_norm).ratio()
        if score > best_score:
            best_score = score
            best_row = row

    if best_row is not None:
        if best_score >= 0.95:
            return MatchResult(
                best_row["script_id"],
                best_row["canonical_title"],
                "matched",
                "fuzzy",
                round(float(best_score), 4),
                False,
                "",
            )
        if best_score >= 0.80:
            return MatchResult(
                best_row["script_id"],
                best_row["canonical_title"],
                "needs_review",
                "fuzzy",
                round(float(best_score), 4),
                True,
                "low_confidence_fuzzy_match",
            )

    return MatchResult("", "", "script_file_missing", "none", round(float(best_score), 4), True, "no_good_script_match")




def normalize_overall_daily(df: pd.DataFrame) -> pd.DataFrame:
    rows = []

    for _, row in df.iterrows():
        rows.append(
            {
                "platform": PLATFORM,
                "date": safe_get(row, "日期"),
                "play_count": to_number(safe_get(row, "视频-播放量", "视频播放量", "播放量")),
                "like_count": to_number(safe_get(row, "视频-点赞量", "点赞量", "点赞数")),
                "comment_count": to_number(safe_get(row, "视频-评论量", "评论量", "评论数")),
                "favorite_count": to_number(safe_get(row, "视频-收藏量", "收藏量", "收藏数")),
                "paid_users": to_number(safe_get(row, "付费人数")),
                "paid_orders": to_number(safe_get(row, "付费订单数", "付费单量")),
                "paid_amount": to_number(safe_get(row, "付费金额（元）", "付费金额(元)", "付费金额")),
                "ad_spend": to_number(safe_get(row, "消耗（元）", "消耗(元)", "消耗（ 元）", "消耗", "花费（元）", "花费(元)")),
                "global_roi": to_number(safe_get(row, "全域ROI", "全域 ROI")),
                "commercial_roi": to_number(safe_get(row, "商业化ROI", "商业化 ROI")),
                "iaa_ltv_with_rebate": to_number(safe_get(row, "IAA广告含返货LTV(元)", "IAA广告含返货LTV（元）")),
                "iaa_roi_with_rebate": to_number(safe_get(row, "IAA广告含返货变现ROI")),
                "iaa_ltv_without_rebate": to_number(safe_get(row, "IAA广告不含返货LTV(元)", "IAA广告不含返货LTV（元）")),
                "iaa_roi_without_rebate": to_number(safe_get(row, "IAA广告不含返货变现ROI")),
                "source_file": safe_get(row, "source_file"),
                "source_sheet": safe_get(row, "source_sheet"),
            }
        )

    return pd.DataFrame(
        rows,
        columns=[
            "platform",
            "date",
            "play_count",
            "like_count",
            "comment_count",
            "favorite_count",
            "paid_users",
            "paid_orders",
            "paid_amount",
            "ad_spend",
            "global_roi",
            "commercial_roi",
            "iaa_ltv_with_rebate",
            "iaa_roi_with_rebate",
            "iaa_ltv_without_rebate",
            "iaa_roi_without_rebate",
            "source_file",
            "source_sheet",
        ],
    )

def normalize_catalog(df: pd.DataFrame, script_registry: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in df.iterrows():
        title = safe_get(row, "短剧名称")
        match = match_title_to_script(title, script_registry)
        rows.append(
            {
                "platform": PLATFORM,
                "platform_drama_id": safe_get(row, "短剧ID"),
                "raw_title": title,
                "canonical_title": title,
                "title_norm": normalize_title(title),
                "sale_status": safe_get(row, "售卖状态"),
                "audit_status": safe_get(row, "审核状态"),
                "audit_reject_reason": safe_get(row, "审核未通过原因"),
                "sales_mode": safe_get(row, "售卖方式"),
                "creator_id": safe_get(row, "创建人ID"),
                "creator_name": safe_get(row, "创建人名称"),
                "created_at": safe_get(row, "创建时间"),
                "updated_at": safe_get(row, "修改时间"),
                "drama_source": safe_get(row, "短剧来源"),
                "copyright_material_uploaded": safe_get(row, "是否上传版权材料"),
                "script_id": match.script_id,
                "script_title": match.script_title,
                "match_status": match.match_status,
                "match_method": match.match_method,
                "match_confidence": match.match_confidence,
                "review_required": match.review_required,
                "match_reason": match.reason,
                "source_file": safe_get(row, "source_file"),
                "source_sheet": safe_get(row, "source_sheet"),
            }
        )
    return pd.DataFrame(rows)


def normalize_drama_daily(df: pd.DataFrame, catalog: pd.DataFrame, script_registry: pd.DataFrame) -> pd.DataFrame:
    rows = []

    catalog_by_norm = {}
    if not catalog.empty:
        for _, c in catalog.iterrows():
            catalog_by_norm[str(c.get("title_norm") or "")] = c

    for _, row in df.iterrows():
        title = safe_get(row, "短剧名称")
        title_norm = normalize_title(title)
        catalog_row = catalog_by_norm.get(title_norm)

        match = match_title_to_script(title, script_registry)

        platform_drama_id = ""
        if catalog_row is not None:
            platform_drama_id = catalog_row.get("platform_drama_id", "")

        rows.append(
            {
                "platform": PLATFORM,
                "date": safe_get(row, "日期"),
                "platform_drama_id": platform_drama_id,
                "raw_title": title,
                "canonical_title": title,
                "title_norm": title_norm,
                "script_id": match.script_id,
                "script_title": match.script_title,
                "match_status": match.match_status,
                "match_method": match.match_method,
                "match_confidence": match.match_confidence,
                "review_required": match.review_required,
                "play_count": to_number(safe_get(row, "视频-播放数", "视频播放数", "播放数", "播放量")),
                "like_count": to_number(safe_get(row, "视频-点赞数", "点赞数", "点赞量")),
                "comment_count": to_number(safe_get(row, "视频-评论数", "评论数", "评论量")),
                "favorite_count": to_number(safe_get(row, "视频-收藏数", "收藏数", "收藏量")),
                "paid_users": to_number(safe_get(row, "付费人数")),
                "paid_amount": to_number(safe_get(row, "付费金额")),
                "paid_orders": to_number(safe_get(row, "付费单量")),
                "ad_spend": to_number(safe_get(row, "消耗", "花费（元）", "花费(元)")),
                "roi": to_number(safe_get(row, "全域ROI", "全域 ROI", "ROI")),
                "source_file": safe_get(row, "source_file"),
                "source_sheet": safe_get(row, "source_sheet"),
            }
        )

    return pd.DataFrame(rows)


def normalize_ad_daily(df: pd.DataFrame, known_titles: list[str], script_registry: pd.DataFrame) -> pd.DataFrame:
    rows = []

    for _, row in df.iterrows():
        account_name = safe_get(row, "广告账户名称")
        extracted_title, extract_method = extract_title_from_account_name(account_name, known_titles)

        if extract_method == "generic_account_name":
            match = MatchResult("", "", "account_name_generic", "none", 0.0, True, "generic_account_name")
        elif extracted_title:
            match = match_title_to_script(extracted_title, script_registry)
            if extract_method == "heuristic_segment" and match.match_status == "matched":
                match = MatchResult(
                    match.script_id,
                    match.script_title,
                    "needs_review",
                    "account_name_heuristic_segment",
                    min(match.match_confidence, 0.85),
                    True,
                    "title_extracted_from_account_name",
                )
        else:
            match = MatchResult("", "", "unmatched", "none", 0.0, True, "cannot_extract_title")

        rows.append(
            {
                "platform": PLATFORM,
                "date": safe_get(row, "日期"),
                "ad_account_id": safe_get(row, "广告账户"),
                "ad_account_name": account_name,
                "extracted_title": extracted_title,
                "extract_method": extract_method,
                "script_id": match.script_id,
                "script_title": match.script_title,
                "match_status": match.match_status,
                "match_method": match.match_method,
                "match_confidence": match.match_confidence,
                "review_required": match.review_required,
                "match_reason": match.reason,
                "impressions": to_number(safe_get(row, "曝光数")),
                "spend": to_number(safe_get(row, "花费（元）", "花费(元)", "消耗")),
                "cover_clicks": to_number(safe_get(row, "封面点击数")),
                "cover_impressions": to_number(safe_get(row, "封面曝光数")),
                "material_impressions": to_number(safe_get(row, "素材曝光数")),
                "valid_play_count": to_number(safe_get(row, "有效播放数")),
                "play_75_count": to_number(safe_get(row, "75%进度播放数", "75% 进度播放数")),
                "complete_play_count": to_number(safe_get(row, "播放完成", "完播数")),
                "completion_rate": to_number(safe_get(row, "完播率")),
                "like_count": to_number(safe_get(row, "点赞量", "点赞数")),
                "comment_count": to_number(safe_get(row, "评论量", "评论数")),
                "share_count": to_number(safe_get(row, "分享数", "分享量")),
                "negative_reduce_count": to_number(safe_get(row, "减少此类作品数")),
                "report_count": to_number(safe_get(row, "举报数")),
                "block_count": to_number(safe_get(row, "拉黑数")),
                "iaa_ltv": to_number(safe_get(row, "IAA广告变现LTV（元）", "IAA广告变现LTV(元)", "IAA LTV")),
                "iaa_roi": to_number(safe_get(row, "IAA广告变现ROI", "IAA ROI")),
                "source_file": safe_get(row, "source_file"),
                "source_sheet": safe_get(row, "source_sheet"),
            }
        )

    return pd.DataFrame(rows)




def make_ad_account_review_tables(ad_daily: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    review_columns_unique = [
        "ad_account_name",
        "extracted_title",
        "script_id",
        "script_title",
        "match_status",
        "match_method",
        "match_confidence",
        "match_reason",
        "review_required",
        "source_file",
    ]

    review_columns_by_spend = [
        "ad_account_name",
        "rows",
        "total_spend",
        "sample_extracted_title",
        "sample_script_title",
        "sample_match_status",
        "sample_match_method",
        "sample_match_confidence",
        "sample_match_reason",
    ]

    if ad_daily.empty or "match_status" not in ad_daily.columns:
        return (
            pd.DataFrame(columns=review_columns_unique),
            pd.DataFrame(columns=review_columns_by_spend),
        )

    review = ad_daily[
        ad_daily["match_status"].isin(["account_name_generic", "needs_review", "unmatched", "ambiguous_match"])
    ].copy()

    if review.empty:
        return (
            pd.DataFrame(columns=review_columns_unique),
            pd.DataFrame(columns=review_columns_by_spend),
        )

    for col in review_columns_unique:
        if col not in review.columns:
            review[col] = ""

    review_unique = (
        review[review_columns_unique]
        .drop_duplicates()
        .sort_values(["match_status", "ad_account_name"], kind="stable")
        .reset_index(drop=True)
    )

    review["spend_numeric"] = pd.to_numeric(review.get("spend", 0), errors="coerce").fillna(0)

    rows = []
    for account_name, group in review.groupby("ad_account_name", dropna=False):
        first = group.iloc[0]
        rows.append(
            {
                "ad_account_name": account_name,
                "rows": int(len(group)),
                "total_spend": round(float(group["spend_numeric"].sum()), 4),
                "sample_extracted_title": first.get("extracted_title", ""),
                "sample_script_title": first.get("script_title", ""),
                "sample_match_status": first.get("match_status", ""),
                "sample_match_method": first.get("match_method", ""),
                "sample_match_confidence": first.get("match_confidence", ""),
                "sample_match_reason": first.get("match_reason", ""),
            }
        )

    review_by_spend = pd.DataFrame(rows, columns=review_columns_by_spend)
    if not review_by_spend.empty:
        review_by_spend = review_by_spend.sort_values(
            ["total_spend", "rows", "ad_account_name"],
            ascending=[False, False, True],
            kind="stable",
        ).reset_index(drop=True)

    return review_unique, review_by_spend

def make_match_report(catalog: pd.DataFrame, drama_daily: pd.DataFrame, ad_daily: pd.DataFrame) -> pd.DataFrame:
    rows = []

    def add_rows(df: pd.DataFrame, source_table: str, title_col: str):
        if df.empty:
            return
        for _, row in df.iterrows():
            status = str(row.get("match_status", ""))
            if status in {"matched"}:
                continue
            rows.append(
                {
                    "source_table": source_table,
                    "platform_title": row.get(title_col, ""),
                    "platform_drama_id": row.get("platform_drama_id", ""),
                    "ad_account_name": row.get("ad_account_name", ""),
                    "extracted_title": row.get("extracted_title", ""),
                    "candidate_script_id": row.get("script_id", ""),
                    "candidate_script_title": row.get("script_title", ""),
                    "match_status": status,
                    "match_method": row.get("match_method", ""),
                    "match_confidence": row.get("match_confidence", ""),
                    "reason": row.get("match_reason", ""),
                    "suggested_action": suggest_action(status),
                    "source_file": row.get("source_file", ""),
                }
            )

    add_rows(catalog, "kuaishou_drama_catalog", "raw_title")
    add_rows(drama_daily, "kuaishou_drama_daily_stats", "raw_title")
    add_rows(ad_daily, "kuaishou_ad_account_daily_stats", "extracted_title")

    if not rows:
        return pd.DataFrame(
            columns=[
                "source_table",
                "platform_title",
                "platform_drama_id",
                "ad_account_name",
                "extracted_title",
                "candidate_script_id",
                "candidate_script_title",
                "match_status",
                "match_method",
                "match_confidence",
                "reason",
                "suggested_action",
                "source_file",
            ]
        )

    report = pd.DataFrame(rows)
    report = report.drop_duplicates()
    return report


def suggest_action(status: str) -> str:
    if status == "script_file_missing":
        return "补充对应剧本文本到 data/episode_scripts，或在映射表中登记为空剧本"
    if status == "title_alias_missing":
        return "人工确认后补充标题别名"
    if status == "account_name_generic":
        return "需要运营补充广告账户名/计划名到短剧ID的映射"
    if status == "ambiguous_match":
        return "人工复核，不能自动确认"
    if status == "needs_review":
        return "人工确认候选剧本，确认后补充 alias 或 mapping"
    return "人工检查"


def write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="快手原始数据目录")
    parser.add_argument("--episode-scripts", required=True, help="本地剧本文本目录")
    parser.add_argument("--output", required=True, help="规范化输出目录")
    args = parser.parse_args()

    input_dir = Path(args.input)
    episode_scripts_dir = Path(args.episode_scripts)
    output_dir = Path(args.output)

    script_registry = build_script_registry(episode_scripts_dir)

    all_catalog_frames: list[pd.DataFrame] = []
    all_drama_daily_frames: list[pd.DataFrame] = []
    all_ad_daily_frames: list[pd.DataFrame] = []
    all_overall_daily_frames: list[pd.DataFrame] = []
    unknown_files: list[dict[str, str]] = []

    files = [
        p for p in input_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in {".csv", ".xls", ".xlsx"}
    ]

    print(f"[kuaishou] 待处理文件数：{len(files)}")

    for path in files:
        print(f"[kuaishou] 读取：{path}")
        frames = read_any_table(path)
        for df in frames:
            kind = classify_table(df)
            print(f"[kuaishou]   sheet={df.get('source_sheet', pd.Series([''])).iloc[0]} kind={kind} rows={len(df)}")

            if kind == "drama_catalog":
                all_catalog_frames.append(df)
            elif kind == "drama_daily":
                all_drama_daily_frames.append(df)
            elif kind == "overall_daily":
                all_overall_daily_frames.append(df)
            elif kind in {"ad_account_daily", "core_daily"}:
                all_ad_daily_frames.append(df)
            else:
                unknown_files.append({"file": path.name, "columns": ",".join(df.columns)})

    raw_catalog = pd.concat(all_catalog_frames, ignore_index=True) if all_catalog_frames else pd.DataFrame()
    raw_drama_daily = pd.concat(all_drama_daily_frames, ignore_index=True) if all_drama_daily_frames else pd.DataFrame()
    raw_ad_daily = pd.concat(all_ad_daily_frames, ignore_index=True, sort=False) if all_ad_daily_frames else pd.DataFrame()
    raw_overall_daily = pd.concat(all_overall_daily_frames, ignore_index=True, sort=False) if all_overall_daily_frames else pd.DataFrame()

    catalog = normalize_catalog(raw_catalog, script_registry) if not raw_catalog.empty else pd.DataFrame()

    known_titles: list[str] = []
    if not catalog.empty:
        known_titles.extend([str(x) for x in catalog["raw_title"].dropna().tolist()])
    if not script_registry.empty:
        known_titles.extend([str(x) for x in script_registry["canonical_title"].dropna().tolist()])
    known_titles = sorted(set([x for x in known_titles if x.strip()]), key=len, reverse=True)

    drama_daily = (
        normalize_drama_daily(raw_drama_daily, catalog, script_registry)
        if not raw_drama_daily.empty
        else pd.DataFrame()
    )

    ad_daily = (
        normalize_ad_daily(raw_ad_daily, known_titles, script_registry)
        if not raw_ad_daily.empty
        else pd.DataFrame()
    )

    overall_daily = (
        normalize_overall_daily(raw_overall_daily)
        if not raw_overall_daily.empty
        else pd.DataFrame()
    )

    match_report = make_match_report(catalog, drama_daily, ad_daily)
    ad_account_review_unique, ad_account_review_by_spend = make_ad_account_review_tables(ad_daily)

    write_csv(script_registry, output_dir / "script_registry.csv")
    write_csv(catalog, output_dir / "kuaishou_drama_catalog.csv")
    write_csv(drama_daily, output_dir / "kuaishou_drama_daily_stats.csv")
    write_csv(ad_daily, output_dir / "kuaishou_ad_account_daily_stats.csv")
    write_csv(overall_daily, output_dir / "kuaishou_overall_daily_stats.csv")
    write_csv(match_report, output_dir / "kuaishou_title_match_report.csv")
    write_csv(ad_account_review_unique, output_dir / "kuaishou_ad_account_review_unique.csv")
    write_csv(ad_account_review_by_spend, output_dir / "kuaishou_ad_account_review_by_spend.csv")

    summary = {
        "platform": PLATFORM,
        "input_dir": str(input_dir),
        "episode_scripts_dir": str(episode_scripts_dir),
        "output_dir": str(output_dir),
        "file_count": len(files),
        "script_count": int(len(script_registry)),
        "drama_catalog_rows": int(len(catalog)),
        "drama_daily_rows": int(len(drama_daily)),
        "ad_account_daily_rows": int(len(ad_daily)),
        "overall_daily_rows": int(len(overall_daily)),
        "match_report_rows": int(len(match_report)),
        "ad_account_review_unique_rows": int(len(ad_account_review_unique)),
        "ad_account_review_by_spend_rows": int(len(ad_account_review_by_spend)),
        "catalog_match_status_counts": catalog["match_status"].value_counts(dropna=False).to_dict() if not catalog.empty else {},
        "drama_daily_match_status_counts": drama_daily["match_status"].value_counts(dropna=False).to_dict() if not drama_daily.empty else {},
        "ad_daily_match_status_counts": ad_daily["match_status"].value_counts(dropna=False).to_dict() if not ad_daily.empty else {},
        "unknown_files": unknown_files,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "kuaishou_market_feedback_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("")
    print("[kuaishou] 导入完成")
    print(f"[kuaishou] 本地剧本数：{len(script_registry)}")
    print(f"[kuaishou] 短剧资产行数：{len(catalog)}")
    print(f"[kuaishou] 短剧日数据行数：{len(drama_daily)}")
    print(f"[kuaishou] 广告账户日数据行数：{len(ad_daily)}")
    print(f"[kuaishou] 平台整体日数据行数：{len(overall_daily)}")
    print(f"[kuaishou] 需处理匹配问题行数：{len(match_report)}")
    print(f"[kuaishou] 广告账户复核去重行数：{len(ad_account_review_unique)}")
    print(f"[kuaishou] 广告账户复核按消耗聚合行数：{len(ad_account_review_by_spend)}")
    print(f"[kuaishou] 输出目录：{output_dir}")

    if unknown_files:
        print("[kuaishou] 有无法分类的文件/表，请查看 summary.json 里的 unknown_files")


if __name__ == "__main__":
    main()
