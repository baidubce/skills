#!/bin/bash
# 百度智能云 BOS Skill 自动设置脚本
# 用法:
#   setup.sh --check-only                    仅检查环境状态
#   setup.sh --ak <AK> --sk <SK> --endpoint <ENDPOINT> --bucket <BUCKET>

set -e

# 颜色
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

ok()   { echo -e "${GREEN}✓${NC} $1"; }
fail() { echo -e "${RED}✗${NC} $1"; }
warn() { echo -e "${YELLOW}!${NC} $1"; }

# 获取脚本所在目录（skill baseDir）
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# ========== 检查函数 ==========

check_node() {
  if command -v node &>/dev/null; then
    ok "Node.js $(node --version)"
    return 0
  else
    fail "Node.js 未安装"
    return 1
  fi
}

check_npm() {
  if command -v npm &>/dev/null; then
    ok "npm $(npm --version)"
    return 0
  else
    fail "npm 未安装"
    return 1
  fi
}

check_bos_node_sdk() {
  if command -v node &>/dev/null && node -e "require('@baiducloud/sdk')" &>/dev/null 2>&1; then
    ok "@baiducloud/sdk (Node.js SDK) 已安装"
    return 0
  else
    fail "@baiducloud/sdk (Node.js SDK) 未安装"
    return 1
  fi
}

check_bcecmd() {
  if command -v bcecmd &>/dev/null; then
    ok "bcecmd 可用"
    return 0
  else
    warn "bcecmd 未安装（可选，安装参考: https://cloud.baidu.com/doc/BOS/s/Ck1rymwdi）"
    return 1
  fi
}

check_env_vars() {
  local all_set=true
  for var in BCE_ACCESS_KEY_ID BCE_SECRET_ACCESS_KEY BCE_BOS_ENDPOINT BCE_BOS_BUCKET; do
    if [ -n "${!var}" ]; then
      ok "$var 已设置"
    else
      fail "$var 未设置"
      all_set=false
    fi
  done
  $all_set
}

# ========== 检查模式 ==========

do_check() {
  echo "=== 百度智能云 BOS Skill 环境检查 ==="
  echo ""
  echo "--- 基础环境 ---"
  check_node || true
  check_npm || true
  echo ""
  echo "--- 方式一: Node.js SDK ---"
  check_bos_node_sdk || true
  echo ""
  echo "--- 方式二: bcecmd ---"
  check_bcecmd || true
  echo ""
  echo "--- 环境变量 ---"
  check_env_vars || true
  echo ""
  echo "--- Skill 文件 ---"
  [ -f "$BASE_DIR/SKILL.md" ] && ok "SKILL.md" || fail "SKILL.md 不存在"
  [ -f "$BASE_DIR/scripts/bos_node.mjs" ] && ok "scripts/bos_node.mjs" || fail "scripts/bos_node.mjs 不存在"
  [ -f "$BASE_DIR/references/api_reference.md" ] && ok "references/api_reference.md" || fail "references/api_reference.md 不存在"
  echo ""
}

# ========== 设置模式 ==========

