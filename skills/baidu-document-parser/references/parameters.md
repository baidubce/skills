# 百度文档解析 API 参数详解（标准版 + PaddleOCR-VL 1.6 + Unlimited-OCR）

三套引擎都是异步接口：先 **提交请求** 拿 `task_id`，再 **轮询获取结果**。本技能脚本已封装提交/轮询/下载/索引/缓存。

## 接口地址

| 引擎 | 提交 | 查询 |
|------|------|------|
| 标准版 | `POST /rest/2.0/brain/online/v2/parser/task` | `POST /rest/2.0/brain/online/v2/parser/task/query` |
| PaddleOCR-VL | `POST /rest/2.0/brain/online/v2/paddle-vl-parser/task` | `POST /rest/2.0/brain/online/v2/paddle-vl-parser/task/query` |
| Unlimited-OCR | `POST /rest/2.0/brain/online/v2/unlimited-ocr-parser/task` | `POST /rest/2.0/brain/online/v2/unlimited-ocr-parser/task/query` |

Host：`https://aip.baidubce.com`，均带 `?access_token={token}`，`Content-Type: application/x-www-form-urlencoded`。

## 文件参数（必选，二选一）

| 参数 | 类型 | 说明 |
|------|------|------|
| file_data | string | 文件 base64。优先级高于 file_url。三套引擎一致：图片 ≤10M（最长边 ≤8192px）、其余 ≤50M；超 50M 须改 file_url |
| file_url | string | 文件 URL，≤ 1024 字节。标准版 PDF ≤ 300M、非 PDF ≤ 50M（PDF ≤2000 页）；VL / Unlimited PDF ≤ 100M（≤500 页）。请关闭 URL 防盗链 |
| file_name | string | 文件名，后缀须正确，如 "1.pdf"（本技能据此判类型/选路） |

## 标准版（官方接口名"文档解析"）独有/通用参数

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| recognize_formula | bool | False | 版式文档公式识别 |
| analysis_chart | bool | False | 统计图表解析 |
| angle_adjust | bool | False | 图片角度矫正 |
| parse_image_layout | bool | False | 返回文档图片位置 |
| language_type | string | CHN_ENG | 识别语种（20+ 种，需指定） |
| switch_digital_width | string | auto | 数字全半角：auto/half/full |
| html_table_format | bool | True | 表格转 HTML 返回 |
| version | string | - | 接口版本（按需） |

### 标准版支持语种

CHN_ENG、JAP、KOR、FRE、SPA、POR、GER、ITA、RUS、DAN、DUT、MAL、SWE、IND、POL、ROM、TUR、GRE、HUN、THA、VIE、ARA、HIN。

## PaddleOCR-VL（PaddleOCR-VL-1.6-0.9B）参数

| 参数 | 类型 | 说明 |
|------|------|------|
| recognize_formula | - | **无需开启**，默认识别公式 |
| parse_image_layout | - | **无需开启**，默认解析所有图片 |
| language_type | - | **无需开启**，默认自动识别语种（100+） |
| analysis_chart | bool | 统计图表解析 |
| merge_tables | bool | 跨页表格合并 |
| relevel_titles | bool | 对 paragraph_title 分级（写入 sub_type） |
| recognize_seal | bool | 识别印章内容 |
| return_span_boxes | bool | 返回行级坐标 |
| angle_adjust | bool | 角度矫正（斜拍/颠倒件） |
| unwarp | bool | 弯折矫正 |
| erase_seal | bool | 擦除印章（会改画面，核章时勿开） |
| erase_watermark | bool | 擦除水印 |
| vlm_pixels_setting | dict | 控制模型对不同内容类型图像缩放时的像素区间。默认：ocr/table min/max 112896/1003520，chart/formula/seal/spotting 112896/112896（spotting max 1605632）。一般无需下发 |

> 公式/图片/语种三项 VL 默认开启，表中标 **无需开启**。`erase_seal` / `erase_watermark` / `unwarp` 为 VL 画面处理项，按场景打开。
>
> **格式实测校准**：官网 VL 文档页格式清单与实际 API 不符——ods / tsv / rtf / odt / odp 实测 VL 后端不支持（提交成功但任务报 TASK_FAILED），请走标准版；图片类 webp / gif / ico / svg 实测可用。

## Unlimited-OCR（文心 Unlimited-OCR 2）参数

