from __future__ import annotations

from pathlib import Path


def sync_tencent_video_exports(*, output_dir: str | Path = "data/tencent_video_exports") -> None:
    """
    Phase 2 placeholder for Tencent Video creator backend sync.

    TODO:
    用户点击同步按钮 -> Playwright 打开腾讯后台 -> 点击下载数据 -> 保存 Excel ->
    调用 importer/analyzer 生成标准化 CSV 和 market_feedback_summary.json。
    """

    raise NotImplementedError("腾讯视频自动登录和自动下载将在第二阶段通过 Playwright 实现。")
