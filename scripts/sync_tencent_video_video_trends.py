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
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "tencent_video_exports" / "video_trends"
DEFAULT_INCLUDE_PATTERN = r"^SJS_\d+$"
DEFAULT_VIDEO_DATA_URL = "https://mp.v.qq.com/datacenter/video"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@dataclass
class VideoTrendSyncResult:
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


def build_download_filename(title: str, now: datetime | None = None) -> str:
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    return f"视频趋势数据-{sanitize_filename(title)}-{stamp}.xlsx"


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


def is_switch_drawer_open(page: Any) -> bool:
    selectors = [
        ".drawer-open",
        "[class*='drawer-open']",
        ".ant-drawer-open",
        "[class*='drawer'][class*='open']",
    ]
    return any(_locator_count(page.locator(selector)) > 0 for selector in selectors)


def close_switch_drawer(page: Any, warnings: list[str] | None = None, timeout_ms: int = 5000) -> bool:
    if not is_switch_drawer_open(page):
        print("drawer-open: 未检测到，无需关闭")
        return True

    print("drawer-open: 已检测到，尝试关闭抽屉")
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

    close_selectors = [
        ".drawer-open button[aria-label='Close']",
        ".drawer-open button[aria-label='close']",
        "[class*='drawer-open'] button[aria-label='Close']",
        ".ant-drawer-close",
        "[class*='drawer'] [class*='close']",
    ]
    for selector in close_selectors:
        try:
            locator = page.locator(selector)
            if _locator_count(locator) > 0:
                locator.first.click(timeout=timeout_ms)
                page.wait_for_timeout(500)
                if not is_switch_drawer_open(page):
                    print("drawer-open: 已通过关闭按钮关闭")
                    return True
        except Exception:
            continue

    mask_selectors = [
        ".ant-drawer-mask",
        "[class*='drawer-mask']",
        "[class*='mask']",
    ]
    for selector in mask_selectors:
        try:
            locator = page.locator(selector)
            if _locator_count(locator) > 0:
                locator.first.click(timeout=timeout_ms, force=True)
                page.wait_for_timeout(500)
                if not is_switch_drawer_open(page):
                    print("drawer-open: 已通过遮罩层关闭")
                    return True
        except Exception:
            continue

    message = "切换视频抽屉仍未关闭，继续执行但后续点击可能被遮挡。"
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


def _click_switch_video(page: Any, timeout_ms: int) -> None:
    drawer_open = is_switch_drawer_open(page)
    print(f"drawer-open: {drawer_open}")
    if drawer_open:
        print("切换视频抽屉已打开，复用现有抽屉")
        return

    candidates = [
        lambda: page.get_by_role("button", name="切换视频"),
        lambda: page.get_by_text("切换视频", exact=True),
        lambda: page.locator("button:has-text('切换视频')"),
        lambda: page.locator("text=切换视频"),
    ]
    for get_locator in candidates:
        locator = get_locator()
        if locator.count() > 0:
            _click_locator_with_force_fallback(locator, timeout_ms)
            return
    raise RuntimeError("未找到“切换视频”按钮。")


def _visible_drawer(page: Any) -> Any | None:
    selectors = [
        ".drawer-open",
        "[class*='drawer-open']",
        ".ant-drawer-open",
        "[class*='drawer'][class*='open']",
    ]
    for selector in selectors:
        locator = page.locator(selector)
        count = _locator_count(locator)
        for index in range(count):
            item = locator.nth(index)
            try:
                if item.is_visible(timeout=500):
                    return item
            except Exception:
                continue
    return None


def _candidate_video_items(page: Any) -> Any:
    selectors = [
        ".titleText",
        "[class*='titleText']",
        "[class*='title']",
    ]
    for selector in selectors:
        locator = page.locator(selector)
        if locator.count() > 0:
            return locator
    return page.locator("text=/\\S+/")


