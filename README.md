# AgentCore Code Interpreter 成本 PoC：HTML/CSV 代码生成

本 PoC 测量 Amazon Bedrock AgentCore Code Interpreter 在“LLM 生成代码、沙箱执行、产出 HTML 或 CSV 文件”这一场景下的冷启动时间、执行耗时和成本，并与在 EC2 上自建 [NVIDIA OpenShell](https://github.com/NVIDIA/OpenShell) 沙箱的方案做对比。

- 区域：ap-northeast-1（东京）
- 代码生成模型：Claude Opus 5.5（`global.anthropic.claude-opus-5-5`）
- 测试日期：2026-11-05
- 成本口径：只统计 Code Interpreter 的费用，不含模型 token 费用

完整报告见 [`REPORT.md`](REPORT.md)。

## 主要结果

| 指标 | 结果 |
|---|---|
| 单请求成本（每个请求新建 session，按公开牌价） | csv_gen $0.000155，csv_to_html_report $0.000321，static_html $0.000284 |
| 月度成本（三类用例各占 1/3） | 1 万次 $2.53，10 万次 $25.34，100 万次 $253.42 |
| 成本构成 | 内存费用占 59% 到 82%。82% 到 94% 的计费秒数在等 LLM，这段时间 CPU 接近 0 |
| 冷启动（Start 到拿到第一个执行结果，p50 / p90） | 1.01 s / 1.10 s，自定义与内置 Code Interpreter 相同 |
| 首次 import pandas+numpy+matplotlib | 约 2.3 s。在后台预热后，agent 首次执行代码的耗时降到 0.01 s |
| 账单核对 | Cost Explorer 的用量与 CloudWatch 指标、USAGE_LOGS 一致到小数点后 8 位 |
| 自建 OpenShell（MicroVM，p50） | 冷启动 1.24 s，每个沙箱约 0.25 GB 内存。2 台 m8i.large 做高可用约 $207/月，按本次混合用例，约 82 万次/月以下 Code Interpreter 更便宜 |

## 目录结构

```
.
├── REPORT.md                       完整报告
├── infra/                          创建测试资源（AWS CLI）
│   ├── create-bastion.sh           压测机 EC2、IAM 角色、安全组（SSH 只放行操作者 /32）
│   ├── create-code-interpreter.sh  自定义 Code Interpreter（SANDBOX），并把 USAGE_LOGS 投递到 CloudWatch Logs
│   └── create-openshell-host.sh    自建对比用的 Ubuntu 24.04 主机
├── bench/                          Code Interpreter 测试与分析
│   ├── run_bench.py                主压测：Opus 生成代码，Code Interpreter 执行，每个请求新建 session
│   ├── export_usage_logs.sh        导出 USAGE_LOGS（每个 session 每秒一条用量记录）
│   ├── analyze.py                  按 session 汇总用量和成本，并外推月度成本
│   ├── reconcile.py                对比压测脚本记录的时间、USAGE_LOGS 和成本估算
│   ├── cold_start.py               冷启动测试（自定义和内置，串行和并发）
│   ├── import_probe.py             首次 import 的耗时分解
│   ├── import_variants.py          不同 import 写法和后台预热的对比
│   ├── probe.py                    查看 Code Interpreter API 响应格式
│   ├── check_cost_explorer.sh      查 Cost Explorer 的按天用量和金额
│   └── ci_region_prices.py         查各区域 Code Interpreter 单价（Price List API）
├── selfhost/                       自建 OpenShell 对比
│   ├── Dockerfile                  沙箱镜像（Python 3.12、pandas 2.3.1、numpy、matplotlib）
│   ├── bench_openshell.sh          冷启动、执行耗时和内存密度测试
│   ├── cost_model.py               自建与 Code Interpreter 的月度成本模型
│   └── results_openshell*.jsonl    Docker 和 MicroVM 驱动的测试结果
├── results/                        测试数据（已脱敏）
│   ├── runs.jsonl                  30 次压测的记录
│   ├── per_session.csv             每个 session 的用量和成本
│   ├── summary.json                各用例成本统计
│   ├── cold_start.jsonl            冷启动测试结果
│   └── import_variants.json        import 写法对比结果
└── samples/                        每个用例一个样例：生成的代码、产物和完整对话记录
```

以下内容不在仓库里，见 [`.gitignore`](.gitignore)：

| 内容 | 原因 | 如何获取 |
|---|---|---|
| `results/usage_logs*.json` | 原始 USAGE_LOGS 包含账号 ID 和资源 ARN | 运行 `bench/export_usage_logs.sh` 重新导出 |
| `results/artifacts/` | 30 次压测的全部产物，约 10 MB | `run_bench.py` 运行时生成；`samples/` 里保留了每个用例一份 |
| `draft_*_folder/` | 飞书文档的草稿和回查内容 | 不需要 |
| 密钥、`.env`、`.venv`、`__pycache__`、`.DS_Store` | 敏感信息或本地文件 | 不需要 |

## 复现步骤

### 前提条件

- AWS CLI v2。命令行 profile 默认为 `test`，可以用 `AWS_PROFILE` 和 `AWS_REGION` 覆盖。
- 账号已开通 Bedrock 中 Claude Opus 5.5 的访问权限，并允许在 ap-northeast-1 使用 AgentCore Code Interpreter。
- 一对 SSH 密钥。公钥会以 `KEY_NAME` 的名称导入，默认为 `ec2-starter-key`。

### 1. 创建资源

```bash
PUB_KEY=~/.ssh/my-key.pub ./infra/create-bastion.sh   # 输出实例 ID 和公网 IP
./infra/create-code-interpreter.sh                   # 输出 CI_ID=ci_cost_test-xxxxxxxx
```

安全组只放行运行脚本这台机器当前的公网 IP。出口 IP 变了的话，需要更新安全组规则。

### 2. 在压测机上跑测试

压测机是 Amazon Linux 2023，系统 Python 是 3.9，脚本里已经加了 `from __future__ import annotations`。依赖装在 venv 里：

```bash
scp -i <key> bench/*.py ec2-user@<ip>:ci-cost/
ssh -i <key> ec2-user@<ip>
cd ~/ci-cost && python3 -m venv .venv && .venv/bin/pip install boto3
mkdir -p main && cd main
../.venv/bin/python ../run_bench.py <CI_ID> 10 3        # 每个用例 10 次，3 个并发
../.venv/bin/python ../cold_start.py <CI_ID> 20 10      # 冷启动；把 <CI_ID> 换成 aws.codeinterpreter.v1 可测内置版本
../.venv/bin/python ../import_variants.py <CI_ID> 8
```

把 `results/runs.jsonl` 和 `cold_start.jsonl` 等结果拷回本地的 `results/` 目录。

### 3. 汇总用量和成本

USAGE_LOGS 最多延迟约 60 分钟。

```bash
bench/export_usage_logs.sh <start-epoch-ms> <end-epoch-ms>   # 生成 results/usage_logs_full_day.json
python3 bench/analyze.py                                     # 每个 session 的成本、各用例统计、月度外推
python3 bench/reconcile.py                                   # 压测脚本记录的时间与 USAGE_LOGS 的对比
```

### 4. 第二天核对账单

```bash
bench/check_cost_explorer.sh 2026-11-05 2026-11-06
```

对比 Cost Explorer 的 UsageQuantity 和 CloudWatch 指标 `AWS/Bedrock-AgentCore` 中 `CPUUsed-vCPUHours`、`MemoryUsed-GBHours` 的全天合计。

### 5. 自建 OpenShell 对比（可选）

```bash
SG_ID=<sg> SUBNET_ID=<subnet> ./infra/create-openshell-host.sh m8i.large
```

在主机上依次完成以下步骤：

1. 安装 Docker Engine 和 OpenShell（`curl -LsSf https://raw.githubusercontent.com/NVIDIA/OpenShell/main/install.sh | sh`）。
2. 在 `~/.config/openshell/gateway.toml` 中设置 `compute_driver`（`docker` 或 `vm`），然后用 `openshell gateway add https://127.0.0.1:17670 --local` 注册网关。
3. 构建镜像：`docker build -t ci-sandbox:py312 selfhost/`。
4. 运行测试：`./selfhost/bench_openshell.sh 15 10`。

MicroVM 驱动需要 KVM。在 EC2 上要用 m8i、c8i、r8i 这些支持嵌套虚拟化的机型，并在实例停止时执行 `aws ec2 modify-instance-cpu-options --nested-virtualization enabled`。

成本模型可以离线运行，修改文件顶部的假设后重跑即可：

```bash
python3 selfhost/cost_model.py
```

## 注意事项

- 报告中的成本都按公开牌价计算：$0.0895/vCPU-h，$0.00945/GB-h，14 个商业区域价格相同。本测试账号的实际入账单价是牌价的 30%，不代表一般客户的价格。有协议价的客户要用自己的单价重算。
- 结论基于单区域、一天的测试和小规模合成任务。自建成本模型中的峰值系数、每个沙箱的内存预留等是假设，而且没有计入运维人力。
- 只有自定义 Code Interpreter 能开启 USAGE_LOGS。内置的 `aws.codeinterpreter.v1` 只能通过 CloudWatch 指标查看用量。

## 清理资源

```bash
AWS="aws --profile test --region ap-northeast-1"
$AWS ec2 terminate-instances --instance-ids <bastion-id> <openshell-id>
$AWS logs delete-delivery --id <delivery-id>          # 用 aws logs describe-deliveries 查找
$AWS logs delete-delivery-source --name ci-cost-usage-src
$AWS logs delete-delivery-destination --name ci-cost-usage-dst
$AWS logs delete-log-group --log-group-name /aws/vendedlogs/bedrock-agentcore/code-interpreter/ci_cost_test
$AWS bedrock-agentcore-control delete-code-interpreter --code-interpreter-id <CI_ID>
$AWS ec2 delete-security-group --group-id <sg-id>     # 实例终止后再删
aws --profile test iam remove-role-from-instance-profile --instance-profile-name ci-cost-bastion-role --role-name ci-cost-bastion-role
aws --profile test iam delete-instance-profile --instance-profile-name ci-cost-bastion-role
aws --profile test iam delete-role-policy --role-name ci-cost-bastion-role --policy-name ci-cost-test
aws --profile test iam detach-role-policy --role-name ci-cost-bastion-role --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
aws --profile test iam delete-role --role-name ci-cost-bastion-role
```