do_setup() {
  local AK=""
  local SK=""
  local ENDPOINT=""
  local BUCKET=""
  local STS_TOKEN=""

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --ak)        AK="$2"; shift 2;;
      --sk)        SK="$2"; shift 2;;
      --endpoint)  ENDPOINT="$2"; shift 2;;
      --bucket)    BUCKET="$2"; shift 2;;
      --sts-token) STS_TOKEN="$2"; shift 2;;
      *) shift;;
    esac
  done

  if [ -z "$AK" ] || [ -z "$SK" ] || [ -z "$ENDPOINT" ] || [ -z "$BUCKET" ]; then
    echo "错误: 缺少必需参数"
    echo "用法: setup.sh --ak <AK> --sk <SK> --endpoint <ENDPOINT> --bucket <BUCKET>"
    exit 1
  fi

  # 输入校验：AK/SK 仅允许字母数字，Endpoint 仅允许域名字符，Bucket 仅允许 DNS 字符
  local SAFE_PATTERN_AKSK='^[A-Za-z0-9/+=]+$'
  local SAFE_PATTERN_ENDPOINT='^[a-zA-Z0-9._-]+$'
  local SAFE_PATTERN_BUCKET='^[a-z0-9][a-z0-9.-]*[a-z0-9]$'

  if [[ ! "$AK" =~ $SAFE_PATTERN_AKSK ]]; then
    echo "错误: AccessKeyId 包含非法字符"; exit 1
  fi
  if [[ ! "$SK" =~ $SAFE_PATTERN_AKSK ]]; then
    echo "错误: SecretAccessKey 包含非法字符"; exit 1
  fi
  if [[ ! "$ENDPOINT" =~ $SAFE_PATTERN_ENDPOINT ]]; then
    echo "错误: Endpoint 包含非法字符"; exit 1
  fi
  if [[ ! "$BUCKET" =~ $SAFE_PATTERN_BUCKET ]]; then
    echo "错误: Bucket 名称包含非法字符"; exit 1
  fi
  if [ -n "$STS_TOKEN" ] && [[ ! "$STS_TOKEN" =~ $SAFE_PATTERN_AKSK ]]; then
    echo "错误: StsToken 包含非法字符"; exit 1
  fi

  echo "=== 百度智能云 BOS Skill 自动设置 ==="
  echo ""

  # 1. 安装 Node.js SDK
  echo "--- 步骤 1: 安装 Node.js SDK ---"
  if check_node; then
    if [ ! -f "$BASE_DIR/package.json" ]; then
      (cd "$BASE_DIR" && npm init -y &>/dev/null)
      ok "已创建 package.json"
    fi
    (cd "$BASE_DIR" && npm install @baiducloud/sdk --no-progress 2>&1 | tail -3)
    ok "@baiducloud/sdk 安装完成"
  else
    warn "Node.js 未安装，跳过 Node.js SDK"
  fi

  # 2. 检查 bcecmd
  echo ""
  echo "--- 步骤 2: 检查 bcecmd ---"
  if check_bcecmd; then
    ok "bcecmd 已就绪"
  else
    echo "  bcecmd 需要手动安装，参考:"
    echo "  https://cloud.baidu.com/doc/BOS/s/Ck1rymwdi"
  fi

  # 3. 持久化凭证到 Skill 数据目录 + 导出环境变量
  echo ""
  echo "--- 步骤 3: 持久化凭证 ---"

  local CRED_DIR="$HOME/.config/openclaw/baidu-cloud-bos"
  local CRED_FILE="$CRED_DIR/credentials.json"
  mkdir -p "$CRED_DIR"

  # 写入 credentials.json
  cat > "$CRED_FILE" <<CREDEOF
{
  "accessKeyId": "$AK",
  "secretAccessKey": "$SK",
  "endpoint": "$ENDPOINT",
  "bucket": "$BUCKET"$([ -n "$STS_TOKEN" ] && echo ",
  \"stsToken\": \"$STS_TOKEN\"")
}
CREDEOF
  chmod 600 "$CRED_FILE"
  ok "凭证已保存到 $CRED_FILE"

  # 同时导出到当前 session
  export BCE_ACCESS_KEY_ID="$AK"
  export BCE_SECRET_ACCESS_KEY="$SK"
  export BCE_BOS_ENDPOINT="$ENDPOINT"
  export BCE_BOS_BUCKET="$BUCKET"
  [ -n "$STS_TOKEN" ] && export BCE_STS_TOKEN="$STS_TOKEN"
  ok "凭证已导出到当前 session"

  # 4. 配置 bcecmd（如果已安装）
  echo ""
  echo "--- 步骤 4: 配置 bcecmd ---"
  if command -v bcecmd &>/dev/null; then
    local BCECMD_CONF="$HOME/.bcecmd"
    mkdir -p "$BCECMD_CONF"

    bcecmd --conf-path "$BCECMD_CONF" configure \
      --access-key "$AK" \
      --secret-key "$SK" \
      --domain "$ENDPOINT" 2>/dev/null && \
      ok "bcecmd 已配置" || \
      warn "bcecmd 配置失败"
  else
    warn "bcecmd 未安装，跳过配置"
  fi

  # 5. 验证连接
  echo ""
  echo "--- 步骤 5: 验证连接 ---"

  local verified=false

  # 优先用 Node.js SDK 验证
  if command -v node &>/dev/null && node -e "require('@baiducloud/sdk')" &>/dev/null 2>&1; then
    if (cd "$BASE_DIR" && node scripts/bos_node.mjs list --max-keys 1 2>/dev/null | grep -q '"success": true'); then
      ok "BOS 连接验证成功（Node.js SDK）"
      verified=true
    fi
  fi

  if [ "$verified" = false ]; then
    warn "BOS 连接验证失败，请检查凭证和网络"
  fi

  echo ""
  echo "=== 设置完成 ==="
  echo "现在可以使用以下方式操作 BOS："
  echo "  方式一: node $BASE_DIR/scripts/bos_node.mjs <action>"
  echo "  方式二: bcecmd bos <command>"
}

# ========== 主入口 ==========

case "$1" in
  --check-only)
    do_check
    ;;
  --ak|--sk|--endpoint|--bucket)
    do_setup "$@"
    ;;
  *)
    echo "百度智能云 BOS Skill 设置工具"
    echo ""
    echo "用法:"
    echo "  $0 --check-only"
    echo "    仅检查环境状态"
    echo ""
    echo "  $0 --ak <AK> --sk <SK> --endpoint <ENDPOINT> --bucket <BUCKET> [--sts-token <TOKEN>]"
    echo "    自动设置环境（安装依赖 + 配置凭证 + 验证连接）"
    ;;
esac