def collect_video_titles(page: Any, *, max_scrolls: int = 8, wait_ms: int = 500) -> list[str]:
    titles: list[str] = []
    last_count = -1

    for _ in range(max_scrolls):
        locator = _candidate_video_items(page)
        count = locator.count()
        for index in range(count):
            try:
                text = locator.nth(index).inner_text(timeout=1000).strip()
            except Exception:
                continue
            if text:
                titles.append(text)

        if len(titles) == last_count:
            break
        last_count = len(titles)

        try:
            page.mouse.wheel(0, 1800)
            page.wait_for_timeout(wait_ms)
        except Exception:
            break

    return dedupe_titles(titles)


def _item_has_visible_switch_button(item: Any) -> bool:
    candidates = [
        item.get_by_text("切换", exact=True),
        item.locator("button:has-text('切换')"),
        item.locator("text=切换"),
    ]
    for candidate in candidates:
        count = _locator_count(candidate)
        for index in range(count):
            button = candidate.nth(index)
            try:
                if button.is_visible(timeout=500):
                    return True
            except Exception:
                continue
    return False


def find_video_item_in_drawer(page: Any, title: str) -> Any | None:
    drawer = _visible_drawer(page)
    if drawer is None:
        print(f"{title}: 未找到可见 drawer-open")
        return None

    selectors = [
        "li",
        "div[class*='listItem']",
        "div[class*='item']",
        "div[class*='itemTexts']",
    ]
    candidates: list[Any] = []
    seen_keys: set[str] = set()
    for selector in selectors:
        locator = drawer.locator(selector).filter(has_text=title)
        count = _locator_count(locator)
        for index in range(count):
            item = locator.nth(index)
            key = f"{selector}:{index}"
            if key in seen_keys:
                continue
            seen_keys.add(key)
            candidates.append(item)

    print(f"{title}: drawer 内匹配到 {len(candidates)} 个候选 item")
    fallback_visible_item: Any | None = None
    for index, item in enumerate(candidates):
        try:
            visible = bool(item.is_visible(timeout=500))
        except Exception:
            visible = False
        print(f"{title}: 候选 item #{index} visible={visible}")
        if not visible:
            continue
        if fallback_visible_item is None:
            fallback_visible_item = item
        if _item_has_visible_switch_button(item):
            print(f"{title}: 选择候选 item #{index} 的可见“切换”按钮")
            return item

    if fallback_visible_item is not None:
        print(f"{title}: 未找到可见按钮，返回第一个可见 item 供后续 scroll/fallback")
        return fallback_visible_item
    return None


def _visible_switch_button_in_item(item: Any) -> Any | None:
    candidates = [
        item.get_by_text("切换", exact=True),
        item.locator("button:has-text('切换')"),
        item.locator("text=切换"),
    ]
    first_hidden: Any | None = None
    for candidate in candidates:
        count = _locator_count(candidate)
        for index in range(count):
            button = candidate.nth(index)
            if first_hidden is None:
                first_hidden = button
            try:
                if button.is_visible(timeout=500):
                    return button
            except Exception:
                continue
    return first_hidden


def _switch_to_video(page: Any, title: str, timeout_ms: int, warnings: list[str] | None = None) -> bool:
    item = find_video_item_in_drawer(page, title)
    if item is None:
        message = f"{title}: drawer 内未找到可见视频项。"
        if warnings is not None:
            warnings.append(message)
        print(message)
        return False

    try:
        item.scroll_into_view_if_needed(timeout=timeout_ms)
    except Exception:
        pass

    switch_button = _visible_switch_button_in_item(item)
    if switch_button is None:
        message = f"{title}: 可见视频项内未找到“切换”按钮。"
        if warnings is not None:
            warnings.append(message)
        print(message)
        return False

    try:
        switch_button.click(timeout=timeout_ms)
        print(f"{title}: 已普通点击可见 item 内“切换”按钮")
        return True
    except Exception as normal_exc:
        try:
            switch_button.click(timeout=timeout_ms, force=True)
            print(f"{title}: 已 force 点击可见 item 内“切换”按钮")
            return True
        except Exception as force_exc:
            try:
                item.evaluate(
                    """
                    (node) => {
                      const buttons = Array.from(node.querySelectorAll('button, a, span, div'));
                      const target = buttons.find((el) => (el.innerText || el.textContent || '').trim() === '切换');
                      if (!target) {
                        throw new Error('item 内没有可点击的切换元素');
                      }
                      target.click();
                    }
                    """
                )
                print(f"{title}: 已通过 DOM evaluate 点击 item 内“切换”按钮")
                return True
            except Exception as eval_exc:
                message = (
                    f"{title}: 点击“切换”失败。普通点击：{normal_exc}；"
                    f"force 点击：{force_exc}；DOM 点击：{eval_exc}"
                )
                if warnings is not None:
                    warnings.append(message)
                print(message)
                return False


