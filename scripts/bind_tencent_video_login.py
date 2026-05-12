from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from app.services.tencent_video_data import save_login_state
from app.services.tencent_video_data.sync_service import TENCENT_VIDEO_HOME_URL


def main() -> None:
    parser = argparse.ArgumentParser(description="绑定腾讯视频创作后台登录态。")
    parser.add_argument(
        "--state",
        default=str(PROJECT_ROOT / "data" / "tencent_video_auth" / "state.json"),
        help="Playwright storage_state 保存路径",
    )
    parser.add_argument(
        "--login-url",
        default=TENCENT_VIDEO_HOME_URL,
        help="腾讯视频创作后台登录入口",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="无头模式。首次登录通常不要开启。",
    )
    args = parser.parse_args()

    state_path = save_login_state(
        state_path=args.state,
        login_url=args.login_url,
        headless=args.headless,
    )
    print(f"腾讯视频登录态已保存：{state_path}")
    print("请不要把 data/tencent_video_auth/state.json 提交到 Git。")


if __name__ == "__main__":
    main()
