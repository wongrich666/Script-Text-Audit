from __future__ import annotations

import argparse
import random
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATE_PATH = PROJECT_ROOT / "data" / "tencent_video_auth" / "state.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "tencent_video_exports" / "album_trends"
DEFAULT_INCLUDE_PATTERN = r".*"
DEFAULT_ALBUM_DATA_URL = "https://mp.v.qq.com/analysis/cid"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@dataclass
class AlbumTrendSyncResult:
    downloaded_files: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def downloads(self) -> list[str]:
        return self.downloaded_files


def sanitize_filename(value: str) -> str:
    sanitized = re.sub(r'[\\/:*?"<>|]+', "_", value.strip())
    sanitized = re.sub(r"\s+", "_", sanitized)
    sanitized = sanitized.strip("._")
    return sanitized or "untitled"


def dedupe_titles(titles: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for title in titles:
        clean_title = str(title or "").strip()
        if not clean_title or clean_title in seen:
            continue
        seen.add(clean_title)
        unique.append(clean_title)
    return unique


def filter_titles_by_pattern(titles: list[str], pattern: str) -> list[str]:
    compiled = re.compile(pattern)
    return [title for title in titles if compiled.search(title)]


def build_download_filename(title: str, now: datetime | None = None, index: int | None = None) -> str:
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    suffix = f"-{index}" if index is not None else ""
    return f"专辑数据-{sanitize_filename(title)}-{stamp}{suffix}.xlsx"


def _import_sync_playwright() -> Any:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright 未安装。请先运行：pip install playwright && python -m playwright install chromium"
        ) from exc
    return sync_playwright


def _locator_count(locator: Any) -> int:
    try:
        return int(locator.count())
    except Exception:
        return 0


def is_album_drawer_open(page: Any) -> bool:
    selectors = [
        ".drawer-open",
        "[class*='drawer-open']",
        ".ant-drawer-open",
        "[class*='drawer'][class*='open']",
    ]
    return any(_locator_count(page.locator(selector)) > 0 for selector in selectors)


def close_album_drawer(page: Any, warnings: list[str] | None = None, timeout_ms: int = 5000) -> bool:
    if not is_album_drawer_open(page):
        print("drawer-open: 未检测到，无需关闭")
        return True

    print("drawer-open: 已检测到，尝试关闭专辑抽屉")
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
        page.locator(".drawer-open, [class*='drawer-open'], .ant-drawer-open").first.wait_for(
            state="hidden",
            timeout=timeout_ms,
        )
        print("drawer-open: 已通过 Escape 关闭")
        return True
    except Exception:
        pass

    for selector in [
        ".drawer-open button[aria-label='Close']",
        "[class*='drawer-open'] button[aria-label='Close']",
        ".ant-drawer-close",
        "[class*='drawer'] [class*='close']",
    ]:
        try:
            locator = page.locator(selector)
            if _locator_count(locator) > 0:
                locator.first.click(timeout=timeout_ms)
                page.wait_for_timeout(500)
                if not is_album_drawer_open(page):
                    print("drawer-open: 已通过关闭按钮关闭")
                    return True
        except Exception:
            continue

    for selector in [".ant-drawer-mask", "[class*='drawer-mask']", "[class*='mask']"]:
        try:
            locator = page.locator(selector)
            if _locator_count(locator) > 0:
                locator.first.click(timeout=timeout_ms, force=True)
                page.wait_for_timeout(500)
                if not is_album_drawer_open(page):
                    print("drawer-open: 已通过遮罩层关闭")
                    return True
        except Exception:
            continue

    message = "切换专辑抽屉仍未关闭，继续执行但后续点击可能被遮挡。"
    print(f"drawer-open: {message}")
    if warnings is not None:
        warnings.append(message)
    return False


def _click_locator_with_force_fallback(locator: Any, timeout_ms: int) -> None:
    target = locator.first
    try:
        target.click(timeout=timeout_ms)
    except Exception:
        target.click(timeout=timeout_ms, force=True)


