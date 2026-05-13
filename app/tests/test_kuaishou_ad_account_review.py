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

    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_make_ad_account_review_tables_filters_review_statuses_and_sorts_by_spend():
    ks = load_kuaishou_module()

    ad_daily = pd.DataFrame(
        [
            {
                "ad_account_name": "A-泛账户",
                "extracted_title": "",
                "script_id": "",
                "script_title": "",
                "match_status": "account_name_generic",
                "match_method": "none",
                "match_confidence": 0,
                "match_reason": "generic_account_name",
                "review_required": True,
                "spend": 100,
                "source_file": "核心数据 (2).csv",
            },
            {
                "ad_account_name": "A-泛账户",
                "extracted_title": "",
                "script_id": "",
                "script_title": "",
                "match_status": "account_name_generic",
                "match_method": "none",
                "match_confidence": 0,
                "match_reason": "generic_account_name",
                "review_required": True,
                "spend": 50,
                "source_file": "核心数据 (3).csv",
            },
            {
                "ad_account_name": "B-低置信",
                "extracted_title": "穿越短剧世界",
                "script_id": "script_1",
                "script_title": "穿越短剧世界我受伤就变强",
                "match_status": "needs_review",
                "match_method": "account_name_heuristic_segment",
                "match_confidence": 0.85,
                "match_reason": "title_extracted_from_account_name",
                "review_required": True,
                "spend": 300,
                "source_file": "核心数据 (2).csv",
            },
            {
                "ad_account_name": "C-已匹配",
                "extracted_title": "男团王子",
                "script_id": "script_2",
                "script_title": "男团王子",
                "match_status": "matched",
                "match_method": "normalized_title_exact",
                "match_confidence": 1,
                "match_reason": "",
                "review_required": False,
                "spend": 999,
                "source_file": "核心数据 (2).csv",
            },
        ]
    )

    review_unique, review_by_spend = ks.make_ad_account_review_tables(ad_daily)

    assert set(review_unique["match_status"]) == {"account_name_generic", "needs_review"}
    assert "C-已匹配" not in set(review_unique["ad_account_name"])

    assert list(review_by_spend["ad_account_name"]) == ["B-低置信", "A-泛账户"]
    assert review_by_spend.loc[0, "total_spend"] == 300
    assert review_by_spend.loc[1, "total_spend"] == 150
    assert review_by_spend.loc[1, "rows"] == 2
