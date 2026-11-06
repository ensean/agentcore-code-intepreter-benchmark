# 样例：Claude Opus 5.5 生成的代码与 Code Interpreter 产物

采集时间 2026-11-05。每个用例跑 1 次，并记录完整 transcript，流程与成本压测相同，只是多存了代码。成本压测那 30 次的全部产物在 `../results/artifacts/`。

| 用例 | 生成的代码 | 产物 | 完整 transcript（prompt、每步代码、stdout、最终回答） |
|---|---|---|---|
| csv_gen | `code/csv_gen-1-step1.py`（生成数据）<br>`code/csv_gen-1-step2.py`（校验） | `artifacts/csv_gen-1-orders.csv`（10,001 行，约 827 KB） | `transcripts/csv_gen-1.json` |
| csv_to_html_report | `code/csv_to_html_report-1-step1.py`、`step2.py`（探查数据）<br>`code/csv_to_html_report-1-step3.py`（汇总、画图、输出 HTML） | `artifacts/csv_to_html_report-1-report.html`（约 229 KB，内嵌 3 张 base64 PNG）<br>输入文件：`artifacts/csv_to_html_report-input-sales.csv` | `transcripts/csv_to_html_report-1.json` |
| static_html | `code/static_html-1-step1.py`（用 Python 写出 HTML 并做校验，约 17.5 KB） | `artifacts/static_html-1-index.html`（约 16 KB） | `transcripts/static_html-1.json` |

本地查看：`open artifacts/csv_to_html_report-1-report.html`