def _click_element_with_fallback(element: Any, timeout_ms: int) -> None:
    try:
        element.scroll_into_view_if_needed(timeout=timeout_ms)
    except Exception:
        pass
    try:
        element.click(timeout=timeout_ms)
        return
    except Exception:
        pass
    try:
        element.click(timeout=timeout_ms, force=True)
        return
    except Exception:
        pass
    element.evaluate("(node) => node.click()")


def _find_first_visible(locator: Any, label: str) -> Any | None:
    count = _locator_count(locator)
    print(f"{label}: 匹配到 {count} 个候选下载按钮")
    for index in range(count):
        item = locator.nth(index)
        try:
            visible = bool(item.is_visible(timeout=500))
        except Exception:
            visible = False
        print(f"{label}: 下载按钮候选 #{index} visible={visible}")
        if visible:
            return item
    return None


def _target_scopes(page: Any, title: str) -> list[Any]:
    scopes: list[Any] = []
    drawer_item = find_album_item_in_drawer(page, title)
    if drawer_item is not None:
        scopes.append(drawer_item)

    for selector in [
        "li",
        "div[class*='listItem']",
        "div[class*='item']",
        "div[class*='card']",
        "div[class*='panel']",
        "div[class*='content']",
    ]:
        try:
            locator = page.locator(selector).filter(has_text=title)
        except Exception:
            continue
        for index in range(_locator_count(locator)):
            item = locator.nth(index)
            try:
                if item.is_visible(timeout=500):
                    scopes.append(item)
            except Exception:
                continue
    return scopes


def _element_debug_info(element: Any) -> tuple[str, str]:
    try:
        data = element.evaluate(
            """
            (node) => ({
              className: node.className || '',
              text: (node.innerText || node.textContent || '').trim()
            })
            """
        )
    except Exception:
        return "", ""
    if isinstance(data, dict):
        return str(data.get("className") or ""), str(data.get("text") or "")
    return "", ""


def find_visible_download_button(page: Any, title: str) -> Any | None:
    scopes = _target_scopes(page, title)

    for scope_index, scope in enumerate(scopes):
        scope_label = f"{title}: scope#{scope_index}"
        candidates = [
            scope.get_by_text("下载数据", exact=True),
            scope.locator("button:has-text('下载数据')"),
            scope.locator("a:has-text('下载数据')"),
            scope.locator("text=下载数据"),
        ]
        for candidate in candidates:
            visible = _find_first_visible(candidate, scope_label)
            if visible is not None:
                class_name, text = _element_debug_info(visible)
                print(f"{title}: 选择当前可见“下载数据”按钮 className={class_name} text={text}")
                return visible
        try:
            scope.scroll_into_view_if_needed(timeout=1000)
        except Exception:
            pass
        try:
            page.mouse.wheel(0, 800)
            scope.wait_for_timeout(300)
        except Exception:
            pass
    print(f"{title}: 当前 drawer/目标行内未找到可见“下载数据”按钮")
    return None


def _click_album_switch(page: Any, timeout_ms: int) -> None:
    drawer_open = is_album_drawer_open(page)
    print(f"drawer-open: {drawer_open}")
    if drawer_open:
        print("切换专辑抽屉已打开，复用现有抽屉")
        return

    candidates = [
        lambda: page.get_by_role("button", name="切换专辑"),
        lambda: page.get_by_text("切换专辑", exact=True),
        lambda: page.locator("button:has-text('切换专辑')"),
        lambda: page.locator("text=切换专辑"),
    ]
    for get_locator in candidates:
        locator = get_locator()
        if _locator_count(locator) > 0:
            _click_locator_with_force_fallback(locator, timeout_ms)
            return
    raise RuntimeError("未找到“切换专辑”按钮。")


def _visible_drawer(page: Any) -> Any | None:
    for selector in [".drawer-open", "[class*='drawer-open']", ".ant-drawer-open", "[class*='drawer'][class*='open']"]:
        locator = page.locator(selector)
        for index in range(_locator_count(locator)):
            item = locator.nth(index)
            try:
                if item.is_visible(timeout=500):
                    return item
            except Exception:
                continue
    return None


