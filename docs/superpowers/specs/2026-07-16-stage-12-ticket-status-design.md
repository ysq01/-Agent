# Stage 12 Ticket Status Design

## Goal

Let customer service agents update ticket status and resolution from the ticket center detail panel while keeping all high-risk order, inventory, payment, and refund state unchanged.

## Scope

- Add a manual ticket status update flow in the ticket center.
- Support statuses: `open`, `pending`, `escalated`, `resolved`, `closed`.
- Support editing `resolution`.
- Refresh the selected ticket detail and ticket list after save.
- Keep the frontend business-facing and Chinese-language only.
- Do not expose API names, tool names, database field names, JSON, or developer diagnostics in the UI.

## Backend Design

- Add `PATCH /api/tickets/{ticket_number}/status`.
- Request body: `{ "status": string, "resolution"?: string }`.
- Reuse the existing ticket status update service where practical.
- Validate status against the allowed set.
- Trim `resolution` before saving.
- Limit `resolution` to 1000 characters.
- Require non-empty `resolution` when status is `resolved` or `closed`.
- Return the updated ticket detail shape used by the ticket center.
- Update only the ticket record. Do not modify order status, payment status, refund status, or product stock.

## Frontend Design

- Add a processing form to `TicketDetailPanel`.
- Controls:
  - Status dropdown with Chinese labels.
  - Resolution textarea.
  - Save button.
- Reset form values when the selected ticket changes.
- Disable save while submitting.
- Show Chinese success and failure messages.
- After a successful save, reload the selected ticket detail and the left ticket list.
- Resolved and closed tickets remain visible and selectable.

## Safety Boundaries

- No real refunds.
- No payment status changes.
- No inventory changes.
- No refund status changes.
- This is a manual customer service action, not an AI automation.
- Agent workflows must not use this feature to close tickets without human confirmation.
- Existing rules evaluation must remain 50/50 passed.

## Validation

- Backend tests cover valid updates, invalid status rejection, resolution persistence, required resolution for `resolved` and `closed`, and unchanged order/payment/inventory data.
- Frontend build must pass.
- Backend test suite must pass.
- Rules evaluation should remain green.
