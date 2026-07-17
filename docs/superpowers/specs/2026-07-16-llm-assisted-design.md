# Stage 11 Design: Optional LLM-Assisted Mode

## Summary

Stage 11 adds an optional LLM-assisted mode to the customer service Agent without replacing the existing rule-based state machine. The default path remains deterministic rules mode, and the project must keep running without an API key.

The LLM can help interpret non-standard customer wording and polish the final customer service reply. It cannot execute or authorize refunds, payment updates, inventory changes, or ticket state changes. All business facts still come from tool APIs, PostgreSQL, and Qdrant policy retrieval. All high-risk decisions still come from deterministic rules and tool validation.

## Goals

- Keep `rules` mode as the default baseline.
- Add `llm_assisted` as an optional mode selected by environment configuration or a front-end preference.
- Let customer service staff toggle "智能增强" in the workbench and persist that preference in `localStorage`.
- Fall back to the existing rules output when there is no API key, the LLM call times out, or the LLM response is invalid.
- Preserve the refund safety boundary in every refund reply: the system only provides review recommendations and does not perform refunds, payment changes, or inventory changes.
- Keep the existing 50-case rules evaluation baseline passing.

## Non-Goals

- Do not replace the rule state machine.
- Do not introduce LangGraph.
- Do not let the LLM select or execute business tools.
- Do not expose API keys, model names, raw JSON, internal tool names, or developer diagnostics in the customer service front end.
- Do not persist Agent traces to the database as part of this stage.
- Do not add user account or server-side preference storage.

## User Experience

The customer service workbench adds a compact business-facing toggle named "智能增强".

When enabled, the preference is saved in browser `localStorage`. Future visits keep the same setting. When disabled, that disabled state is also saved. The next Agent request includes the selected mode.

The UI should describe the feature in business language only, for example:

- Enabled: "辅助理解表达并优化回复"
- Disabled: "使用稳定规则处理"

The result panel remains business-oriented. It continues to show problem type, handling method, confidence, linked ticket, reply, and referenced policies. It does not show LLM provider, model, API key status, tool names, raw actions, or JSON.

## API Shape

`AgentProcessRequest` gains an optional `mode` field:

```text
mode: "rules" | "llm_assisted" | null
```

`AgentProcessResponse` remains unchanged to preserve existing front-end behavior and existing API shape tests.

Mode resolution:

- If request mode is `rules`, run deterministic rules mode.
- If request mode is `llm_assisted`, attempt optional LLM assistance.
- If request mode is omitted, read `AGENT_MODE`.
- Invalid or unsupported values are rejected by schema validation.
- If resolved mode is `llm_assisted` but the LLM is unavailable, use rules output.

## Backend Components

### Configuration

Environment variables:

- `AGENT_MODE=rules|llm_assisted`, default `rules`
- `DASHSCOPE_API_KEY`, optional
- `DASHSCOPE_MODEL`, optional, default `qwen-plus`
- `DASHSCOPE_BASE_URL`, optional, default `https://dashscope.aliyuncs.com/compatible-mode/v1`
- `DASHSCOPE_TIMEOUT_SECONDS`, optional conservative timeout

### LLM Client

Add a small `backend/app/services/llm_client.py` module.

Responsibilities:

- Read optional Alibaba Cloud DashScope configuration from the environment.
- Return `None` when no API key is configured.
- Use a short timeout.
- Catch network, timeout, parsing, and provider errors.
- Expose narrow helper methods:
  - `classify_intent_with_llm(message: str) -> AgentIntent | None`
  - `polish_reply_with_llm(message: str, rule_reply: str, intent: AgentIntent, need_human: bool) -> str | None`

The client should use only standard-library HTTP facilities unless an existing runtime dependency is already available. It must not add a mandatory SDK dependency for this stage. The HTTP call uses Alibaba Cloud Model Studio's OpenAI-compatible chat completions endpoint.

### Agent Workflow Integration

The workflow keeps the same node order:

```text
intent_classification
information_check
policy_retrieval
tool_selection
business_action
response_generation
trace_recording
```

The LLM can be consulted inside the existing intent classification step after the rules classifier runs. The rules result remains authoritative unless the rule confidence is low or the rules classify the message as `other`. The LLM result may only set one of the existing allowed intents.

The LLM can be consulted after deterministic response generation to polish the final reply. The final reply must still preserve required safety wording for refund scenarios. If the polished reply removes or weakens the refund safety wording, discard it or append the required safety sentence.

No LLM output can change:

- selected tools
- tool results
- database writes
- refund eligibility
- refund amount
- payment status
- inventory state
- ticket status

### Safety Guardrails

Refund-related business behavior remains deterministic:

- `check_refund_eligibility` only returns review advice.
- Payment status is not changed.
- Inventory is not changed.
- The response must state that no real refund, payment change, or inventory change is performed.

The LLM prompt must explicitly state that it is not allowed to approve, reject, execute, or imply execution of a refund. The implementation also enforces this outside the prompt by preserving deterministic tool selection and mandatory safety wording.

## Evaluation

Rules evaluation remains the default:

```powershell
.\.venv\Scripts\python.exe -m scripts.run_eval
```

`run_eval` may gain:

```text
--mode rules|llm_assisted
```

Default is `rules`, preserving the current baseline and output behavior. In `llm_assisted` mode, missing API keys or LLM failures should not fail the evaluation; they fall back to rules.

If evaluation reports include mode metadata, it should be added in a backward-compatible way. The front-end quality center can continue reading existing reports without requiring mode-specific UI in this stage.

## Tests

Add focused backend tests:

- No `DASHSCOPE_API_KEY` with `llm_assisted` falls back to the same rules result.
- LLM exception during classification or polishing falls back to rules output.
- LLM-suggested high-risk behavior cannot add tools or change tool execution.
- Refund safety wording remains present after LLM-assisted response generation.
- Request mode schema accepts `rules` and `llm_assisted` and rejects invalid values.

Keep existing tests passing, including the API response shape test.

Frontend verification:

- `npm run build`
- Type checks pass after adding request mode and persisted toggle.

Backend verification:

- `.\.venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider`
- Optional: `.\.venv\Scripts\python.exe -m scripts.run_eval --mode rules`

## Documentation Updates

Update README, architecture, and demo guide after implementation:

- Document `AGENT_MODE`, `DASHSCOPE_API_KEY`, `DASHSCOPE_MODEL`, and `DASHSCOPE_BASE_URL`.
- Clarify that `rules` remains default.
- Clarify that no API key is required for local demo.
- Explain the front-end "智能增强" toggle and fallback behavior.
- Restate refund/payment/inventory safety boundaries.

## Open Decisions

All implementation choices needed for this stage are resolved:

- Front-end preference storage uses `localStorage`.
- Back-end response shape remains unchanged.
- LLM usage is limited to intent assistance and reply polishing.
- Rules evaluation remains default.
