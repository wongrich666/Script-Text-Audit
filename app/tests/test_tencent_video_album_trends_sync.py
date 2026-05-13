from __future__ import annotations

import unittest
import tempfile
from datetime import datetime
from pathlib import Path

from scripts.sync_tencent_video_album_trends import (
    AlbumTrendSyncResult,
    build_download_filename,
    dedupe_titles,
    filter_titles_by_pattern,
    find_visible_download_button,
    _download_album_data,
    sanitize_filename,
)


class TencentVideoAlbumTrendsSyncTests(unittest.TestCase):
    def test_sanitize_filename(self) -> None:
        self.assertEqual(sanitize_filename(" 冥府审判师 "), "冥府审判师")
        self.assertEqual(sanitize_filename("什么，隔壁邻居竟是我偶像:/?*"), "什么，隔壁邻居竟是我偶像")
        self.assertEqual(sanitize_filename(""), "untitled")

    def test_filter_titles_by_pattern(self) -> None:
        titles = ["冥府审判师", "小医奴", "开局血条负一百"]

        self.assertEqual(filter_titles_by_pattern(titles, r"冥府审判师|小医奴"), ["冥府审判师", "小医奴"])
        self.assertEqual(filter_titles_by_pattern(titles, r".*"), titles)

    def test_dedupe_titles(self) -> None:
        self.assertEqual(
            dedupe_titles(["冥府审判师", "冥府审判师", "", " 小医奴 ", "小医奴"]),
            ["冥府审判师", "小医奴"],
        )

    def test_build_download_filename(self) -> None:
        filename = build_download_filename("冥府审判师", datetime(2026, 5, 13, 11, 30, 0))

        self.assertEqual(filename, "专辑数据-冥府审判师-20260513-113000.xlsx")

    def test_result_structure(self) -> None:
        result = AlbumTrendSyncResult(downloaded_files=["a.xlsx"], warnings=["warning"])

        self.assertEqual(result.downloads, ["a.xlsx"])
        self.assertEqual(result.downloaded_files, ["a.xlsx"])
        self.assertEqual(result.warnings, ["warning"])

    def test_visible_download_button_is_selected_and_hidden_not_clicked(self) -> None:
        class FakeDownloadButton:
            def __init__(self, visible: bool) -> None:
                self.visible = visible
                self.clicked = False

            def is_visible(self, timeout: int = 0) -> bool:
                return self.visible

            def click(self, *args: object, **kwargs: object) -> None:
                if not self.visible:
                    raise RuntimeError("hidden")
                self.clicked = True

            def scroll_into_view_if_needed(self, timeout: int = 0) -> None:
                return None

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
        button = find_visible_download_button(page, "冥府审判师")
        button.click()

        self.assertFalse(page.hidden.clicked)
        self.assertTrue(page.visible.clicked)

    def test_album_download_success_path_is_correct(self) -> None:
        class FakeDownloadButton:
            def is_visible(self, timeout: int = 0) -> bool:
                return True

            def click(self, *args: object, **kwargs: object) -> None:
                return None

            def scroll_into_view_if_needed(self, timeout: int = 0) -> None:
                return None

            def evaluate(self, script: str) -> dict[str, str] | None:
                if "className" in script:
                    return {"className": "download-btn", "text": "下载数据"}
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

        class FakePage:
            def __init__(self) -> None:
                self.button = FakeDownloadButton()
                self.scope = FakeScope(self.button)
                self.download_handler = None
                self.mouse = type("Mouse", (), {"wheel": lambda _self, x, y: None})()

            def locator(self, selector: str) -> FakeScopeLocator | FakeDownloadLocator:
                if "drawer" in selector:
                    return FakeScopeLocator([])
                return FakeScopeLocator([self.scope])

            def get_by_text(self, *args: object, **kwargs: object) -> FakeDownloadLocator:
                return FakeDownloadLocator(self.button)

            def on(self, event: str, handler: object) -> None:
                self.download_handler = handler

            def wait_for_timeout(self, timeout: int) -> None:
                if self.download_handler is not None:
                    self.download_handler(FakeDownload())

        with tempfile.TemporaryDirectory() as temp_dir:
            paths = _download_album_data(FakePage(), "冥府审判师", Path(temp_dir), timeout_ms=100)

            self.assertEqual(len(paths), 1)
            self.assertTrue(Path(paths[0]).exists())
            self.assertIn("专辑数据-冥府审判师-", Path(paths[0]).name)


if __name__ == "__main__":
    unittest.main()
