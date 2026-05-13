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
    get_current_video_title,
    verify_current_video_title,
    _download_current_video,
    _click_switch_video,
    _switch_to_video,
    sanitize_filename,
)


class FakeDrawerItem:
    def __init__(
        self,
        text: str,
        visible: bool,
        has_button: bool = True,
        *,
        button_visible: bool = True,
        reveal_button_on_hover: bool = False,
        current: bool = False,
    ) -> None:
        self.text = text
        self.visible = visible
        self.has_button = has_button
        self.button_visible = button_visible
        self.reveal_button_on_hover = reveal_button_on_hover
        self.current = current
        self.clicked = False
        self.hovered = False

    def is_visible(self, timeout: int = 0) -> bool:
        return self.visible

    def get_by_text(self, *args: object, **kwargs: object) -> "FakeButtonLocator":
        return FakeButtonLocator(self)

    def locator(self, selector: str) -> "FakeButtonLocator":
        return FakeButtonLocator(self)

    def scroll_into_view_if_needed(self, timeout: int = 0) -> None:
        return None

    def hover(self, timeout: int = 0) -> None:
        self.hovered = True

    def click(self, *args: object, **kwargs: object) -> None:
        self.clicked = True

    def inner_text(self, timeout: int = 0) -> str:
        suffix = " 当前" if self.current else ""
        return f"{self.text}{suffix}"

    def evaluate(self, script: str) -> str | None:
        if "querySelectorAll" in script:
            if not self.has_button:
                raise RuntimeError("no button")
            self.clicked = True
            return None
        if "node.click()" in script:
            self.clicked = True
            return None
        if "innerText" in script or "textContent" in script:
            return self.inner_text()
        return self.inner_text()


