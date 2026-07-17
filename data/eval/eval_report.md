# 客服 Agent 评测报告

- 生成时间：2026-07-16T06:40:54.683144+00:00
- 评测集总数：50
- 通过数：50
- 失败数：0
- 工具调用匹配方式：Deduplicated set exact match over Agent actions.tool_name; None values are ignored.
- 政策命中方式：A case is a policy hit when any expected_policy_keywords value appears in policy_sources.policy_title or policy_sources.source_file.
- 数据库写入策略：The default script runs Agent calls inside an outer database transaction and rolls it back after writing reports, so eval-created or escalated tickets do not persist unless persist mode is explicitly used.

## 指标

| 指标 | 数值 |
| --- | ---: |
| intent_accuracy | 100.00% |
| tool_call_accuracy | 100.00% |
| policy_hit_rate | 100.00% |
| human_escalation_accuracy | 100.00% |
| average_latency_ms | 43.21 |
| auto_resolution_rate | 62.00% |

## 延迟分位

| 指标 | ms |
| --- | ---: |
| p50 | 34.33 |
| p95 | 56.70 |
| max | 481.04 |

## 按 Intent 分组

| intent | total | passed | failed | intent_accuracy | policy_hit_rate | average_latency_ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| refund_request | 12 | 12 | 0 | 100.00% | 100.00% | 73.30 |
| shipping_issue | 8 | 8 | 0 | 100.00% | 100.00% | 28.18 |
| invoice_request | 7 | 7 | 0 | 100.00% | 100.00% | 41.55 |
| complaint | 8 | 8 | 0 | 100.00% | 100.00% | 43.03 |
| account_issue | 5 | 5 | 0 | 100.00% | 100.00% | 25.91 |
| other | 10 | 10 | 0 | 100.00% | 100.00% | 29.08 |

## 失败原因分类

无失败原因。

## 失败案例

无失败案例。
