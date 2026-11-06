# AgentCore Code Interpreter 成本测试：HTML/CSV 代码生成（ap-northeast-1）

测试日期：2026-11-05（UTC 10:04 - 10:12）。使用一个内部测试账号（下文记为 `<account-id>`）。
本报告只统计 Code Interpreter 的费用，不含 Claude Opus 5.5 的 token 费用。

## 1. 测试方法

- **执行端**：东京 EC2 bastion `ci-cost-bastion`（t8i.medium），Python venv 加 boto3，使用实例角色访问 AWS。
- **Agent 流程**：用 Bedrock Converse 调用 `global.anthropic.claude-opus-5-5`（maxTokens 16000），工具 `execute_python` 映射到 Code Interpreter 的 `executeCode`。单个请求最多 10 轮。
- **Session 策略**：每个请求新建一个 session。流程为：先 `StartCodeInterpreterSession`，然后由 LLM 循环生成代码并执行，接着 `readFiles` 下载产物，最后立即 `StopCodeInterpreterSession`。
- **Code Interpreter**：使用自定义 `ci_cost_test-Eg0NV2eS7Y`。它的 networkMode 为 SANDBOX，运行时与内置的 `aws.codeinterpreter.v1` 相同。之所以用自定义资源，是因为只有自定义资源可以开启 USAGE_LOGS。
- **沙箱规格**：probe 实测为 2 vCPU、8 GB 内存，Python 3.12，pandas 2.3.1。
- **用量来源**：Code Interpreter vended USAGE_LOGS，每秒一条记录，字段为 `codeInterpreter.vcpu.hours.used` 和 `codeInterpreter.memory.gb_hours.used`，写入日志组 `/aws/vendedlogs/bedrock-agentcore/code-interpreter/ci_cost_test`。
- **交叉校验**：日志合计（34 个 session，含 probe 和 smoke 测试）为 0.028744 vCPU-h 和 0.610635 GB-h。CloudWatch 指标 `AWS/Bedrock-AgentCore` 中 `CPUUsed-vCPUHours` / `MemoryUsed-GBHours` 的同期合计与之完全一致。
- **单价**：来自 Price List API，东京区：

  | usagetype | 单价 |
  |---|---|
  | APN1-CodeInterpreter:Consumption-based:vCPU | $0.0895 / vCPU-hour |
  | APN1-CodeInterpreter:Consumption-based:Memory | $0.00945 / GB-hour |

### 用例（每个用例跑 10 次，3 个并发，30/30 成功）

| 用例 | 内容 | 产物 |
|---|---|---|
| csv_gen | 生成 10,000 行、10 列的模拟订单数据 | orders.csv，约 830 KB，10,001 行 |
| csv_to_html_report | 上传 sales.csv（1 万行），用 pandas 汇总，matplotlib 画 3 张图，以 base64 内嵌进 HTML 报表 | report.html，约 230 KB |
| static_html | 生成单文件响应式落地页（hero、功能区、定价、FAQ），并用 html.parser 校验 | index.html，9 到 18 KB |

## 2. 结果（每个请求的均值）

| 用例 | Session 时长 (s) | 其中 LLM 等待 (s) | 计费秒数 | vCPU·秒 | 平均内存 GB | 峰值 GB | executeCode 次数 | CPU $ | 内存 $ | **合计 $/请求** | P90 $/请求 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| csv_gen | 22.9 | 20.3 | 26.2 | 2.59 | 1.30 | 1.42 | 1.1 | 0.000064 | 0.000091 | **0.000155** | 0.000203 |
| csv_to_html_report | 51.3 | 46.9 | 54.5 | 4.65 | 1.42 | 1.55 | 4.8 | 0.000116 | 0.000205 | **0.000321** | 0.000405 |
| static_html | 60.7 | 59.3 | 63.8 | 2.05 | 1.42 | 1.47 | 1.0 | 0.000051 | 0.000233 | **0.000284** | 0.000367 |
| 30 次合计 | | | | | | | | | | $0.007602 | |

每次 session 的明细见 `results/per_session.csv`，原始运行记录见 `results/runs.jsonl`，生成的文件见 `results/artifacts/`。