class FakeButton:
    def __init__(self, item: FakeDrawerItem) -> None:
        self.item = item

    def is_visible(self, timeout: int = 0) -> bool:
        button_visible = self.item.button_visible or (self.item.reveal_button_on_hover and self.item.hovered)
        return self.item.visible and self.item.has_button and button_visible

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

    def wait_for_timeout(self, timeout: int) -> None:
        return None


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

    def test_target_item_without_switch_button_clicks_item_itself(self) -> None:
        item = FakeDrawerItem("SJS_30", visible=True, has_button=False)
        page = FakeDrawerPage([item])
        warnings: list[str] = []

        switched = _switch_to_video(page, "SJS_30", timeout_ms=100, warnings=warnings)

        self.assertTrue(switched)
        self.assertTrue(item.clicked)
        self.assertEqual(warnings, [])

    def test_current_item_without_switch_button_is_success(self) -> None:
        item = FakeDrawerItem("SJS_30", visible=True, has_button=False, current=True)
        page = FakeDrawerPage([item])
        warnings: list[str] = []

        switched = _switch_to_video(page, "SJS_30", timeout_ms=100, warnings=warnings)

        self.assertTrue(switched)
        self.assertFalse(item.clicked)
        self.assertEqual(warnings, [])

    def test_target_item_switch_button_visible_after_hover_is_clicked(self) -> None:
        item = FakeDrawerItem("SJS_27", visible=True, has_button=True, button_visible=False, reveal_button_on_hover=True)
        page = FakeDrawerPage([item])
        warnings: list[str] = []

        switched = _switch_to_video(page, "SJS_27", timeout_ms=100, warnings=warnings)

        self.assertTrue(switched)
        self.assertTrue(item.hovered)
        self.assertTrue(item.clicked)
        self.assertEqual(warnings, [])

    def test_target_item_hidden_switch_button_uses_dom_evaluate(self) -> None:
        item = FakeDrawerItem("SJS_27", visible=True, has_button=True, button_visible=False)
        page = FakeDrawerPage([item])
        warnings: list[str] = []

        switched = _switch_to_video(page, "SJS_27", timeout_ms=100, warnings=warnings)

        self.assertTrue(switched)
        self.assertTrue(item.hovered)
        self.assertTrue(item.clicked)
        self.assertEqual(warnings, [])

    def test_missing_target_video_item_does_not_click_first_visible_item(self) -> None:
        first = FakeDrawerItem("SJS_01", visible=True, has_button=True)
        page = FakeDrawerPage([first])
        warnings: list[str] = []

        switched = _switch_to_video(page, "SJS_99", timeout_ms=100, warnings=warnings)

        self.assertFalse(switched)
        self.assertFalse(first.clicked)
        self.assertTrue(any("未找到包含目标 title" in warning for warning in warnings))

    def test_download_button_can_be_found_in_page_detail_module(self) -> None:
        class FakeDownloadButton:
            def __init__(self, visible: bool) -> None:
                self.visible = visible

            def is_visible(self, timeout: int = 0) -> bool:
                return self.visible

            def evaluate(self, script: str) -> dict[str, str]:
                return {"className": "downloadButton___abc", "text": "下载数据"}

        class FakeDownloadLocator:
            def __init__(self, buttons: list[FakeDownloadButton]) -> None:
                self.buttons = buttons

            def filter(self, has_text: str) -> "FakeDownloadLocator":
                return self

            def count(self) -> int:
                return len(self.buttons)

            def nth(self, index: int) -> FakeDownloadButton:
                return self.buttons[index]

        class FakeScope:
            def __init__(self, buttons: list[FakeDownloadButton]) -> None:
                self.buttons = buttons

            def is_visible(self, timeout: int = 0) -> bool:
                return True

            def locator(self, selector: str) -> FakeDownloadLocator:
                return FakeDownloadLocator(self.buttons)

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
                self.button = FakeDownloadButton(True)
                self.scope = FakeScope([self.button])

            def locator(self, selector: str) -> FakeScopeLocator:
                if "detailModule" in selector:
                    return FakeScopeLocator([self.scope])
                return FakeScopeLocator([])

        page = FakePage()

        self.assertIs(find_visible_download_button(page, "SJS_17"), page.button)

    def test_hidden_page_download_button_is_not_selected(self) -> None:
        class FakeDownloadButton:
            def is_visible(self, timeout: int = 0) -> bool:
                return False

            def evaluate(self, script: str) -> dict[str, str]:
                return {"className": "downloadButton___abc", "text": "下载数据"}

        class FakeDownloadLocator:
            def __init__(self, buttons: list[FakeDownloadButton]) -> None:
                self.buttons = buttons

            def filter(self, has_text: str) -> "FakeDownloadLocator":
                return self

            def count(self) -> int:
                return len(self.buttons)

            def nth(self, index: int) -> FakeDownloadButton:
                return self.buttons[index]

        class FakeScope:
            def __init__(self) -> None:
                self.buttons = [FakeDownloadButton()]

            def locator(self, selector: str) -> FakeDownloadLocator:
                return FakeDownloadLocator(self.buttons)

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
                self.scope = FakeScope()

            def locator(self, selector: str) -> FakeScopeLocator:
                if "detailModule" in selector:
                    return FakeScopeLocator([self.scope])
                return FakeScopeLocator([])

        self.assertIsNone(find_visible_download_button(FakePage(), "SJS_17"))

    def test_current_title_mismatch_skips_download(self) -> None:
        class FakeTitleItem:
            def is_visible(self, timeout: int = 0) -> bool:
                return True

            def inner_text(self, timeout: int = 0) -> str:
                return "SJS_28"

        class FakeTitleLocator:
            first = None

            def __init__(self) -> None:
                self.first = self

            def count(self) -> int:
                return 1

            def nth(self, index: int) -> FakeTitleItem:
                return FakeTitleItem()

            def is_visible(self, timeout: int = 0) -> bool:
                return False

        class FakePage:
            def locator(self, selector: str) -> FakeTitleLocator:
                return FakeTitleLocator()

            def get_by_text(self, *args: object, **kwargs: object) -> FakeTitleLocator:
                return FakeTitleLocator()

        warnings: list[str] = []

        self.assertFalse(verify_current_video_title(FakePage(), "SJS_27", warnings))
        self.assertTrue(any("与目标不一致" in warning for warning in warnings))

    def test_current_title_ignores_duration_and_selects_video_title(self) -> None:
        class FakeTitleItem:
            def __init__(self, text: str) -> None:
                self.text = text

            def is_visible(self, timeout: int = 0) -> bool:
                return True

            def inner_text(self, timeout: int = 0) -> str:
                return self.text

        class FakeTitleLocator:
            def __init__(self, texts: list[str]) -> None:
                self.items = [FakeTitleItem(text) for text in texts]

            def filter(self, has_text: str) -> "FakeTitleLocator":
                return FakeTitleLocator([item.text for item in self.items if has_text in item.text])

            def count(self) -> int:
                return len(self.items)

            def nth(self, index: int) -> FakeTitleItem:
                return self.items[index]

        class FakePage:
            def locator(self, selector: str) -> FakeTitleLocator:
                return FakeTitleLocator(["00:56", "SJS_27"])

        self.assertEqual(get_current_video_title(FakePage()), "SJS_27")

    def test_current_title_returns_none_for_duration_only(self) -> None:
        class FakeTitleItem:
            def __init__(self, text: str) -> None:
                self.text = text

            def is_visible(self, timeout: int = 0) -> bool:
                return True

            def inner_text(self, timeout: int = 0) -> str:
                return self.text

        class FakeTitleLocator:
            def __init__(self, texts: list[str]) -> None:
                self.items = [FakeTitleItem(text) for text in texts]

            def filter(self, has_text: str) -> "FakeTitleLocator":
                return FakeTitleLocator([item.text for item in self.items if has_text in item.text])

            def count(self) -> int:
                return len(self.items)

            def nth(self, index: int) -> FakeTitleItem:
                return self.items[index]

        class FakePage:
            def locator(self, selector: str) -> FakeTitleLocator:
                return FakeTitleLocator(["00:56", "01:26", "1:02"])

        self.assertIsNone(get_current_video_title(FakePage()))

    def test_exact_title_span_visible_passes_verification(self) -> None:
        class FakeTitleItem:
            def __init__(self, text: str) -> None:
                self.text = text

            def is_visible(self, timeout: int = 0) -> bool:
                return True

            def inner_text(self, timeout: int = 0) -> str:
                return self.text

        class FakeTitleLocator:
            first = None

            def __init__(self, texts: list[str]) -> None:
                self.items = [FakeTitleItem(text) for text in texts]
                self.first = self

            def filter(self, has_text: str) -> "FakeTitleLocator":
                return FakeTitleLocator([item.text for item in self.items if has_text in item.text])

            def count(self) -> int:
                return len(self.items)

            def nth(self, index: int) -> FakeTitleItem:
                return self.items[index]

            def is_visible(self, timeout: int = 0) -> bool:
                return bool(self.items)

        class FakePage:
            def locator(self, selector: str) -> FakeTitleLocator:
                return FakeTitleLocator(["00:56", "SJS_27"])

            def wait_for_timeout(self, timeout: int) -> None:
                return None

            def get_by_text(self, *args: object, **kwargs: object) -> FakeTitleLocator:
                return FakeTitleLocator([])

        self.assertTrue(verify_current_video_title(FakePage(), "SJS_27", []))

    def test_exact_target_visible_passes_when_current_title_missing(self) -> None:
        class FakeTitleItem:
            def __init__(self, text: str, visible: bool = True) -> None:
                self.text = text
                self.visible = visible

            def is_visible(self, timeout: int = 0) -> bool:
                return self.visible

            def inner_text(self, timeout: int = 0) -> str:
                return self.text

        class FakeTitleLocator:
            first = None

            def __init__(self, items: list[FakeTitleItem]) -> None:
                self.items = items
                self.first = self

            def filter(self, has_text: str) -> "FakeTitleLocator":
                return FakeTitleLocator([item for item in self.items if has_text in item.text])

            def count(self) -> int:
                return len(self.items)

            def nth(self, index: int) -> FakeTitleItem:
                return self.items[index]

            def is_visible(self, timeout: int = 0) -> bool:
                return any(item.visible for item in self.items)

        class FakePage:
            def locator(self, selector: str) -> FakeTitleLocator:
                if selector == "span[class*='title']":
                    return FakeTitleLocator([FakeTitleItem("SJS_27", visible=True)])
                return FakeTitleLocator([])

            def wait_for_timeout(self, timeout: int) -> None:
                return None

            def get_by_text(self, *args: object, **kwargs: object) -> FakeTitleLocator:
                return FakeTitleLocator([])

        self.assertTrue(verify_current_video_title(FakePage(), "SJS_27", []))

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

            def evaluate(self, script: str) -> dict[str, str] | None:
                if "className" in script:
                    return {"className": "download-btn", "text": "下载数据"}
                self.clicked = True
                return None

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

            def evaluate(self, script: str) -> dict[str, str] | None:
                if "className" in script:
                    return {"className": "download-btn", "text": "下载数据"}
                self.clicked = True
                return None

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
