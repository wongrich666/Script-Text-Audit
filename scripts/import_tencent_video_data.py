from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from app.services.tencent_video_data import (
    generate_market_feedback_summary,
    import_tencent_video_exports,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="导入腾讯视频创作后台导出的 Excel 数据。")
    parser.add_argument(
        "--input",
        default="data/tencent_video_exports",
        help="腾讯视频后台下载的 .xlsx 文件目录",
    )
    parser.add_argument(
        "--output",
        default="data/tencent_video_normalized",
        help="标准化 CSV / JSON 输出目录",
    )
    args = parser.parse_args()

    import_result = import_tencent_video_exports(args.input, args.output)
    analysis_result = generate_market_feedback_summary(args.output)

    warnings = import_result.warnings + analysis_result.warnings
    generated_files = import_result.generated_files + analysis_result.generated_files

    print("腾讯视频平台数据导入完成。")
    print("")
    print("读取的 Excel：")
    if import_result.read_excels:
        for path in import_result.read_excels:
            print(f"- {path}")
    else:
        print("- 无")

    print("")
    print("生成的 CSV/JSON：")
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
