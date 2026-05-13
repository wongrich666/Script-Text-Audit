from __future__ import annotations

import unittest
import tempfile
from datetime import datetime
from pathlib import Path

from scripts.sync_tencent_video_video_trends import (
    VideoTrendSyncResult,
    build_download_filename,
    close_switch_drawer,
    dedupe_titles,
    find_video_item_in_drawer,
    filter_titles_by_pattern,
    find_visible_download_button,
    _download_current_video,
    _click_switch_video,
    _switch_to_video,
    sanitize_filename,
)


class FakeDrawerItem:
    def __init__(self, text: str, visible: bool, has_button: bool = True) -> None:
        self.text = text
        self.visible = visible
        self.has_button = has_button
        self.clicked = False

    def is_visible(self, timeout: int = 0) -> bool:
        return self.visible

    def get_by_text(self, *args: object, **kwargs: object) -> "FakeButtonLocator":
        return FakeButtonLocator(self)

    def locator(self, selector: str) -> "FakeButtonLocator":
        return FakeButtonLocator(self)

    def scroll_into_view_if_needed(self, timeout: int = 0) -> None:
        return None

    def evaluate(self, script: str) -> None:
        if not self.has_button:
            raise RuntimeError("no button")
        self.clicked = True


class FakeButton:
    def __init__(self, item: FakeDrawerItem) -> None:
        self.item = item

    def is_visible(self, timeout: int = 0) -> bool:
        return self.item.visible and self.item.has_button

    def click(self, *args: object, **kwargs: object) -> None:
        if not self.is_visible():
            raise RuntimeError("button hidden")
        self.item.clicked = True


class FakeButtonLocator:
    def __init__(self, item: FakeDrawerItem) -> None:
        self.item = item

    def count(self) -> int:
        return 1 if self.item.has_button else 0

    def nth(self, index: int) -> FakeButton:
        return FakeButton(self.item)


class FakeItemLocator:
    def __init__(self, items: list[FakeDrawerItem]) -> None:
        self.items = items

    def filter(self, has_text: str) -> "FakeItemLocator":
        return FakeItemLocator([item for item in self.items if has_text in item.text])

    def count(self) -> int:
        return len(self.items)

    def nth(self, index: int) -> FakeDrawerItem:
        return self.items[index]


class FakeDrawer:
    def __init__(self, items: list[FakeDrawerItem]) -> None:
        self.items = items

    def is_visible(self, timeout: int = 0) -> bool:
        return True

    def locator(self, selector: str) -> FakeItemLocator:
        return FakeItemLocator(self.items)


class FakeDrawerLocator:
    def __init__(self, drawer: FakeDrawer | None) -> None:
        self.drawer = drawer

    def count(self) -> int:
        return 1 if self.drawer is not None else 0

    def nth(self, index: int) -> FakeDrawer:
        if self.drawer is None:
            raise IndexError(index)
        return self.drawer


class FakeDrawerPage:
    def __init__(self, items: list[FakeDrawerItem]) -> None:
        self.drawer = FakeDrawer(items)

    def locator(self, selector: str) -> FakeDrawerLocator:
        if "drawer" in selector:
            return FakeDrawerLocator(self.drawer)
        return FakeDrawerLocator(None)


