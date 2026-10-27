# API Key 配置指南（baidu-document-parser）

本技能鉴权**二选一**，任配其一即可：

- **方式 A — AK/SK**：`BAIDU_DOC_AI_API_KEY`（AK）+ `BAIDU_DOC_AI_SECRET_KEY`（SK），脚本用 client_credentials 换 access_token，调用时拼 `?access_token=`。
- **方式 B — API Key（单串，新版统一鉴权）**：`BAIDU_DOC_AI_BEARER_TOKEN`；或只配 `BAIDU_DOC_AI_API_KEY`、**不配** SK。脚本以 `Authorization: Bearer <API Key>` 调用，不再换 token。

> 解析优先级：先 `BAIDU_DOC_AI_BEARER_TOKEN` → 再 AK+SK → 再单独的 `BAIDU_DOC_AI_API_KEY`（当 Bearer）。两者都没有则报 `CREDENTIALS_REQUIRED`。

## 1. 获取 API Key 和 Secret Key

访问 **https://ai.baidu.com/ai-doc/REFERENCE/Ck3dwjhhu#1-获取aksk**

- 登录百度云账号
- 创建应用或查看已有的 API Key / Secret Key
- 复制你的 **API Key** 和 **Secret Key**

## 2. 领取免费测试资源

访问 **https://cloud.baidu.com/doc/OCR/s/fk3h7xu7h**

| 用户类型 | 标准版免费额度 | PaddleOCR-VL 免费额度 |
|---------|---------------|----------------------|
| 个人实名认证 | 200 页 | 200 页 |
| 企业实名认证 | 200 页 | 1000 页 |

## 3. 配置环境变量

### 方式一：直接设置

```bash
# A. AK/SK
export BAIDU_DOC_AI_API_KEY="your_actual_api_key_here"
export BAIDU_DOC_AI_SECRET_KEY="your_actual_secret_key_here"

# B. API Key（单串，二选一，与上面的 SK 不要同时用）
export BAIDU_DOC_AI_BEARER_TOKEN="your_api_key_here"
```

### 方式二：通过配置文件

编辑 `~/.claude/settings.json` 或项目 `.claude/settings.json`：

```json
{
  "skills": {
    "entries": {
      "baidu-document-parser": {
        "env": {
          "BAIDU_DOC_AI_API_KEY": "your_actual_api_key_here",
          "BAIDU_DOC_AI_SECRET_KEY": "your_actual_secret_key_here"
        }
      }
    }
  }
}
```

## 4. 验证配置

```bash
curl -X POST 'https://aip.baidubce.com/oauth/2.0/token' \
  -d 'grant_type=client_credentials' \
  -d 'client_id={your_api_key}' \
  -d 'client_secret={your_secret_key}'
```

成功返回 `access_token` 与 `expires_in: 2592000`（30 天）。

## 5. 测试

```bash
python3 scripts/baidu_doc_parser.py parse --file_url "https://example.com/test.pdf" --file_name "test.pdf"
```

## 常见问题

- `echo $BAIDU_DOC_AI_API_KEY` 验证变量是否设置
- 确认 API Key 已开通百度智能文档分析平台服务
- 检查账户余额或免费额度
- access_token 过期（110/111）脚本会在下次运行自动重取

## 相关链接

- [获取 AK/SK](https://ai.baidu.com/ai-doc/REFERENCE/Ck3dwjhhu#1-获取aksk)
- [领取免费资源](https://cloud.baidu.com/doc/OCR/s/fk3h7xu7h)
- [百度云控制台](https://console.bce.baidu.com/ai/)
