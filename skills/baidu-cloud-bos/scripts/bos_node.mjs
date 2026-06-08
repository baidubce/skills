#!/usr/bin/env node
/**
 * 百度智能云 BOS Node.js SDK 操作脚本
 *
 * 依赖：npm install @baiducloud/sdk
 * 凭证读取优先级：
 *   1. 环境变量：BCE_ACCESS_KEY_ID / BCE_SECRET_ACCESS_KEY / BCE_BOS_ENDPOINT / BCE_BOS_BUCKET
 *   2. 配置文件：~/.config/openclaw/baidu-cloud-bos/credentials.json
 *   BCE_STS_TOKEN（可选，临时凭证）
 *
 * 用法：node bos_node.mjs <action> [--option value ...]
 */

import { createRequire } from 'module';
import { createReadStream, readFileSync, writeFileSync, existsSync } from 'fs';
import { basename, resolve, join } from 'path';
import { homedir } from 'os';
import { stat } from 'fs/promises';

const require = createRequire(import.meta.url);
const { BosClient } = require('@baiducloud/sdk');

// 凭证加载：环境变量优先，回退到 ~/.config/openclaw/baidu-cloud-bos/credentials.json
function loadCredentials() {
  let ak = process.env.BCE_ACCESS_KEY_ID;
  let sk = process.env.BCE_SECRET_ACCESS_KEY;
  let endpoint = process.env.BCE_BOS_ENDPOINT;
  let bucket = process.env.BCE_BOS_BUCKET;
  let stsToken = process.env.BCE_STS_TOKEN;

  if (!ak || !sk || !endpoint || !bucket) {
    const credPath = join(homedir(), '.config', 'openclaw', 'baidu-cloud-bos', 'credentials.json');
    if (existsSync(credPath)) {
      try {
        const cred = JSON.parse(readFileSync(credPath, 'utf-8'));
        ak = ak || cred.accessKeyId;
        sk = sk || cred.secretAccessKey;
        endpoint = endpoint || cred.endpoint;
        bucket = bucket || cred.bucket;
        stsToken = stsToken || cred.stsToken;
      } catch (e) {
        // credentials.json 解析失败，忽略
      }
    }
  }

  if (!ak || !sk || !endpoint || !bucket) {
    console.error(JSON.stringify({
      success: false,
      error: '缺少凭证。请通过环境变量设置，或运行 setup.sh 将凭证保存到 ~/.config/openclaw/baidu-cloud-bos/credentials.json',
    }));
    process.exit(1);
  }

  return { ak, sk, endpoint, bucket, stsToken };
}

const { ak: AK, sk: SK, endpoint: ENDPOINT, bucket: BUCKET, stsToken: STS_TOKEN } = loadCredentials();

const config = {
  credentials: {
    ak: AK,
    sk: SK,
  },
  endpoint: ENDPOINT.startsWith('http') ? ENDPOINT : `https://${ENDPOINT}`,
};

if (STS_TOKEN) {
  config.sessionToken = STS_TOKEN;
}

const client = new BosClient(config);

// 解析命令行参数
function parseArgs(args) {
  const result = {};
  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    if (arg.startsWith('--')) {
      const key = arg.slice(2);
      const next = args[i + 1];
      if (next && !next.startsWith('--')) {
        result[key] = next;
        i++;
      } else {
        result[key] = true;
      }
    }
  }
  return result;
}

// 输出 JSON 结果
function output(data) {
  console.log(JSON.stringify(data, null, 2));
}

// ========== 图片处理 ==========

// 图片处理操作注册表：key 是 CLI flag 名，value 是验证+构建函数
// 扩展新操作只需在此添加一个条目
const IMAGE_OPS = {
  bright: (value) => {
    const b = parseInt(value, 10);
    if (isNaN(b) || b < -100 || b > 100) {
      throw new Error('--bright 参数范围：-100 到 100');
    }
    return `image/bright,b_${b}`;
  },
  contrast: (value) => {
    const c = parseInt(value, 10);
    if (isNaN(c) || c < -100 || c > 100) throw new Error('--contrast 参数范围：-100 到 100');
    return `image/contrast,c_${c}`;
  },

  blur: (value) => {
    // 接受 "r,s" 格式（如 "2,50"）或单个数字（r=s）
    const parts = String(value).split(',');
    const r = parseInt(parts[0], 10);
    const s = parseInt(parts[1] ?? parts[0], 10);
    if (isNaN(r) || r < 1 || r > 50) throw new Error('--blur r 参数范围：1 到 50');
    if (isNaN(s) || s < 1 || s > 50) throw new Error('--blur s 参数范围：1 到 50');
    return `image/blur,r_${r},s_${s}`;
  },

  rotate: (value) => {
    const a = parseInt(value, 10);
    if (isNaN(a) || a < -360 || a > 360) throw new Error('--rotate 参数范围：-360 到 360');
    return `image/rotate,a_${a}`;
  },

  'auto-orient': (value) => {
    const o = parseInt(value, 10);
    if (o !== 0 && o !== 1) throw new Error('--auto-orient 参数取值：0 或 1');
    return `image/auto-orient,o_${o}`;
  },
};

/**
 * 从 CLI opts 构建 x-bce-process 字符串。
 * --process 直传优先；否则从便捷 flag 构建并链式合并。
 * 返回 undefined 表示无图片处理。
 */
