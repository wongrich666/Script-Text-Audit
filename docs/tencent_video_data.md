# 腾讯视频平台数据反馈模块使用说明

## 适用范围

本模块用于把腾讯视频创作后台导出的播放数据接入剧本审核报告，作为剧本复盘的辅助依据。

当前阶段只支持导入已经下载好的 Excel 文件，不做自动登录，不做自动下载，也不依赖导演表单数据。

## 需要下载的 Excel

请从腾讯视频创作后台下载以下 `.xlsx` 文件，并保持后台导出的文件名格式：

- `账号趋势数据-*.xlsx`
- `专辑趋势数据-*.xlsx`
- `剧集趋势数据-*.xlsx`
- `视频趋势数据-*.xlsx`

不需要手动转换 CSV。系统会自动读取 Excel，并生成标准化 CSV 和分析 JSON。

## 原始文件位置

把下载好的原始 Excel 放到：

```text
data/tencent_video_exports/
```

## 运行命令

在项目根目录执行：

```bash
python scripts/import_tencent_video_data.py --input data/tencent_video_exports --output data/tencent_video_normalized
```

命令会完成：

- 扫描 `data/tencent_video_exports/`
- 读取可识别的腾讯视频 Excel
- 标准化字段
- 输出 CSV
- 生成 `market_feedback_summary.json`

## 输出文件

运行完成后会输出到：

```text
data/tencent_video_normalized/account_daily_stats.csv
data/tencent_video_normalized/album_daily_stats.csv
data/tencent_video_normalized/episode_stats.csv
data/tencent_video_normalized/video_daily_stats.csv
data/tencent_video_normalized/market_feedback_summary.json
```

其中：

- `account_daily_stats.csv`：账号趋势标准化数据
- `album_daily_stats.csv`：专辑趋势标准化数据
- `episode_stats.csv`：剧集趋势标准化数据
- `video_daily_stats.csv`：视频趋势标准化数据
- `market_feedback_summary.json`：供审核报告使用的平台反馈摘要

## 审核报告接入

如果以下文件存在：

```text
data/tencent_video_normalized/market_feedback_summary.json
```

最终审核报告会自动增加一节：

```text
腾讯视频平台反馈分析
```

该章节会把平台数据转成自然语言摘要，通常包括：

- 账号整体趋势
- 专辑表现
- 剧集掉点排行
- 高曝光低有效播放集数
- 高互动/高分享集数
- 剧本复盘建议

如果 `market_feedback_summary.json` 不存在，原来的纯文本审核流程不受影响。

## 解读原则

平台数据只作为剧本复盘辅助依据，不代表因果结论。

报告中应使用谨慎表述，例如：

- “数据提示”
- “建议复盘”
- “可能需要检查”

不要把平台数据写成“证明某集一定有问题”。例如，高曝光低有效播放只提示该集可能值得复盘，需要结合剧本文本、标题封面、投放位置、更新节奏等因素综合判断。

## 不要提交到 Git

以下目录和文件可能包含真实业务数据、账号数据或后台导出文件，不要提交到 Git：

```text
data/tencent_video_exports/
data/tencent_video_normalized/
data/tencent_video_auth/
*.xlsx
```

这些路径已经在 `.gitignore` 中配置。提交前仍建议运行 `git status` 确认没有误提交真实数据。
