# 百度文档解析 API 错误码参考（标准版 + PaddleOCR-VL 通用）

两套引擎（`/v2/parser` 标准版、`/v2/paddle-vl-parser` VL）共用同一套 OCR 错误码。

## 认证相关错误

| 错误码 | 错误信息 | 说明 | 解决方案 |
|--------|---------|------|----------|
| 1 | Unknown error | 未知错误 | 重试请求，持续出现请联系技术支持 |
| 2 | Service temporarily unavailable | 服务暂不可用 | 重试请求 |
| 3 | Unsupported openapi method | API 接口不存在 | 检查 URL 是否正确 |
| 4 | Open api request limit reached | 集群超限额 | 重试请求 |
| 6 | No permission to access data | 无接口调用权限（应用未勾选接口） | 登录控制台编辑对应应用、勾选相关文字识别接口后重试；或用[权限额度诊断工具](https://console.bce.baidu.com/tools/#/aiInterfacePermissions)自助诊断 |
| 14 | IAM Certification failed | IAM 认证失败 | 检查签名或改用 AK/SK |
| 17 | Open api daily request limit reached | 日配额超限 | 购买额度或等待次日重置 |
| 18 | Open api qps request limit reached | QPS 超限 | 降低请求频率 |
| 19 | Open api total request limit reached | 总量配额超限 | 购买额外配额 |
| 100 | Invalid parameter | access_token 无效 | 重新获取 access_token |
| 110 | Access token invalid or no longer valid | access_token 无效 | token 有效期 30 天，重新获取 |
| 111 | Access token expired | access_token 过期 | 重新获取 |

## 文件相关错误

| 错误码 | 错误信息 | 说明 | 解决方案 |
|--------|---------|------|----------|
| 216200 | empty file or fileurl | 文件或 URL 为空 | 提供 file_data 或 file_url |
| 216201 | file format error | 文件格式不支持 | 使用支持的格式 |
| 216202 | file size error | 文件大小超限 | 缩减文件大小（file_data ≤ 50MB） |

## 任务处理错误

| 错误码 | 错误信息 | 说明 | 解决方案 |
|--------|---------|------|----------|
| 282000 | internal error | 任务处理失败 | 重试或联系技术支持 |
| 282003 | missing parameters | 缺少必要参数 | 检查必填参数 |
| 282005 | quota exceed error | 额度不足 | 申请增加配额 |
| 282006 | check user auth error | 用户权限校验失败 | 验证用户权限 |
| 282007 | task not exist, please check task id | 任务不存在 | 检查 task_id 是否正确 |
| 282018 | Service busy | 服务繁忙 | 降低请求频率 |

## URL 相关错误

| 错误码 | 错误信息 | 说明 | 解决方案 |
|--------|---------|------|----------|
| 282111 | url format illegal | URL 格式不合法 | 检查 URL 格式 |
| 282112 | url download timeout | URL 下载超时 | 检查 URL 是否可访问 |
| 282113 | url response invalid | URL 响应无效 | 检查 URL 返回内容 |
| 282114 | url size error | URL 长度超过 1024 字节 | 缩短 URL |

## 错误处理策略

| 错误类型 | 错误码 | 建议处理方式 |
|---------|--------|-------------|
| 瞬时错误 | 1, 2, 4, 282000, 282018 | 指数退避重试 |
| 认证错误 | 100, 110, 111 | 重新获取 access_token |
| 配额错误 | 17, 18, 19, 282005 | 等待或购买额外配额 |
| 参数错误 | 216200, 216201, 282003, 283016 | 修正参数后重试 |
| URL 错误 | 282111, 282112, 282113, 282114 | 检查并修正 URL |

## 错误响应格式

```json
{
  "log_id": "13665091038742503867108513247688",
  "error_code": "282007",
  "error_msg": "task not exist, please check task id",
  "result": "null"
}
```

## 云端 error_code → 本技能 code 对照

脚本把百度 `error_code` 归一成稳定的技能 `code`（失败响应带 `code`/`message`/`user_prompt`/`details`）：

| 本技能 code | 命中的云端 error_code | Agent 动作 |
|-------------|----------------------|-----------|
| AUTH_FORBIDDEN | 6 | 停，提示管理员开通 |
| CREDENTIALS_REQUIRED | 14, 100, 110, 111 / 本地缺 AK/SK / oauth 失败 | 停，发开通说明 |
| QUOTA_EXCEEDED | 17, 19, 282005 | 停，提示充值 |
| RATE_LIMIT | 4, 18, 282018 | 退避后同一任务重试，不重新提交 |
| UNSUPPORTED_TYPE | 216201 / 本地扩展名不支持 | 停，换格式 |
| FILE_TOO_LARGE | 216202, 282114 / 本地 > 50M | 停，压缩/改 URL/选页 |
| FILE_NOT_FOUND | 216200, 282111, 282112, 282113 / 本地不存在或为空 | 停，重选文件 |
| TASK_FAILED | 任务 status=failed 或带 task_error | 看 details.task_error |
| TIMEOUT | 轮询超 300s | `--resume_task` 续查 |
| BACKEND_UNAVAILABLE | 1, 2, 282000, 282003, 282007 等未归类 | 不自动换引擎，问用户 |

> `LOW_TEXT_QUALITY` 是成功响应里的警告（`warnings[]`），不是错误码。

## 获取帮助

- [文字识别快速入门（创建应用 / 获取 API Key / 开通能力）](https://cloud.baidu.com/doc/OCR/s/Olpjnv9u9)
- [权限额度诊断工具（自助诊断接口权限/额度）](https://console.bce.baidu.com/tools/#/aiInterfacePermissions)
- [提交工单](https://ticket.bce.baidu.com/#/ticket/create~productId=96&questionId=1306&channel=2)
- [百度云控制台](https://console.bce.baidu.com/ai/)
