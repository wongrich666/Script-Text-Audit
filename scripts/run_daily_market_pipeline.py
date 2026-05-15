from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


def now_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def run_step(name: str, cmd: list[str], required: bool = True) -> dict[str, Any]:
    print("")
    print("=" * 80)
    print(f"[pipeline] {name}")
    print("[pipeline] " + " ".join(cmd))
    print("=" * 80)

    result = subprocess.run(cmd, text=True)

    info = {
        "name": name,
        "cmd": cmd,
        "returncode": result.returncode,
        "required": required,
        "ok": result.returncode == 0,
    }

    if required and result.returncode != 0:
        raise RuntimeError(f"步骤失败：{name} returncode={result.returncode}")

    return info


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default="latest", help="剧查查图片处理日期：latest/all/today/yesterday/YYYY-MM-DD")
    parser.add_argument("--include-existing-juchacha", action="store_true", help="强制重跑已存在于正式表的剧查查图片")
    parser.add_argument(
        "--juchacha-finalize-policy",
        default="warning_ok",
        choices=["manual", "clean_only", "warning_ok"],
        help="manual=不自动 finalize；clean_only=无 error 且无 warning 才 finalize；warning_ok=无 error 即 finalize",
    )
    parser.add_argument("--skip-kuaishou", action="store_true")
    parser.add_argument("--skip-juchacha", action="store_true")
    parser.add_argument("--skip-tests", action="store_true")
    args = parser.parse_args()

    batch_id = now_id()
    python = sys.executable
    steps: list[dict[str, Any]] = []

    status_path = Path(f"data/pipeline_status/daily_status_{batch_id}.json")
    latest_status_path = Path("data/pipeline_status/daily_status_latest.json")

    juchacha_import_summary: dict[str, Any] = {}
    juchacha_quality_summary: dict[str, Any] = {}

    try:
        if not args.skip_kuaishou:
            steps.append(
                run_step(
                    "导入快手 normalized 数据",
                    [
                        python,
                        "scripts/import_kuaishou_data.py",
                        "--input",
                        "data/kuaishou_exports/raw",
                        "--episode-scripts",
                        "data/kuaishou_episode_scripts_canonical",
                        "--output",
                        "data/kuaishou_normalized",
                    ],
                )
            )

        steps.append(run_step("生成腾讯建模单集数据集", [python, "scripts/build_modeling_episode_dataset.py"]))

        steps.append(
            run_step(
                "生成跨平台统一数据层",
                [
                    python,
                    "scripts/build_platform_market_normalized.py",
                    "--tencent",
                    "data/tencent_video_normalized",
                    "--kuaishou",
                    "data/kuaishou_normalized",
                    "--output",
                    "data/platform_market_normalized",
                ],
            )
        )

        steps.append(
            run_step(
                "生成基础市场反馈报告",
                [python, "scripts/build_market_feedback_report.py", "--input", "data/platform_market_normalized"],
            )
        )

        if not args.skip_juchacha:
            juchacha_cmd = [
                python,
                "scripts/import_juchacha_ranking_images.py",
                "--input",
                "data/external_benchmark/juchacha_images/raw",
                "--output",
                "data/external_benchmark/juchacha_normalized",
                "--raw-output",
                "data/external_benchmark/juchacha_raw_ocr",
                "--date",
                args.date,
            ]

            if args.include_existing_juchacha:
                juchacha_cmd.append("--include-existing")

            steps.append(run_step("导入剧查查日榜图片 OCR 草稿", juchacha_cmd))

            juchacha_import_summary = read_json(
                Path("data/external_benchmark/juchacha_normalized/juchacha_import_summary.json")
            )
            image_count = int(juchacha_import_summary.get("image_count", 0) or 0)

            if image_count > 0:
                steps.append(
                    run_step(
                        "检查剧查查草稿质量",
                        [
                            python,
                            "scripts/check_juchacha_quality.py",
                            "--draft",
                            "data/external_benchmark/juchacha_normalized/juchacha_rankings_draft.csv",
                            "--output",
                            "data/external_benchmark/juchacha_normalized/juchacha_rankings_quality_issues.csv",
                            "--summary",
                            "data/external_benchmark/juchacha_normalized/juchacha_quality_summary.json",
                        ],
                    )
                )

                juchacha_quality_summary = read_json(
                    Path("data/external_benchmark/juchacha_normalized/juchacha_quality_summary.json")
                )

                error_count = int(juchacha_quality_summary.get("error_count", 0) or 0)
                warning_count = int(juchacha_quality_summary.get("warning_count", 0) or 0)

                should_finalize = False
                if args.juchacha_finalize_policy == "warning_ok":
                    should_finalize = error_count == 0
                elif args.juchacha_finalize_policy == "clean_only":
                    should_finalize = error_count == 0 and warning_count == 0
                elif args.juchacha_finalize_policy == "manual":
                    should_finalize = False

                if should_finalize:
                    steps.append(
                        run_step(
                            "确认并合并剧查查正式榜单",
                            [
                                python,
                                "scripts/finalize_juchacha_rankings.py",
                                "--draft",
                                "data/external_benchmark/juchacha_normalized/juchacha_rankings_draft.csv",
                                "--final",
                                "data/external_benchmark/juchacha_normalized/juchacha_rankings.csv",
                                "--accept-all",
                            ],
                        )
                    )
                else:
                    print("[pipeline] 剧查查未自动 finalize。")
                    print(
                        f"[pipeline] policy={args.juchacha_finalize_policy} "
                        f"error_count={error_count} warning_count={warning_count}"
                    )

            else:
                print("[pipeline] 剧查查没有新图片需要处理，跳过质量检查和 finalize。")

            if Path("data/external_benchmark/juchacha_normalized/juchacha_rankings.csv").exists():
                steps.append(
                    run_step(
                        "追加剧查查外部榜单到市场报告",
                        [
                            python,
                            "scripts/append_juchacha_to_market_report.py",
                            "--base-report",
                            "data/platform_market_normalized/market_feedback_report.md",
                            "--rankings",
                            "data/external_benchmark/juchacha_normalized/juchacha_rankings.csv",
                            "--output",
                            "data/platform_market_normalized/market_feedback_report_with_juchacha.md",
                        ],
                    )
                )

        if not args.skip_tests:
            steps.append(run_step("运行 pytest 全量测试", [python, "-m", "pytest", "-q"]))

        final_summary = {
            "batch_id": batch_id,
            "ok": all(s.get("ok") for s in steps),
            "args": vars(args),
            "steps": steps,
            "juchacha_import_summary": juchacha_import_summary,
            "juchacha_quality_summary": juchacha_quality_summary,
            "outputs": {
                "pipeline_status": str(status_path),
                "latest_pipeline_status": str(latest_status_path),
                "market_report": "data/platform_market_normalized/market_feedback_report.md",
                "market_report_with_juchacha": "data/platform_market_normalized/market_feedback_report_with_juchacha.md",
                "juchacha_final": "data/external_benchmark/juchacha_normalized/juchacha_rankings.csv",
            },
        }

        write_json(status_path, final_summary)
        write_json(latest_status_path, final_summary)

        print("")
        print("=" * 80)
        print("[pipeline] 日常市场数据流水线完成")
        print(f"[pipeline] status: {status_path}")
        print(f"[pipeline] latest: {latest_status_path}")
        print("=" * 80)

    except Exception as exc:
        error_summary = {
            "batch_id": batch_id,
            "ok": False,
            "args": vars(args),
            "steps": steps,
            "error": repr(exc),
        }
        write_json(status_path, error_summary)
        write_json(latest_status_path, error_summary)
        print(f"[pipeline] 失败：{exc}")
        raise


if __name__ == "__main__":
    main()