function buildProcessString(opts) {
  if (opts.process) return opts.process;

  const parts = [];
  for (const [flag, builder] of Object.entries(IMAGE_OPS)) {
    if (opts[flag] !== undefined) {
      parts.push(builder(opts[flag]));
    }
  }

  if (parts.length === 0) return undefined;

  // 多操作链式合并：image/bright,b_-5 + image/resize,w_200 → image/bright,b_-5/resize,w_200
  return parts[0] + parts.slice(1).map(p => '/' + p.replace(/^image\//, '')).join('');
}

// ========== 操作实现 ==========

async function upload(opts) {
  const filePath = opts.file;
  const key = opts.key || basename(filePath);

  if (!filePath) {
    throw new Error('缺少 --file 参数');
  }
  if (!existsSync(filePath)) {
    throw new Error(`文件不存在：${filePath}`);
  }

  const fileInfo = await stat(filePath);
  const buffer = readFileSync(filePath);

  const response = await client.putObject(BUCKET, key, buffer);

  output({
    success: true,
    action: 'upload',
    key,
    etag: response.body?.eTag || response.http_headers?.etag,
    size: fileInfo.size,
    bucket: BUCKET,
  });
}

async function putString(opts) {
  const content = opts.content;
  const key = opts.key;
  const contentType = opts['content-type'] || 'text/plain';

  if (!content) {
    throw new Error('缺少 --content 参数');
  }
  if (!key) {
    throw new Error('缺少 --key 参数');
  }

  const response = await client.putObjectFromString(BUCKET, key, content, {
    'Content-Type': contentType,
  });

  output({
    success: true,
    action: 'put-string',
    key,
    etag: response.body?.eTag || response.http_headers?.etag,
    bucket: BUCKET,
  });
}

async function download(opts) {
  const key = opts.key;
  const outputPath = opts.output || basename(key);

  if (!key) {
    throw new Error('缺少 --key 参数');
  }

  const response = await client.getObjectToFile(BUCKET, key, resolve(outputPath));

  output({
    success: true,
    action: 'download',
    key,
    savedTo: resolve(outputPath),
    bucket: BUCKET,
  });
}

async function list(opts) {
  const prefix = opts.prefix || '';
  const maxKeys = parseInt(opts['max-keys'], 10) || 100;
  const marker = opts.marker || '';

  const options = {};
  if (prefix) options.prefix = prefix;
  if (maxKeys) options.maxKeys = maxKeys;
  if (marker) options.marker = marker;

  const response = await client.listObjects(BUCKET, options);
  const contents = response.body?.contents || [];

  const files = contents.map(item => ({
    key: item.key,
    size: item.size,
    lastModified: item.lastModified,
    eTag: item.eTag,
    storageClass: item.storageClass,
  }));

  output({
    success: true,
    action: 'list',
    prefix,
    count: files.length,
    isTruncated: response.body?.isTruncated || false,
    nextMarker: response.body?.nextMarker || null,
    files,
  });
}

async function signUrl(opts) {
  const key = opts.key;
  const expires = parseInt(opts.expires, 10) || 3600;

  if (!key) {
    throw new Error('缺少 --key 参数');
  }

  const processStr = buildProcessString(opts);
  const params = processStr ? { 'x-bce-process': processStr } : undefined;

  const url = client.generatePresignedUrl(BUCKET, key, 0, expires, undefined, params);

  const result = { success: true, action: 'sign-url', key, expires, url };
  if (processStr) result.process = processStr;

  output(result);
}

async function headObject(opts) {
  const key = opts.key;

  if (!key) {
    throw new Error('缺少 --key 参数');
  }

  const response = await client.getObjectMetadata(BUCKET, key);
  const headers = response.http_headers || {};

  output({
    success: true,
    action: 'head',
    key,
    contentLength: parseInt(headers['content-length'], 10),
    contentType: headers['content-type'],
    eTag: headers.etag,
    lastModified: headers['last-modified'],
    storageClass: headers['x-bce-storage-class'] || 'STANDARD',
    bucket: BUCKET,
  });
}

async function deleteObject(opts) {
  const key = opts.key;

  if (!key) {
    throw new Error('缺少 --key 参数');
  }

  await client.deleteObject(BUCKET, key);

  output({
    success: true,
    action: 'delete',
    key,
    bucket: BUCKET,
  });
}

async function copyObject(opts) {
  const sourceBucket = opts['source-bucket'] || BUCKET;
  const sourceKey = opts['source-key'];
  const key = opts.key;

  if (!sourceKey) {
    throw new Error('缺少 --source-key 参数');
  }
  if (!key) {
    throw new Error('缺少 --key 参数（目标路径）');
  }

  const response = await client.copyObject(sourceBucket, sourceKey, BUCKET, key);

  output({
    success: true,
    action: 'copy',
    sourceBucket,
    sourceKey,
    destBucket: BUCKET,
    destKey: key,
    eTag: response.body?.eTag,
  });
}

async function listBuckets() {
  const response = await client.listBuckets();
  const buckets = (response.body?.buckets || []).map(b => ({
    name: b.name,
    location: b.location,
    creationDate: b.creationDate,
  }));

  output({
    success: true,
    action: 'list-buckets',
    count: buckets.length,
    buckets,
  });
}

// ========== 主入口 ==========

const args = process.argv.slice(2);
const action = args[0];
const opts = parseArgs(args.slice(1));

const actions = {
  upload,
  'put-string': putString,
  download,
  list,
  'sign-url': signUrl,
  head: headObject,
  delete: deleteObject,
  copy: copyObject,
  'list-buckets': listBuckets,
};

if (!action || !actions[action]) {
  output({
    success: false,
    error: `未知操作：${action || '(空)'}`,
    availableActions: Object.keys(actions),
    usage: 'node bos_node.mjs <action> [--option value ...]',
  });
  process.exit(1);
}

try {
  await actions[action](opts);
} catch (err) {
  output({
    success: false,
    action,
    error: err.message || String(err),
    code: err.code,
    statusCode: err.status_code,
  });
  process.exit(1);
}
