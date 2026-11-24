# 完整流程与命令

## 从需求到交付

| 阶段 | 云端行为 | 宿主行为 |
| --- | --- | --- |
| 接收 | 创建会话、接收输入文件 | 说明“正在把需求和文件交给伐谋”，只创建一次 |
| 澄清 | 检查数据，返回缺失的业务问题 | 转达问题与选项，保留原约束；回答用 append |
| 方案 | 准备方案并产生待审批事项 | 展示方案摘要、计划链接和执行范围，处理准确的审批 ID |
| 求解 | 执行、评估、生成结果与报告 | 按 `status_markdown` 同步阶段进度，跟随云端完成本轮并收齐交付 |
| 求解交付 | 返回结论及 artifacts | 每份文件独立链接，说明验证与缺失情况 |
| 深度演化 | 用户提出后准备提交，并另行审批 | 展示轮数、GPU和费用估算；授权必须覆盖当前成本 |
| 初始化 | 创建实验后校验提交内容 | 有实验 ID 只说明已登记；初始化 passed 才说明演化已启动 |
| 后台演化 | 独立实验持续运行，可触发新的会话轮次 | 默认交还控制权；明确要求持续跟进才保持 follow |
| 演化交付 | 实验结束、同步结果、分析并生成报告 | 实验完成与报告可交付分别确认，再展示最终结果 |

不要在宿主自行重做云端求解、修造业务结果或凭普通文字猜实验状态。云端模型所说的“已启动”与结构化回执冲突时，以回执为准并说明不确定处。
独立演化可能在会话 idle 后继续；只把本轮结果说清楚，不把 idle、命令退出或观察窗口结束等同整个任务成功。

## 命令用法

所有命令从当前技能自己的 scripts/famou.py 调用，使用 --format json。

```sh
python3 "<skill-dir>/scripts/famou.py" start --text-file "/absolute/request.txt" --file "/absolute/data.csv" --image "/absolute/ref.png" --format json
python3 "<skill-dir>/scripts/famou.py" append SESSION_ID "业务答复" --file "/absolute/more.csv" --format json
python3 "<skill-dir>/scripts/famou.py" confirm SESSION_ID --approval-id APPROVAL_ID --format json
python3 "<skill-dir>/scripts/famou.py" wait SESSION_ID --mode follow --format json
python3 "<skill-dir>/scripts/famou.py" sessions --format json
python3 "<skill-dir>/scripts/famou.py" links SESSION_ID --file-id FILE_ID --format json
```

--file / --image / --file-id 可以重复；单次最多上传 30 个文件或图片，压缩包按解压后总大小校验。--text-file 与直接文字二选一；文件名和文字按宿主的参数机制传递，不拼接未转义的 shell。
--wait-seconds 控制单次观察窗口（10–540秒），不改变云端运行时限。未指定时初始命令用 60 秒、后续 wait 按 120→180→240 秒自适应递增，peek 默认 15 秒；遇到澄清、审批、报错或交付立即返回，不等满窗口。
continuation.argv 已包含运行模式与路径，完整执行即可；interactive 跟随云端完成当前回合，follow 继续跟进后台演化，peek 只观察一次。
--links auto 默认只在交付/交还控制权时签发链接；--links none 用于不需要链接的诊断；--links all 用于本次明确需要查看入口。
已有任务本轮正在运行时，进度查询用 wait；不要用“继续”“查一下”反复 append，避免干扰云端执行。
外部 API Key 不可直接调用实验查询接口（会返回 AccessDenied），wait 回放的是会话事件，返回的 evolution.observed_at 是最后回执时间。
需要更新实验状态而原会话已 idle 且回执陈旧时，可按用户的查询请求在原会话 append 一次“请核对当前实验进度”，再只读 wait；该消息会触发云端一轮工作，不能包装成纯只读操作。

## 澄清与审批

- start 口径保真：转发给 `start` 的文字不得替用户把模糊要求补全成具体的目标函数、优先级权重或未说明的规则；保留模糊处，让云端先查数据再发起澄清。
- clarification：收到 `needs_clarification` 时必须暂停并展示 `clarification_markdown` 中的**全部问题、全部可选项及默认参考**（宿主提问组件不可用时用清晰编号列表）。严禁宿主自行按默认值替用户回答，也不得把“大致原则”当成澄清答案直接 `append`；唯有用户明确指定选项或亲口授权使用默认值时才可提交。
- pending_approval：解释方案、数据范围和可能成本，再根据现有用户授权决定是否 confirm。不是所有“确认”都代表执行批准，也不能拿执行授权去跳过业务澄清。
- evolution_estimate：是冻结积分估算，接口返回时可一并给出当前可用资源点与缺口，不是实际扣费；查询失败明确未知，不能写成0。
- 审批ID必须来自当前回执。旧ID、重复确认或响应丢失都先恢复状态，不能换个ID猜测。
- 深度演化只有用户提出或既有明确授权覆盖时才发起。请求“跑一下求解”不等于同意额外演化。
- 新需求、文件变化或方案变更按原会话 append，重新核对受影响的审批，不创建第二份任务。
