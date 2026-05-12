from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


TENCENT_VIDEO_HOME_URL = "https://mp.v.qq.com/"
DEFAULT_DATA_PAGE_URL = "https://mp.v.qq.com/datacenter/fans"
DEFAULT_AUTH_STATE_PATH = Path("data/tencent_video_auth/state.json")
DEFAULT_EXPORT_DIR = Path("data/tencent_video_exports")


@dataclass
class TencentVideoSyncResult:
    downloaded_files: list[str] = field(default_factory=list)
    snapshot_files: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _import_sync_playwright() -> Any:
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright 未安装。请先运行：pip install playwright && python -m playwright install chromium"
        ) from exc
    return sync_playwright, PlaywrightTimeoutError


def save_login_state(
    *,
    state_path: str | Path = DEFAULT_AUTH_STATE_PATH,
    login_url: str = TENCENT_VIDEO_HOME_URL,
    headless: bool = False,
) -> Path:
    sync_playwright, _ = _import_sync_playwright()
    state_file = Path(state_path)
    state_file.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()
        page.goto(login_url, wait_until="domcontentloaded")
        input("请在打开的浏览器中完成腾讯视频创作后台登录，登录完成后回到终端按 Enter 保存登录态...")
        context.storage_state(path=str(state_file))
        browser.close()

    return state_file


def _safe_count(locator: Any) -> int:
    try:
        return int(locator.count())
    except Exception:
        return 0


def _find_download_locator(page: Any) -> Any | None:
    candidates = [
        lambda: page.get_by_role("button", name="下载数据"),
        lambda: page.get_by_text("下载数据", exact=True),
        lambda: page.locator("text=下载数据"),
        lambda: page.locator("button:has-text('下载')"),
        lambda: page.locator("a:has-text('下载')"),
    ]

    for get_locator in candidates:
        try:
            locator = get_locator()
        except Exception:
            continue
        if _safe_count(locator) > 0:
            return locator.first()
    return None


def _save_body_snapshot(page: Any, snapshot_path: Path, warnings: list[str]) -> None:
    try:
        body_text = page.locator("body").inner_text(timeout=5000)
    except Exception as exc:
        body_text = f"无法读取页面正文：{exc}"
        warnings.append(f"未找到下载按钮，且读取页面正文失败：{exc}")

    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(body_text, encoding="utf-8")


def _suggested_download_filename(download: Any, fallback_prefix: str = "tencent_video_export") -> str:
    try:
        name = str(download.suggested_filename or "").strip()
    except Exception:
        name = ""
    if name:
        return name
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{fallback_prefix}_{stamp}.xlsx"


def _download_or_snapshot(page: Any, output_dir: Path, result: TencentVideoSyncResult, timeout_ms: int) -> None:
    download_locator = _find_download_locator(page)
    snapshot_path = output_dir / "fans_snapshot.txt"

    if download_locator is None:
        _save_body_snapshot(page, snapshot_path, result.warnings)
        result.snapshot_files.append(str(snapshot_path))
        result.warnings.append("fans 页面未找到“下载数据”按钮，已保存页面正文快照。")
        return

    try:
        with page.expect_download(timeout=timeout_ms) as download_info:
            download_locator.click()
        download = download_info.value
    except Exception as exc:
        _save_body_snapshot(page, snapshot_path, result.warnings)
        result.snapshot_files.append(str(snapshot_path))
        result.warnings.append(f"点击“下载数据”后未获得下载文件，已保存页面正文快照。原因：{exc}")
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    target_path = output_dir / _suggested_download_filename(download)
    download.save_as(str(target_path))
    result.downloaded_files.append(str(target_path))


def sync_tencent_video_exports(
    *,
    auth_state_path: str | Path = DEFAULT_AUTH_STATE_PATH,
    output_dir: str | Path = DEFAULT_EXPORT_DIR,
    data_url: str = DEFAULT_DATA_PAGE_URL,
    headless: bool = False,
    timeout_ms: int = 30000,
) -> TencentVideoSyncResult:
    """
    Optional Playwright downloader for Tencent Video creator data.

    This tool reuses a user-saved storage_state. It does not bypass captcha,
    does not crack signatures, and does not hard-code cookies.
    """

    result = TencentVideoSyncResult()
    state_file = Path(auth_state_path)
    export_dir = Path(output_dir)
    export_dir.mkdir(parents=True, exist_ok=True)

    if not state_file.exists():
        result.warnings.append(f"登录态不存在：{state_file}。请先运行 scripts/bind_tencent_video_login.py。")
        return result

    try:
        sync_playwright, _ = _import_sync_playwright()
    except RuntimeError as exc:
        result.warnings.append(str(exc))
        return result

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        context = browser.new_context(
            storage_state=str(state_file),
            accept_downloads=True,
        )
        page = context.new_page()
        page.goto(data_url, wait_until="domcontentloaded", timeout=timeout_ms)
        try:
            page.wait_for_load_state("networkidle", timeout=timeout_ms)
        except Exception:
            result.warnings.append("页面 networkidle 等待超时，继续尝试查找下载按钮。")
        _download_or_snapshot(page, export_dir, result, timeout_ms)
        browser.close()

    return result
