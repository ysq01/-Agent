# 客服 Agent 评测报告

- 生成时间：2026-07-16T14:52:26.086793+00:00
- 评测集总数：50
- 通过数：49
- 失败数：1
- 工具调用匹配方式：Deduplicated set exact match over Agent actions.tool_name; None values are ignored.
- 政策命中方式：A case is a policy hit when any expected_policy_keywords value appears in policy_sources.policy_title or policy_sources.source_file.
- 数据库写入策略：The default script runs Agent calls inside an outer database transaction and rolls it back after writing reports, so eval-created or escalated tickets do not persist unless persist mode is explicitly used.

## 指标

| 指标 | 数值 |
| --- | ---: |
| intent_accuracy | 98.00% |
| tool_call_accuracy | 100.00% |
| policy_hit_rate | 100.00% |
| human_escalation_accuracy | 98.00% |
| average_latency_ms | 2051.39 |
| auto_resolution_rate | 60.00% |

## 延迟分位

| 指标 | ms |
| --- | ---: |
| p50 | 2064.05 |
| p95 | 2866.75 |
| max | 3244.83 |

## 按 Intent 分组

| intent | total | passed | failed | intent_accuracy | policy_hit_rate | average_latency_ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| refund_request | 12 | 12 | 0 | 100.00% | 100.00% | 2393.72 |
| shipping_issue | 8 | 8 | 0 | 100.00% | 100.00% | 2318.87 |
| invoice_request | 7 | 7 | 0 | 100.00% | 100.00% | 1829.28 |
| complaint | 8 | 8 | 0 | 100.00% | 100.00% | 1471.29 |
| account_issue | 5 | 5 | 0 | 100.00% | 100.00% | 1720.17 |
| other | 10 | 9 | 1 | 90.00% | 100.00% | 2211.77 |

## 失败原因分类

| reason | count |
| --- | ---: |
| intent_mismatch | 1 |
| human_escalation_mismatch | 1 |

## 失败案例

| id | expected_intent | actual_intent | expected_tools | actual_tools | failure_reasons |
| --- | --- | --- | --- | --- | --- |
| EVAL-044 | other | refund_request | search_policy | search_policy | intent mismatch: expected other, got refund_request; need_human mismatch: expected False, got True |