| 参数 | 类型 | 默认 | 适用场景 | 说明 |
|------|------|------|---------|------|
| angle_adjust | bool | True | 斜拍、颠倒、旋转的图片/扫描件 | 角度矫正（Unlimited 默认开启） |
| angle_mode | string | direction | 颠倒但方向固定用 direction；任意旋转/倒装用 arbitrary | 矫正模式：direction 四方向 / arbitrary 任意方向 |
| erase_seal | bool | False | 印章挡住字、只要读正文且**不需要核章** | 擦除印章（会改画面） |
| erase_watermark | bool | False | 水印挡住字、只要读正文 | 擦除水印 |
| unwarp | bool | False | 纸张弯折/卷曲导致的识别不清 | 图像扭曲矫正 |
| need_pdffile_data | bool | False | 下游要整份 PDF 原件归档/二次处理 | 返回整份 PDF 下载链接（30 天有效） |
| need_pdffile_vis_data | bool | False | 开了角度矫正/擦章等预处理，下游要看处理后的 PDF | 返回预处理后 PDF 下载链接（30 天有效） |
| page_filter | list[int] | - | 长文档只要某几页，云端直取省时省额度 | 云端只解析指定页，**页码从 0 开始**（[1,3] = 第 2、4 页）。本技能统一用 `--page_range`（1 基）解析后本地裁剪，不传此参数 |

> **无需开关的内置能力**：跨页段落/表格自动合并（markdown 中表格以 HTML `<table>` 内嵌；实测跨列用 `colspan`、跨行以空单元格占位而非 `rowspan`）、标题层级精准分级、公式/图片默认识别。不返回细粒度版面坐标（要行坐标/核章走 VL）。

## 文档分块（标准版 / VL 支持，RAG 场景）

`return_doc_chunks` 为字典：`switch`(bool, 默认 False)、`split_type`(chunk/mark)、`separators`(list)、`chunk_size`(int, -1=语义自动切)。本技能 `--chunk` 开启语义自动分块。

## 返回结构

### 查询返回（result）

| 字段 | 说明 |
|------|------|
| task_id | 任务 ID |
| status | pending / processing / running / success / failed |
| task_error | 失败/额度不足等报错 |
| markdown_url | Markdown 结果链接（30 天有效） |
| parse_result_url | JSON 结果 BOS 链接（30 天有效） |

### parse_result_url JSON 顶层

`file_name`、`file_id`、`pages[]`，分块开启时含 `chunks[]`。

### 页面对象 pages[]

`page_id`、`page_num`(0 基)、`text`、`markdown`、`layouts[]`、`tables[]`、`images[]`、`meta`。
`meta`：`page_width`、`page_height`、`is_scan`(是否扫描件)、`page_angle`、`page_type`(text/contents/appendix/others)、`sheet_name`(Excel)。

> Unlimited-OCR：整份文档结果优先用 `markdown_url`（复杂表格以 HTML `<table>` 内嵌，实测跨列 `colspan`、跨行空单元格占位）；`parse_result_url` 的页级 `markdown` 兜底，顶层还含 `pdf_data` / `pdf_vis_data`（开 `need_pdffile_*` 时返回）。

### 版面元素 layouts[]

公共字段：`layout_id`、`text`、`position`[x,y,w,h]、`type`、`sub_type`、`parent`、`children`。
VL 额外：`polygon`（多边形顶点）、`span_boxes`（行信息，开 `return_span_boxes` 生效）。

**版面类型差异**：

- 标准版（8+ 类）：text、table、image、head_tail、contents、seal、title、formula、hand_sign；title 的 sub_type 为 `title_{n}`/`image_title`/`table_title`，image 的 sub_type 为 `chart`/`figure`/`QR_code`/`Bar_code`。
- VL（24 类）：text、table、image、chart、doc_title、paragraph_title、figure_title、display_formula、inline_formula、formula_number、header、footer、header_image、footer_image、number、abstract、algorithm、aside_text、content、footnote、reference、reference_content、seal、vertical_text。

### 表格对象 tables[]

`layout_id`、`markdown`、`position`、`cells`、`matrix`（2D 索引矩阵，重复下标=合并单元格）、`merge_table`（begin/inner/end）。标准版另有 `table_title_id`。

### 图片对象 images[]

`layout_id`、`position`、`data_url`、`image_description`（统计图表解析，JSON 字符串，需 `json.loads`）。标准版另有 `image_title_id`、`content_layouts`。

## QPS 与轮询

- 提交 2 QPS；查询标准版 10 QPS / VL 5 QPS / Unlimited 2 QPS（官方口径）。
- 提交后 5~10 秒开始轮询，间隔 5 秒，最大 300 秒。
- `error_code=0` 只代表任务已创建，不代表解析完成；以 `status=success` 为准（Unlimited 官方注：查询超时不代表任务失败，保留 `task_id` 继续查询，勿重复提交）。

## 相关文档

- [标准版 API](https://ai.baidu.com/ai-doc/OCR/llxst5nn0)
- [PaddleOCR-VL API](https://cloud.baidu.com/doc/OCR/s/3mi73at9o)
- [Unlimited-OCR API](https://cloud.baidu.com/doc/OCR/s/fmr1p39gb)
- [错误码参考](error_codes.md)
- [API Key 配置](apikey-fetch.md)

