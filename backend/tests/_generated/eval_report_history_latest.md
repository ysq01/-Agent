# 客服 Agent 评测报告

- 生成时间：2026-07-16T12:00:00+00:00
- 评测集总数：0
- 通过数：0
- 失败数：0
- 工具调用匹配方式：Deduplicated set exact match over Agent actions.tool_name; None values are ignored.
- 政策命中方式：A case is a policy hit when any expected_policy_keywords value appears in policy_sources.policy_title or policy_sources.source_file.
- 数据库写入策略：The default script runs Agent calls inside an outer database transaction and rolls it back after writing reports, so eval-created or escalated tickets do not persist unless persist mode is explicitly used.

## 指标

| 指标 | 数值 |
| --- | ---: |
| intent_accuracy | 0.00% |
| tool_call_accuracy | 0.00% |
| policy_hit_rate | 0.00% |
| human_escalation_accuracy | 0.00% |
| average_latency_ms | 0.00 |
| auto_resolution_rate | 0.00% |

## 延迟分位

| 指标 | ms |
| --- | ---: |
| p50 | 0.00 |
| p95 | 0.00 |
| max | 0.00 |

## 按 Intent 分组

| intent | total | passed | failed | intent_accuracy | policy_hit_rate | average_latency_ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |

## 失败原因分类

无失败原因。

## 失败案例

无失败案例。