class TencentVideoVideoTrendsSyncTests(unittest.TestCase):
    def test_sanitize_filename(self) -> None:
        self.assertEqual(sanitize_filename(" SJS_17 "), "SJS_17")
        self.assertEqual(sanitize_filename("小医奴03:/?*"), "小医奴03")
        self.assertEqual(sanitize_filename(""), "untitled")

    def test_filter_titles_by_pattern(self) -> None:
        titles = ["SJS_17", "SJS_abc", "小医奴03", "SJS_18"]

        self.assertEqual(filter_titles_by_pattern(titles, r"^SJS_\d+$"), ["SJS_17", "SJS_18"])
        self.assertEqual(filter_titles_by_pattern(titles, r"小医奴\d+"), ["小医奴03"])

    def test_dedupe_titles(self) -> None:
        self.assertEqual(
            dedupe_titles(["SJS_17", "SJS_17", "", " 小医奴03 ", "小医奴03"]),
            ["SJS_17", "小医奴03"],
        )

    def test_build_download_filename(self) -> None:
        filename = build_download_filename("SJS_17", datetime(2026, 5, 13, 10, 45, 0))

        self.assertEqual(filename, "视频趋势数据-SJS_17-20260513-104500.xlsx")

    def test_close_switch_drawer_does_not_raise(self) -> None:
        class FakeKeyboard:
            def __init__(self, page: "FakePage") -> None:
                self.page = page

            def press(self, key: str) -> None:
                self.page.drawer_open = False

        class FakeLocator:
            def __init__(self, page: "FakePage", selector: str) -> None:
                self.page = page
                self.selector = selector
                self.first = self

            def count(self) -> int:
                return 1 if self.page.drawer_open and "drawer" in self.selector else 0

            def wait_for(self, state: str, timeout: int) -> None:
                if self.page.drawer_open:
                    raise TimeoutError("drawer still open")

            def click(self, *args: object, **kwargs: object) -> None:
                self.page.drawer_open = False

        class FakePage:
            def __init__(self) -> None:
                self.drawer_open = True
                self.keyboard = FakeKeyboard(self)

            def locator(self, selector: str) -> FakeLocator:
                return FakeLocator(self, selector)

            def wait_for_timeout(self, timeout: int) -> None:
                return None

        warnings: list[str] = []
        page = FakePage()

        self.assertTrue(close_switch_drawer(page, warnings, timeout_ms=100))
        self.assertFalse(page.drawer_open)
        self.assertEqual(warnings, [])

    def test_click_switch_video_reuses_open_drawer(self) -> None:
        class FakeLocator:
            def __init__(self, count: int = 0) -> None:
                self._count = count
                self.first = self
                self.clicked = False

            def count(self) -> int:
                return self._count

            def click(self, *args: object, **kwargs: object) -> None:
                self.clicked = True

        class FakePage:
            def __init__(self) -> None:
                self.button_locator = FakeLocator(1)

            def locator(self, selector: str) -> FakeLocator:
                if "drawer-open" in selector:
                    return FakeLocator(1)
                return FakeLocator(0)

            def get_by_role(self, *args: object, **kwargs: object) -> FakeLocator:
                return self.button_locator

            def get_by_text(self, *args: object, **kwargs: object) -> FakeLocator:
                return self.button_locator

        page = FakePage()

        _click_switch_video(page, timeout_ms=100)

        self.assertFalse(page.button_locator.clicked)

    def test_result_structure_contains_downloads_and_warnings(self) -> None:
        result = VideoTrendSyncResult(downloaded_files=["a.xlsx"], warnings=["warning"])

        self.assertEqual(result.downloads, ["a.xlsx"])
        self.assertEqual(result.downloaded_files, ["a.xlsx"])
        self.assertEqual(result.warnings, ["warning"])

    def test_duplicate_title_selects_visible_item(self) -> None:
        hidden = FakeDrawerItem("SJS_27", visible=False, has_button=True)
        visible = FakeDrawerItem("SJS_27", visible=True, has_button=True)
        page = FakeDrawerPage([hidden, visible])

        item = find_video_item_in_drawer(page, "SJS_27")

        self.assertIs(item, visible)

    def test_hidden_item_is_not_clicked(self) -> None:
        hidden = FakeDrawerItem("SJS_25", visible=False, has_button=True)
        visible = FakeDrawerItem("SJS_25", visible=True, has_button=True)
        page = FakeDrawerPage([hidden, visible])
        warnings: list[str] = []

        switched = _switch_to_video(page, "SJS_25", timeout_ms=100, warnings=warnings)

        self.assertTrue(switched)
        self.assertFalse(hidden.clicked)
        self.assertTrue(visible.clicked)
        self.assertEqual(warnings, [])

    def test_missing_visible_switch_button_returns_warning(self) -> None:
        item = FakeDrawerItem("SJS_30", visible=True, has_button=False)
        page = FakeDrawerPage([item])
        warnings: list[str] = []

        switched = _switch_to_video(page, "SJS_30", timeout_ms=100, warnings=warnings)

        self.assertFalse(switched)
        self.assertFalse(item.clicked)
        self.assertTrue(any("未找到“切换”按钮" in warning for warning in warnings))

    def test_visible_download_button_is_selected_and_hidden_not_clicked(self) -> None:
        class FakeDownloadButton:
            def __init__(self, visible: bool) -> None:
                self.visible = visible
                self.clicked = False

            def is_visible(self, timeout: int = 0) -> bool:
                return self.visible

            def scroll_into_view_if_needed(self, timeout: int = 0) -> None:
                return None

            def click(self, *args: object, **kwargs: object) -> None:
                if not self.visible:
                    raise RuntimeError("hidden")
                self.clicked = True

            def evaluate(self, script: str) -> None:
                self.clicked = True

        class FakeDownloadLocator:
            def __init__(self, buttons: list[FakeDownloadButton]) -> None:
                self.buttons = buttons

            def count(self) -> int:
                return len(self.buttons)

            def nth(self, index: int) -> FakeDownloadButton:
                return self.buttons[index]

        class FakeScope:
            def __init__(self, buttons: list[FakeDownloadButton]) -> None:
                self.buttons = buttons

            def is_visible(self, timeout: int = 0) -> bool:
                return True

            def get_by_text(self, *args: object, **kwargs: object) -> FakeDownloadLocator:
                return FakeDownloadLocator(self.buttons)

            def locator(self, selector: str) -> FakeDownloadLocator:
                return FakeDownloadLocator(self.buttons)

            def scroll_into_view_if_needed(self, timeout: int = 0) -> None:
                return None

            def wait_for_timeout(self, timeout: int) -> None:
                return None

        class FakeScopeLocator:
            def __init__(self, scopes: list[FakeScope]) -> None:
                self.scopes = scopes

            def filter(self, has_text: str) -> "FakeScopeLocator":
                return self

            def count(self) -> int:
                return len(self.scopes)

            def nth(self, index: int) -> FakeScope:
                return self.scopes[index]

        class FakePage:
            def __init__(self) -> None:
                self.hidden = FakeDownloadButton(False)
                self.visible = FakeDownloadButton(True)
                self.buttons = [self.hidden, self.visible]
                self.scope = FakeScope(self.buttons)
                self.mouse = type("Mouse", (), {"wheel": lambda _self, x, y: None})()

            def locator(self, selector: str) -> FakeScopeLocator | FakeDownloadLocator:
                if "drawer" in selector:
                    return FakeScopeLocator([])
                return FakeScopeLocator([self.scope])

            def get_by_text(self, *args: object, **kwargs: object) -> FakeDownloadLocator:
                return FakeDownloadLocator(self.buttons)

            def wait_for_timeout(self, timeout: int) -> None:
                return None

        page = FakePage()

        button = find_visible_download_button(page, "SJS_17")
        button.click()

        self.assertFalse(page.hidden.clicked)
        self.assertTrue(page.visible.clicked)

    def test_video_download_success_path_is_correct(self) -> None:
        class FakeDownloadButton:
            def __init__(self) -> None:
                self.clicked = False

            def is_visible(self, timeout: int = 0) -> bool:
                return True

            def scroll_into_view_if_needed(self, timeout: int = 0) -> None:
                return None

            def click(self, *args: object, **kwargs: object) -> None:
                self.clicked = True

            def evaluate(self, script: str) -> None:
                self.clicked = True

        class FakeDownloadLocator:
            def __init__(self, button: FakeDownloadButton | None) -> None:
                self.button = button

            def count(self) -> int:
                return 1 if self.button is not None else 0

            def nth(self, index: int) -> FakeDownloadButton:
                if self.button is None:
                    raise IndexError(index)
                return self.button

        class FakeScope:
            def __init__(self, button: FakeDownloadButton) -> None:
                self.button = button

            def is_visible(self, timeout: int = 0) -> bool:
                return True

            def get_by_text(self, *args: object, **kwargs: object) -> FakeDownloadLocator:
                return FakeDownloadLocator(self.button)

            def locator(self, selector: str) -> FakeDownloadLocator:
                return FakeDownloadLocator(self.button)

            def scroll_into_view_if_needed(self, timeout: int = 0) -> None:
                return None

            def wait_for_timeout(self, timeout: int) -> None:
                return None

        class FakeScopeLocator:
            def __init__(self, scopes: list[FakeScope]) -> None:
                self.scopes = scopes

            def filter(self, has_text: str) -> "FakeScopeLocator":
                return self

            def count(self) -> int:
                return len(self.scopes)

            def nth(self, index: int) -> FakeScope:
                return self.scopes[index]

        class FakeDownload:
            def save_as(self, path: str) -> None:
                Path(path).write_text("fake xlsx", encoding="utf-8")

        class FakeDownloadInfo:
            value = FakeDownload()

        class FakeDownloadContext:
            def __enter__(self) -> FakeDownloadInfo:
                return FakeDownloadInfo()

            def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
                return False

        class FakePage:
            def __init__(self) -> None:
                self.button = FakeDownloadButton()
                self.scope = FakeScope(self.button)
                self.mouse = type("Mouse", (), {"wheel": lambda _self, x, y: None})()

            def locator(self, selector: str) -> FakeScopeLocator | FakeDownloadLocator:
                if "drawer" in selector:
                    return FakeScopeLocator([])
                return FakeScopeLocator([self.scope])

            def get_by_text(self, *args: object, **kwargs: object) -> FakeDownloadLocator:
                return FakeDownloadLocator(self.button)

            def wait_for_timeout(self, timeout: int) -> None:
                return None

            def expect_download(self, timeout: int = 0) -> FakeDownloadContext:
                return FakeDownloadContext()

        with tempfile.TemporaryDirectory() as temp_dir:
            path = _download_current_video(FakePage(), "SJS_17", Path(temp_dir), timeout_ms=100)

            self.assertTrue(Path(path).exists())
            self.assertIn("视频趋势数据-SJS_17-", Path(path).name)


if __name__ == "__main__":
    unittest.main()
