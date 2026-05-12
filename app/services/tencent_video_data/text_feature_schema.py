from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pandas as pd


TEXT_FEATURE_COLUMNS = [
    "episode_no",
    "episode_title",
    "has_script_text",
    "script_length",
    "opening_conflict_score",
    "hook_score",
    "emotion_intensity",
    "exposition_ratio",
    "dialogue_density",
    "cliffhanger_score",
    "plot_progress_score",
    "reversal_count",
    "main_goal_clarity",
    "created_at",
]

PLACEHOLDER_FEATURE_COLUMNS = [
    "opening_conflict_score",
    "hook_score",
    "emotion_intensity",
    "exposition_ratio",
    "dialogue_density",
    "cliffhanger_score",
    "plot_progress_score",
    "reversal_count",
    "main_goal_clarity",
]


@dataclass
class TextFeatureSchemaResult:
    generated_files: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def build_episode_text_features(normalized_dir: str | Path) -> TextFeatureSchemaResult:
    base_path = Path(normalized_dir)
    result = TextFeatureSchemaResult()
    samples_path = base_path / "episode_samples.csv"
    output_path = base_path / "episode_text_features.csv"

    if not samples_path.exists():
        result.warnings.append(f"{samples_path.name}: 文件不存在，无法生成 episode_text_features.csv。")
        return result

    try:
        samples = pd.read_csv(samples_path, keep_default_na=False)
    except Exception as exc:
        result.warnings.append(f"{samples_path.name}: 读取失败，无法生成 episode_text_features.csv。原因：{exc}")
        return result

    for field in ["episode_no", "episode_title", "script_text"]:
        if field not in samples.columns:
            samples[field] = ""

    script_text = samples["script_text"].fillna("").astype(str)
    created_at = datetime.now().isoformat(timespec="seconds")
    features = pd.DataFrame(
        {
            "episode_no": samples["episode_no"],
            "episode_title": samples["episode_title"].fillna("").astype(str),
            "has_script_text": script_text.str.strip().ne(""),
            "script_length": script_text.str.len(),
            "created_at": created_at,
        }
    )

    for field in PLACEHOLDER_FEATURE_COLUMNS:
        features[field] = pd.NA

    features = features[TEXT_FEATURE_COLUMNS]
    features.to_csv(output_path, index=False, encoding="utf-8-sig")
    result.generated_files.append(str(output_path))
    return result
