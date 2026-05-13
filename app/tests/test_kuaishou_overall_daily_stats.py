from pathlib import Path
import importlib.util
import sys

import pandas as pd


def load_kuaishou_module():
    module_path = Path("scripts/import_kuaishou_data.py")
    module_name = "import_kuaishou_data"

    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)

    assert spec is not None
    assert spec.loader is not None

    # dataclasses 在 Python 3.12 下会通过 sys.modules 查当前模块。
    # 动态加载脚本时必须先注册，否则 @dataclass 会报 NoneType.__dict__。
    sys.modules[module_name] = module

    spec.loader.exec_module(module)
    return module


def test_classify_overall_daily_payment_core_table():
    ks = load_kuaishou_module()

    df = pd.DataFrame(
        [
            {
                "日期": "2026-05-01",
                "付费人数": 10,
                "付费订单数": 11,
                "付费金额（元）": 120.5,
                "消耗（元）": 80.0,
                "全域ROI": 1.5,
                "IAA广告含返货LTV(元)": 0.3,
            }
        ]
    )

    assert ks.classify_table(df) == "overall_daily"


def test_classify_overall_daily_video_core_table():
    ks = load_kuaishou_module()

    df = pd.DataFrame(
        [
            {
                "日期": "2026-05-01",
                "视频-播放量": 1000,
                "视频-点赞量": 20,
                "视频-评论量": 3,
                "视频-收藏量": 2,
                "付费金额（元）": 120.5,
                "消耗（ 元）": 80.0,
                "IAA广告不含返货变现ROI": 0.9,
            }
        ]
    )

    assert ks.classify_table(df) == "overall_daily"


def test_normalize_overall_daily_maps_expected_columns():
    ks = load_kuaishou_module()

    raw = pd.DataFrame(
        [
            {
                "日期": "2026-05-01",
                "视频-播放量": "1000",
                "视频-点赞量": "20",
                "视频-评论量": "3",
                "视频-收藏量": "2",
                "付费人数": "4",
                "付费订单数": "5",
                "付费金额（元）": "120.5",
                "消耗（元）": "80",
                "全域ROI": "1.5",
                "商业化ROI": "1.2",
                "IAA广告含返货LTV(元)": "0.3",
                "IAA广告含返货变现ROI": "0.4",
                "IAA广告不含返货LTV(元)": "0.2",
                "IAA广告不含返货变现ROI": "0.25",
                "source_file": "核心数据 (1).csv",
                "source_sheet": "",
            }
        ]
    )

    out = ks.normalize_overall_daily(raw)

    assert list(out.columns) == [
        "platform",
        "date",
        "play_count",
        "like_count",
        "comment_count",
        "favorite_count",
        "paid_users",
        "paid_orders",
        "paid_amount",
        "ad_spend",
        "global_roi",
        "commercial_roi",
        "iaa_ltv_with_rebate",
        "iaa_roi_with_rebate",
        "iaa_ltv_without_rebate",
        "iaa_roi_without_rebate",
        "source_file",
        "source_sheet",
    ]
    assert out.loc[0, "platform"] == "kuaishou"
    assert out.loc[0, "date"] == "2026-05-01"
    assert out.loc[0, "play_count"] == 1000.0
    assert out.loc[0, "paid_orders"] == 5.0
    assert out.loc[0, "paid_amount"] == 120.5
    assert out.loc[0, "ad_spend"] == 80.0
    assert out.loc[0, "source_file"] == "核心数据 (1).csv"


def test_build_script_registry_empty_dir_keeps_columns(tmp_path):
    ks = load_kuaishou_module()

    registry = ks.build_script_registry(tmp_path)

    assert registry.empty
    assert list(registry.columns) == [
        "script_id",
        "canonical_title",
        "title_norm",
        "aliases",
        "script_path",
        "episode_count",
        "content_hash",
    ]
