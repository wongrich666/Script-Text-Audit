from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .analyzer import extract_episode_no_from_title


@dataclass
class ScriptAlignResult:
    updated_files: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    aligned_count: int = 0


def load_episode_scripts(script_dir: str | Path) -> tuple[dict[int, str], list[str]]:
    base_path = Path(script_dir)
    warnings: list[str] = []
    scripts: dict[int, str] = {}

    if not base_path.exists():
        warnings.append(f"{base_path}: 逐集剧本文本目录不存在，已跳过 script_text 对齐。")
        return scripts, warnings

    for script_path in sorted(base_path.glob("*.txt")):
        episode_no = extract_episode_no_from_title(script_path.stem)
        if episode_no is None:
            warnings.append(f"{script_path.name}: 无法从文件名提取集数，已跳过。")
            continue
        try:
            text = script_path.read_text(encoding="utf-8-sig").strip().lstrip("\ufeff")
        except UnicodeDecodeError:
            text = script_path.read_text(encoding="utf-8").strip().lstrip("\ufeff")
        except Exception as exc:
            warnings.append(f"{script_path.name}: 读取失败，已跳过。原因：{exc}")
            continue
        scripts[episode_no] = text

    return scripts, warnings


def align_episode_scripts(
    normalized_dir: str | Path,
    script_dir: str | Path = "data/episode_scripts",
) -> ScriptAlignResult:
    result = ScriptAlignResult()
    samples_path = Path(normalized_dir) / "episode_samples.csv"

    if not samples_path.exists():
        result.warnings.append(f"{samples_path.name}: 文件不存在，无法对齐逐集剧本文本。")
        return result

    scripts, warnings = load_episode_scripts(script_dir)
    result.warnings.extend(warnings)
    if not scripts:
        return result

    try:
        samples = pd.read_csv(samples_path, keep_default_na=False)
    except Exception as exc:
        result.warnings.append(f"{samples_path.name}: 读取失败，无法对齐逐集剧本文本。原因：{exc}")
        return result

    if "episode_no" not in samples.columns:
        result.warnings.append(f"{samples_path.name}: 缺少 episode_no 字段，无法对齐逐集剧本文本。")
        return result
    if "script_text" not in samples.columns:
        samples["script_text"] = ""

    episode_numbers = pd.to_numeric(samples["episode_no"], errors="coerce")
    for index, episode_no in episode_numbers.items():
        if pd.isna(episode_no):
            continue
        text = scripts.get(int(episode_no))
        if text is None:
            continue
        samples.at[index, "script_text"] = text
        result.aligned_count += 1

    samples.to_csv(samples_path, index=False, encoding="utf-8-sig")
    result.updated_files.append(str(samples_path))
    return result