def collect_album_titles(page: Any, *, max_scrolls: int = 8, wait_ms: int = 500) -> list[str]:
    drawer = _visible_drawer(page)
    if drawer is None:
        return []

    titles: list[str] = []
    last_count = -1
    selectors = [
        ".titleText",
        "[class*='titleText']",
        "li",
        "div[class*='listItem']",
        "div[class*='item']",
        "div[class*='itemTexts']",
    ]

    for _ in range(max_scrolls):
        for selector in selectors:
            locator = drawer.locator(selector)
            for index in range(_locator_count(locator)):
                try:
                    text = locator.nth(index).inner_text(timeout=1000).strip()
                except Exception:
                    continue
                if text and text != "切换":
                    lines = [line.strip() for line in text.splitlines() if line.strip()]
                    titles.extend(line for line in lines if line != "切换")

        if len(titles) == last_count:
            break
        last_count = len(titles)

        try:
            page.mouse.wheel(0, 1800)
            page.wait_for_timeout(wait_ms)
        except Exception:
            break

    return dedupe_titles(titles)


def _item_has_switch(item: Any) -> bool:
    candidates = [
        item.get_by_text("切换", exact=True),
        item.locator("button:has-text('切换')"),
        item.locator("text=切换"),
    ]
    return any(_locator_count(candidate) > 0 for candidate in candidates)


def find_album_item_in_drawer(page: Any, title: str) -> Any | None:
    drawer = _visible_drawer(page)
    if drawer is None:
        print(f"{title}: 未找到可见专辑抽屉")
        return None

    candidates: list[Any] = []
    for selector in ["li", "div[class*='listItem']", "div[class*='item']", "div[class*='itemTexts']"]:
        locator = drawer.locator(selector).filter(has_text=title)
        for index in range(_locator_count(locator)):
            candidates.append(locator.nth(index))

    print(f"{title}: drawer 内匹配到 {len(candidates)} 个候选专辑 item")
    fallback: Any | None = None
    for index, item in enumerate(candidates):
        try:
            visible = bool(item.is_visible(timeout=500))
        except Exception:
            visible = False
        print(f"{title}: 候选 item #{index} visible={visible}")
        if not visible:
            continue
        if fallback is None:
            fallback = item
        if _item_has_switch(item):
            print(f"{title}: 选择候选 item #{index}")
            return item
    return fallback


def _click_album_item(page: Any, title: str, timeout_ms: int, warnings: list[str] | None = None) -> bool:
    item = find_album_item_in_drawer(page, title)
    if item is None:
        message = f"{title}: 专辑抽屉内未找到可见专辑项。"
        print(message)
        if warnings is not None:
            warnings.append(message)
        return False

    try:
        item.scroll_into_view_if_needed(timeout=timeout_ms)
    except Exception:
        pass

    candidates = [
        item.get_by_text("切换", exact=True),
        item.locator("button:has-text('切换')"),
        item.locator("text=切换"),
    ]
    for candidate in candidates:
        if _locator_count(candidate) == 0:
            continue
        try:
            candidate.first.click(timeout=timeout_ms)
            print(f"{title}: 已点击“切换”按钮")
            return True
        except Exception:
            try:
                candidate.first.click(timeout=timeout_ms, force=True)
                print(f"{title}: 已 force 点击“切换”按钮")
                return True
            except Exception:
                continue

    try:
        item.evaluate(
            """
            (node) => {
              const buttons = Array.from(node.querySelectorAll('button, a, span, div'));
              const target = buttons.find((el) => (el.innerText || el.textContent || '').trim() === '切换');
              if (target) {
                target.click();
              } else {
                node.click();
              }
            }
            """
        )
        print(f"{title}: 已通过 DOM evaluate 点击专辑项")
        return True
    except Exception as exc:
        message = f"{title}: 点击专辑项失败。原因：{exc}"
        print(message)
        if warnings is not None:
            warnings.append(message)
        return False


def _wait_current_title(page: Any, title: str, timeout_ms: int) -> None:
    try:
        page.get_by_text(title, exact=True).first.wait_for(state="visible", timeout=timeout_ms)
    except Exception:
        page.wait_for_timeout(1500)


