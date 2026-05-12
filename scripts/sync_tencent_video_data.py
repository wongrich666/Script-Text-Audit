from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from app.services.tencent_video_data import (
    align_episode_scripts,
    build_episode_samples,
    build_episode_text_features,
    generate_market_feedback_summary,
    import_tencent_video_exports,
    sync_tencent_video_exports,
)
from app.services.tencent_video_data.sync_service import DEFAULT_DATA_PAGE_URL


def main() -> None:
    parser = argparse.ArgumentParser(description="自动同步腾讯视频数据并生成标准化分析结果。")
    parser.add_argument(
        "--state",
        default=str(PROJECT_ROOT / "data" / "tencent_video_auth" / "state.json"),
        help="Playwright storage_state 路径",
    )
    parser.add_argument(
        "--exports",
        default=str(PROJECT_ROOT / "data" / "tencent_video_exports"),
        help="腾讯视频 Excel 下载目录",
    )
    parser.add_argument(
        "--output",
        default=str(PROJECT_ROOT / "data" / "tencent_video_normalized"),
        help="标准化 CSV / JSON 输出目录",
    )
    parser.add_argument(
        "--data-url",
        default=DEFAULT_DATA_PAGE_URL,
        help="腾讯视频后台数据页 URL",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="无头模式。需要验证码或重新登录时建议关闭。",
    )
    args = parser.parse_args()

    sync_result = sync_tencent_video_exports(
        auth_state_path=args.state,
        output_dir=args.exports,
        data_url=args.data_url,
        headless=args.headless,
    )
    import_result = import_tencent_video_exports(args.exports, args.output)
    analysis_result = generate_market_feedback_summary(args.output)
    sample_result = build_episode_samples(args.output)
    script_align_result = align_episode_scripts(
        args.output,
        PROJECT_ROOT / "data" / "episode_scripts",
    )
    text_feature_result = build_episode_text_features(args.output)

    generated_files = (
        sync_result.downloaded_files
        + sync_result.snapshot_files
        + import_result.generated_files
        + analysis_result.generated_files
        + sample_result.generated_files
        + script_align_result.updated_files
        + text_feature_result.generated_files
    )
    warnings = (
        sync_result.warnings
        + import_result.warnings
        + analysis_result.warnings
        + sample_result.warnings
        + script_align_result.warnings
        + text_feature_result.warnings
    )

    print("腾讯视频平台数据同步完成。")
    print("")
    print("下载的文件：")
    if sync_result.downloaded_files:
        for path in sync_result.downloaded_files:
            print(f"- {path}")
    else:
        print("- 无")

    print("")
    print("生成/更新的文件：")
    if generated_files:
        for path in generated_files:
            print(f"- {path}")
    else:
        print("- 无")

    print("")
    print("Warnings：")
    if warnings:
        for warning in warnings:
            print(f"- {warning}")
    else:
        print("- 无")


if __name__ == "__main__":
    main()