## 3. 月度外推（按均值，USD）

| 用例 | 1 万次/月 | 10 万次/月 | 100 万次/月 |
|---|---|---|---|
| csv_gen | 1.55 | 15.51 | 155.07 |
| csv_to_html_report | 3.21 | 32.09 | 320.93 |
| static_html | 2.84 | 28.42 | 284.24 |
| 三类各占 1/3 | 2.53 | 25.34 | 253.42 |

如果按 P90 做预算，大约在上表基础上乘以 1.3。

## 4. 观察

1. **内存费用占大头，占 59% 到 82%。** 沙箱启动后常驻内存约 1.42 GB，空闲时也照样计费。CPU 只在真正执行代码时计费，单个请求只有 2 到 5 vCPU·秒。
2. **大部分计费时间花在等 LLM 上。** 82% 到 94% 的计费秒数里 CPU 接近 0，这段时间 session 只是在等 Opus 生成代码。这部分空闲内存费用分别占各用例总成本的 49%（csv_gen）、54%（report）和 78%（static_html）。static_html 中 LLM 要写约 60 秒的 HTML 才调用一次工具，是最典型的情况。
3. **计费秒数比客户端看到的 session 时长多约 3 秒**，来自 microVM 启动和关闭的开销。每个请求都要承担这部分固定成本，约 $0.00001。
4. **任务计算量很小。** 1 万行 CSV 的读写和 3 张 matplotlib 图，在 2 vCPU 上都在秒级完成。HTML 报表用例需要 4 到 6 次 executeCode（含 LLM 自查和修正），因此 CPU 用量最高。

## 4.1 冷启动延迟（单独测试，不调用 LLM）

脚本为 `bench/cold_start.py`，数据见 `results/cold_start.jsonl`。从东京的 bastion 发起，每个 session 的流程是：先 Start，然后连续执行 `print(1)` 两次，再执行两次 `import pandas, numpy, matplotlib`，最后 Stop。自定义 CI 和内置 `aws.codeinterpreter.v1` 各跑 20 次串行和 10 次并发，共 60 个 session，没有出错。

| 指标（秒，p50 / p90 / max） | 自定义 CI，串行 | 自定义 CI，10 并发 | 内置 CI，串行 | 内置 CI，10 并发 |
|---|---|---|---|---|
| StartCodeInterpreterSession API | 0.85 / 0.92 / 1.33 | 0.89 / 1.46 / 1.49 | 0.85 / 0.94 / 1.32 | 0.91 / 1.05 / 1.50 |
| 第一次 executeCode `print(1)` | 0.16 / 0.18 / 0.18 | 0.16 / 0.17 / 0.18 | 0.15 / 0.18 / 0.21 | 0.16 / 0.17 / 0.17 |
| **Start 到拿到第一个执行结果** | **1.01 / 1.07 / 1.50** | 1.05 / 1.59 / 1.62 | **1.01 / 1.10 / 1.49** | 1.07 / 1.18 / 1.63 |
| 再次 executeCode（热） | 0.10 / 0.12 / 0.13 | 0.12 / 0.13 / 0.13 | 0.10 / 0.12 / 0.18 | 0.09 / 0.12 / 0.13 |
| 首次 import pandas+numpy+matplotlib | 2.37 / 2.70 / 2.84 | 2.45 / 2.66 / 2.79 | 2.48 / 2.80 / 3.26 | 2.46 / 2.56 / 2.72 |
| 再次 import（已缓存） | 0.14 / 0.16 / 0.17 | 0.12 / 0.14 / 0.15 | 0.12 / 0.16 / 0.18 | 0.14 / 0.16 / 0.16 |

