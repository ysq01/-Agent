# Stage 12 Ticket Status Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add manual ticket status and resolution updates to the ticket center.

**Architecture:** The backend exposes a ticket-center PATCH route that validates and updates only ticket fields, then returns the same ticket detail model used by the existing detail API. The frontend calls that route from the detail panel, keeps the form business-facing, and reloads detail plus list after a save.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, Pydantic, PostgreSQL test fixtures, React, TypeScript, Vite.

## Global Constraints

- Statuses are `open`, `pending`, `escalated`, `resolved`, and `closed`.
- `resolution` is required for `resolved` and `closed`.
- `resolution` is trimmed and limited to 1000 characters.
- The feature updates only ticket `status` and `resolution`.
- The feature must not change order payment status, order status, refund state, or product stock.
- UI text must be Chinese and business-facing.
- Existing rules evaluation must remain 50/50 passed.

---

### Task 1: Backend API And Validation

**Files:**
- Modify: `backend/app/schemas/tickets.py`
- Modify: `backend/app/services/tickets.py`
- Modify: `backend/app/api/tickets.py`
- Test: `backend/tests/test_dashboard_read_api.py`

**Interfaces:**
- Consumes: existing `TicketDetailResponse` and ticket list/detail service.
- Produces: `TicketStatusUpdateRequest` and `update_ticket_status(session, ticket_number, request) -> TicketDetailResponse`.

- [ ] Write failing tests for valid update, invalid status, required resolution, detail persistence, and unchanged order/payment/product state.
- [ ] Run targeted backend tests and confirm they fail because the route does not exist.
- [ ] Add request schema with status and resolution validation.
- [ ] Add ticket service update function that only mutates ticket fields.
- [ ] Add `PATCH /api/tickets/{ticket_number}/status`.
- [ ] Run targeted backend tests and confirm they pass.

### Task 2: Frontend Ticket Detail Form

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`

**Interfaces:**
- Consumes: `updateTicketStatus(ticketNumber, request)`.
- Produces: detail panel form that calls `onSaved` so the parent reloads current detail and list.

- [ ] Add TypeScript request type for ticket status updates.
- [ ] Add API client function for the PATCH route.
- [ ] Pass a save callback from `TicketsPage` to `TicketDetailPanel`.
- [ ] Add status select, resolution textarea, save button, save state, and Chinese feedback.
- [ ] Reset form when selected ticket changes.
- [ ] Refresh detail and list after save.

### Task 3: Verification

**Files:**
- No source file changes expected unless verification finds a bug.

- [ ] Run `.\.venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider` from `backend`.
- [ ] Run `npm run build` from `frontend`.
- [ ] Run rules evaluation if available without writing blocked reports, or report if the sandbox blocks it.
- [ ] Provide VSCode backend and frontend startup commands.
