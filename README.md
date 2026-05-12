# 纯文本剧本审核分析系统

## 项目目标

本项目用于对AI生成剧本进行纯文本层面的审核分析，输出结构化评分数据、可视化分析数据和自然语言审核总结。

## 当前阶段

MVP 阶段，只处理剧本文本，不处理视频、BGM、封面、演员、评论弹幕和播放数据。

## 核心功能

1. 剧本内容解析
2. 分项评分
3. 问题标签识别
4. 可视化数据输出
5. 审核报告生成
6. 样本数据保存
7. 腾讯视频平台数据反馈辅助分析

## 腾讯视频平台数据反馈

第一阶段支持导入已经从腾讯视频创作后台下载好的 `.xlsx` 文件，不需要用户手动准备 CSV，也不会自动登录或自动下载。

原始 Excel 放在：

- `data/tencent_video_exports/`

支持文件名：

- `账号趋势数据-*.xlsx`
- `专辑趋势数据-*.xlsx`
- `剧集趋势数据-*.xlsx`
- `视频趋势数据-*.xlsx`

运行导入与分析：

```bash
python scripts/import_tencent_video_data.py --input data/tencent_video_exports --output data/tencent_video_normalized
```

程序会自动生成标准化 CSV 和 `market_feedback_summary.json` 到：

- `data/tencent_video_normalized/`

如果 `data/tencent_video_normalized/market_feedback_summary.json` 存在，后续审核报告会自动追加“腾讯视频平台反馈分析”章节；如果不存在，原来的纯文本审核流程不受影响。

详细使用说明见：[docs/tencent_video_data.md](docs/tencent_video_data.md)。

## 项目目录

- app/prompts：提示词
- app/rubrics：评分规则和问题标签
- app/schemas：输出结构
- app/services：后续服务逻辑
- configs：路径和模型配置
- scripts：工具脚本
- docs：项目文档
