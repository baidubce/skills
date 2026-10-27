# 百度文档解析 API 参数详解（标准版 4.0 + PaddleOCR-VL 1.6）

两套引擎都是异步接口：先 **提交请求** 拿 `task_id`，再 **轮询获取结果**。本技能脚本已封装提交/轮询/下载/索引/缓存。

## 接口地址

| 引擎 | 提交 | 查询 |
|------|------|------|
| 标准版 | `POST /rest/2.0/brain/online/v2/parser/task` | `POST /rest/2.0/brain/online/v2/parser/task/query` |
| PaddleOCR-VL | `POST /rest/2.0/brain/online/v2/paddle-vl-parser/task` | `POST /rest/2.0/brain/online/v2/paddle-vl-parser/task/query` |

Host：`https://aip.baidubce.com`，均带 `?access_token={token}`，`Content-Type: application/x-www-form-urlencoded`。

## 文件参数（必选，二选一）

| 参数 | 类型 | 说明 |
|------|------|------|
| file_data | string | 文件 base64。优先级高于 file_url。标准版 ≤ 50M；VL 图片 ≤ 10M、版式 ≤ 100M、流式 ≤ 50M。超 50M 直传须改 file_url |
| file_url | string | 文件 URL，≤ 1024 字节。标准版 PDF ≤ 300M；VL PDF ≤ 100M。请关闭 URL 防盗链 |
| file_name | string | 文件名，后缀须正确，如 "1.pdf"（本技能据此判类型/选路） |

## 标准版（Pipeline 4.0）独有/通用参数

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

## PaddleOCR-VL（1.6）参数

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

> 公式/图片/语种三项 VL 默认开启，表中标 **无需开启**。`erase_seal` / `erase_watermark` / `unwarp` 为 VL 画面处理项，按场景打开。

## 文档分块（两套引擎均支持，RAG 场景）

`return_doc_chunks` 为字典：`switch`(bool, 默认 False)、`split_type`(chunk/mark)、`separators`(list)、`chunk_size`(int, -1=语义自动切)。本技能 `--chunk` 开启语义自动分块。

## 返回结构

### 查询返回（result）

| 字段 | 说明 |
|------|------|
| task_id | 任务 ID |
| status | pending / processing / success / failed |
| task_error | 失败/额度不足等报错 |
| markdown_url | Markdown 结果链接（30 天有效） |
| parse_result_url | JSON 结果 BOS 链接（30 天有效） |

### parse_result_url JSON 顶层

`file_name`、`file_id`、`pages[]`，分块开启时含 `chunks[]`。

### 页面对象 pages[]

`page_id`、`page_num`(0 基)、`text`、`layouts[]`、`tables[]`、`images[]`、`meta`。
`meta`：`page_width`、`page_height`、`is_scan`(是否扫描件)、`page_angle`、`page_type`(text/contents/appendix/others)、`sheet_name`(Excel)。

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

- 提交 2 QPS；查询标准版 10 QPS / VL 5 QPS。
- 提交后 5~10 秒开始轮询，间隔 5 秒，最大 300 秒。

## 相关文档

- [标准版 API](https://ai.baidu.com/ai-doc/OCR/llxst5nn0)
- [PaddleOCR-VL API](https://cloud.baidu.com/doc/OCR/s/3mi73at9o)
- [错误码参考](error_codes.md)
- [API Key 配置](apikey-fetch.md)

