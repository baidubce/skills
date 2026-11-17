# Version History

## 1.1.0 (2026-11-16)

- 新增 Unlimited-OCR（文心 Unlimited-OCR 2）第三引擎：超长文本跨页段落/表格自动合并、标题层级精准分级、复杂表格以 HTML `<table>` 内嵌（实测：跨列 colspan、跨行空单元格占位）。
- 版本表述对齐官网：标准版去掉过时 "Pipeline 4.0"；PaddleOCR-VL 补全模型名 PaddleOCR-VL-1.6-0.9B。
- 格式扩展（官网 + 实测校准）：标准版新增 ods/tsv/rtf/odt/odp/webp/gif/ico/svg；VL 支持 webp/gif/ico/svg 图片类（ods/tsv/rtf/odt/odp 实测云端不支持，本地已拦截并提示走标准版）。
- 计费与免费额度按官网更新（Unlimited 2000 页/月、0.02 元/页限时折扣等）；限制口径对齐（直传 ≤50M/图片 ≤10M/8192px、file_url PDF 300M vs 100M、PDF ≤2000 页 vs ≤500 页）。
- 新增 VL 参数 `vlm_pixels_setting`、Unlimited 参数适用场景说明。

## 1.0.0

- 初始版本：标准版（文档解析）+ PaddleOCR-VL 1.6 双引擎统一入口。
- 异步任务提交/轮询、内容哈希缓存复用、六类索引（身份/目录/页/要素/检索/门牌）、结构化错误码（code/message/user_prompt）、API Key 配置指南。