- Session 冷启动约 1 秒。Start 返回后，第一次执行的耗时只比热执行多约 0.05 秒，说明 Start 返回时沙箱基本已经就绪。
- 第一次 import pandas 和 matplotlib 要额外花约 2.3 秒，这部分耗时在服务端 `executionTime` 里也能看到。也就是说，涉及数据分析的请求实际要多等约 3.3 秒才能开始干活。
- 自定义 SANDBOX CI 和内置 CI 的延迟没有差别。10 个 session 同时启动时，p90 会多出最多约 0.5 秒。
- 计费侧（来自第 2 节的 USAGE_LOGS）：第一条用量记录出现在客户端调用 Start 后约 1.36 秒（p50 1.34 秒）。最后一条记录比 Stop 返回晚约 3.5 秒（p50 3.56 秒）。因此计费秒数比客户端测到的 session 时长平均多约 3 秒，这部分主要是关闭阶段的开销，按 1.42 GB 内存计约 $0.00001/次。

## 4.2 能否预制环境来减少 import 耗时

数据见 `results/import_variants.json`，脚本为 `bench/import_probe.py` 和 `bench/import_variants.py`。

- **环境本身已经是预制好的。** pandas、numpy、matplotlib 都已预装，`.pyc` 已存在，matplotlib 的字体缓存（fontlist）也已生成。site-packages 是只读的。所以 2.3 秒不是安装或编译造成的，而是在全新的 IPython kernel 里第一次 import 的耗时。
- **Code Interpreter 不支持自定义镜像。** `CreateCodeInterpreter` 只能配置网络、证书、执行角色和文件系统挂载（S3 Files 或 EFS）。挂载一个装好包的 EFS 也帮不上忙，因为包本来就装好了，走网络文件系统只会更慢。如果确实需要自定义镜像，只能改用 AgentCore Runtime 或 Harness 的容器镜像，但那是另一个产品，计费方式也不同。
- **在 kernel 里第一次 import 的耗时分解**（5 个 session 的典型值）：numpy 0.25 秒，pandas 0.80 秒，matplotlib 0.27 秒，pyplot 1.0 秒，合计约 2.3 秒。在同一个沙箱里起一个新的 `python3` 子进程做同样的 import，只要约 0.7 秒。但 kernel 的这部分开销没法控制。
- **换一种 import 写法没有用**（每种 8 个 session，p50）：
  - 先 `matplotlib.use('Agg')` 再 import pyplot：2.33 秒
  - 不用 pyplot，只用 `matplotlib.figure.Figure`：2.22 秒
  - 原来的写法：2.31 秒
- **有效的做法是后台预热。** Start 返回后立即在后台发一个 `executeCode` 执行 import，同时让 LLM 生成第一轮回复（实测这一轮要 16 到 75 秒）。之后 agent 第一次真正执行代码时，服务端 executionTime 的 p50 从 2.31 秒降到 0.01 秒，import 的耗时被完全藏在 LLM 等待里。
  - 成本：如果请求本来就要用 pandas，额外成本基本为 0，因为 import 只是提前做了。如果请求用不到（比如 static_html），会多出大约 2 vCPU·秒的 CPU，加上 import 后多占的内存，估算不超过 $0.0001/请求。这个数字是估算，没有单独计量。
  - 建议只对需要数据处理的请求做预热，比如按路由或意图判断。
- **另一种做法是预热 session 池。** 预先 Start 好 N 个 session 并完成 import，每个请求取一个用，用完就 Stop。这样仍然是每个请求一个 session，同时省掉约 1 秒的启动和 2.3 秒的 import。代价是池里等待的 session 按约 1.45 GB 内存计费，单个 session 一直等着的话约 $0.0137/小时（约 $10/月）。按到达率推算：
  - 100 万次/月时，平均每 2.6 秒来一个请求。3 个 session 的池子，每个 session 平均只等约 8 秒，每个请求多付约 $0.00003，即增加约 10%。
  - 1 万次/月时，平均每 4.3 分钟来一个请求。池里的 session 平均要等几分钟，每个请求多付约 $0.0009，即成本变为原来的约 3 倍，不划算。

## 5. 降本方向（未实测，按以上数据推算）