def _wait_current_title(page: Any, title: str, timeout_ms: int) -> None:
    try:
        page.get_by_text(title, exact=True).first.wait_for(state="visible", timeout=timeout_ms)
    except Exception:
        page.wait_for_timeout(1500)


def _download_current_video(page: Any, title: str, output_dir: Path, timeout_ms: int) -> str:
    download_button = page.get_by_text("下载数据", exact=True)
    if download_button.count() == 0:
        download_button = page.locator("button:has-text('下载数据')")
    if download_button.count() == 0:
        raise RuntimeError(f"{title}: 未找到“下载数据”按钮。")

    print(f"{title}: 点击下载数据")
    with page.expect_download(timeout=timeout_ms) as download_info:
        _click_locator_with_force_fallback(download_button, timeout_ms)
    download = download_info.value
    output_dir.mkdir(parents=True, exist_ok=True)
    target_path = output_dir / build_download_filename(title)
    download.save_as(str(target_path))
    return str(target_path)


def sync_video_trends(
    *,
    url: str,
    include_pattern: str,
    limit: int | None,
    output_dir: str | Path,
    state_path: str | Path = DEFAULT_STATE_PATH,
    headless: bool = False,
    timeout_ms: int = 30000,
) -> VideoTrendSyncResult:
    result = VideoTrendSyncResult()
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
            result.warnings.append("页面 networkidle 等待超时，继续尝试读取视频列表。")

        _click_switch_video(page, timeout_ms)
        page.wait_for_timeout(1000)
        titles = filter_titles_by_pattern(collect_video_titles(page), include_pattern)
        if limit is not None and limit > 0:
            titles = titles[:limit]

        for title in titles:
            print(f"当前处理视频：{title}")
            try:
                _click_switch_video(page, timeout_ms)
                page.wait_for_timeout(500)
                if not _switch_to_video(page, title, timeout_ms, result.warnings):
                    continue
                _wait_current_title(page, title, timeout_ms)
                close_switch_drawer(page, result.warnings, timeout_ms=timeout_ms)
                downloaded = _download_current_video(page, title, output_path, timeout_ms)
                result.downloaded_files.append(downloaded)
            except Exception as exc:
                result.warnings.append(f"{title}: 下载失败，继续下一个。原因：{exc}")
            time.sleep(random.uniform(2, 5))

        browser.close()

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="批量下载腾讯视频创作平台视频趋势数据。")
    parser.add_argument("--url", default=DEFAULT_VIDEO_DATA_URL, help="腾讯视频后台视频数据页 URL")
    parser.add_argument("--include-pattern", default=DEFAULT_INCLUDE_PATTERN, help="需要下载的视频标题正则")
    parser.add_argument("--limit", type=int, default=None, help="只下载前 N 个，用于测试")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_DIR), help="下载输出目录")
    args = parser.parse_args()

    result = sync_video_trends(
        url=args.url,
        include_pattern=args.include_pattern,
        limit=args.limit,
        output_dir=args.output,
        headless=False,
    )

    print("腾讯视频视频趋势数据同步完成。")
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