def _download_album_data(page: Any, title: str, output_dir: Path, timeout_ms: int) -> list[str]:
    download_button = find_visible_download_button(page, title)
    if download_button is None:
        raise RuntimeError(f"{title}: 未找到“下载数据”按钮。")

    output_dir.mkdir(parents=True, exist_ok=True)
    downloads: list[Any] = []

    def handle_download(download: Any) -> None:
        downloads.append(download)

    page.on("download", handle_download)
    print(f"{title}: 点击下载数据")
    _click_element_with_fallback(download_button, timeout_ms)
    page.wait_for_timeout(5000)

    saved_files: list[str] = []
    for index, download in enumerate(downloads, start=1):
        target_path = output_dir / build_download_filename(title, index=index if len(downloads) > 1 else None)
        download.save_as(str(target_path))
        saved_files.append(str(target_path))
        print(f"{title}: 下载文件路径 {target_path}")
    return saved_files


def sync_album_trends(
    *,
    url: str,
    include_pattern: str,
    limit: int | None,
    output_dir: str | Path,
    state_path: str | Path = DEFAULT_STATE_PATH,
    headless: bool = False,
    timeout_ms: int = 30000,
) -> AlbumTrendSyncResult:
    result = AlbumTrendSyncResult()
    state_file = Path(state_path)
    output_path = Path(output_dir)

    if not state_file.exists():
        result.warnings.append("登录态不存在，请先运行：python scripts/bind_tencent_video_login.py")
        return result

    sync_playwright = _import_sync_playwright()
    output_path.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        context = browser.new_context(storage_state=str(state_file), accept_downloads=True)
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        try:
            page.wait_for_load_state("networkidle", timeout=timeout_ms)
        except Exception:
            result.warnings.append("页面 networkidle 等待超时，继续尝试读取专辑列表。")
        try:
            page.get_by_text("专辑分析").first.wait_for(state="visible", timeout=timeout_ms)
        except Exception:
            page.get_by_text("切换专辑").first.wait_for(state="visible", timeout=timeout_ms)

        _click_album_switch(page, timeout_ms)
        page.wait_for_timeout(1000)
        titles = filter_titles_by_pattern(collect_album_titles(page), include_pattern)
        if limit is not None and limit > 0:
            titles = titles[:limit]

        for title in titles:
            print(f"当前处理专辑：{title}")
            try:
                _click_album_switch(page, timeout_ms)
                page.wait_for_timeout(500)
                if not _click_album_item(page, title, timeout_ms, result.warnings):
                    continue
                _wait_current_title(page, title, timeout_ms)
                downloaded = _download_album_data(page, title, output_path, timeout_ms)
                close_album_drawer(page, result.warnings, timeout_ms=timeout_ms)
                if downloaded:
                    result.downloaded_files.extend(downloaded)
                else:
                    result.warnings.append(f"{title}: 点击下载数据后未捕获到下载文件。")
            except Exception as exc:
                result.warnings.append(f"{title}: 下载失败，继续下一个。原因：{exc}")
            time.sleep(random.uniform(2, 5))

        browser.close()

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="批量下载腾讯视频创作平台专辑趋势数据。")
    parser.add_argument("--url", default=DEFAULT_ALBUM_DATA_URL, help="腾讯视频后台专辑数据页 URL")
    parser.add_argument("--include-pattern", default=DEFAULT_INCLUDE_PATTERN, help="需要下载的专辑标题正则")
    parser.add_argument("--limit", type=int, default=None, help="只下载前 N 个专辑，用于测试")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_DIR), help="下载输出目录")
    parser.add_argument("--headless", action="store_true", help="无头模式。默认关闭，方便观察浏览器动作。")
    args = parser.parse_args()

    result = sync_album_trends(
        url=args.url,
        include_pattern=args.include_pattern,
        limit=args.limit,
        output_dir=args.output,
        headless=args.headless,
    )

    print("腾讯视频专辑趋势数据同步完成。")
    print("")
    print("下载文件：")
    if result.downloaded_files:
        for path in result.downloaded_files:
            print(f"- {path}")
    else:
        print("- 无")

    print("")
    print("Warnings：")
    if result.warnings:
        for warning in result.warnings:
            print(f"- {warning}")
    else:
        print("- 无")


if __name__ == "__main__":
    main()