- **延迟创建 session**：等 LLM 第一次发出 tool_use 时再 Start，拿到产物后立即 Stop。对 static_html 这种“先长时间生成、再执行一次”的场景，单请求成本预计可从约 $0.00028 降到约 $0.00006 到 $0.00008。
- **复用 session**：同一用户的连续请求复用一个 session，可以省掉每次约 3 秒的启动开销。但两次请求之间的空闲内存同样计费，所以要设较短的 `sessionTimeoutSeconds`。这次测试按要求每个请求都新建 session，没有测这种方式。
- 无论哪种方式，都要显式调用 Stop。只靠超时回收的话，session 会一直按约 1.4 GB 内存计费，直到超时（本次设为 900 秒，相当于约 $0.0033/次，是正常请求成本的 10 倍以上）。

## 6. 明天用 Cost Explorer 核对

账户在 2026-10-29 到 11-05 之间没有任何 Code Interpreter 用量，所以 11-05 当天的账单只包含本次测试。

```bash
bench/check_cost_explorer.sh 2026-11-05 2026-11-06
```

11-05 当天的预期值（含 probe 和 smoke 测试，共 34 个 session）：

| usagetype | 预期 UsageQuantity | 预期费用 |
|---|---|---|
| APN1-CodeInterpreter:Consumption-based:vCPU | ≈ 0.0287 vCPU-h | ≈ $0.0026 |
| APN1-CodeInterpreter:Consumption-based:Memory | ≈ 0.6106 GB-h | ≈ $0.0058 |

金额太小，Cost Explorer 可能显示为 $0.00 或 $0.01，所以主要对比 UsageQuantity。官方说明遥测数据仅供参考，实际计费以计量数据为准，两者可能有少量差异。

注意：第 4.1 节的冷启动测试在 11-05 又增加了 60 个短 session，其中 30 个用的是内置 CI，不会写入上面的日志组。所以明天核对时，应以账户级 CloudWatch 指标的全天合计为准：

```bash
for m in CPUUsed-vCPUHours MemoryUsed-GBHours; do
  aws cloudwatch get-metric-statistics --profile test --region ap-northeast-1 --namespace AWS/Bedrock-AgentCore \
    --metric-name $m --dimensions Name=Service,Value=AgentCore.CodeInterpreter \
    --start-time 2026-11-05T00:00:00Z --end-time 2026-11-06T00:00:00Z --period 86400 --statistics Sum \
    --query "Datapoints[0].Sum" --output text
done
```

## 7. 本次创建的资源（测试结束后可清理）

| 资源 | 名称 |
|---|---|
| EC2 | ci-cost-bastion（t8i.medium，30 GB gp3）、ci-cost-openshell（m8i.large，40 GB gp3，开启嵌套虚拟化） |
| 安全组 | ci-cost-bastion-sg，只放行 SSH 来自操作者公网 IP 的 /32 |
| IAM 角色和实例配置文件 | ci-cost-bastion-role |
| 密钥对 | ec2-starter-key |
| Code Interpreter | ci_cost_test（SANDBOX 网络模式） |
| 日志投递 | ci-cost-usage-src / ci-cost-usage-dst，日志组 `/aws/vendedlogs/bedrock-agentcore/code-interpreter/ci_cost_test`（保留 30 天） |

脚本说明见 `README.md`。

## 8. Cost Explorer 核对结果（2026-11-06 拉取，11-05 全天）

| 来源 | vCPU-h | GB-h | 按公开牌价计算 | 实际入账 |
|---|---|---|---|---|
| Cost Explorer | 0.12457226 | 0.98639542 | $0.020471 | $0.006141 |
| CloudWatch 账户级指标 | 0.12457226 | 0.98639542 | $0.020471 | - |
| 自定义 CI 的 USAGE_LOGS（105 个 session） | 0.09639421 | 0.89180470 | $0.017055 | - |
| 内置 CI 的 CloudWatch 指标（30 个 session） | 0.02817806 | 0.09459072 | $0.003416 | - |

- 用量完全一致。本报告用 USAGE_LOGS 按 session 拆出来的用量，就是实际计费的用量。
- 本账户的入账单价正好是公开牌价的 30%（$0.02685/vCPU-h，$0.002835/GB-h）。Cost Explorer 中 RECORD_TYPE 只有 Usage，没有 Credit 行项，说明是账户级的非公开费率。同一账户的 EC2 按需费用约为牌价的 6% 到 8%。报告中的所有成本仍按公开牌价计算。
