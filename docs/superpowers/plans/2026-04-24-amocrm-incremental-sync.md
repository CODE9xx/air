# amoCRM Companies And Incremental Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add real amoCRM company import, incremental post-export updates, and tariff-based automatic sync cadence.

**Architecture:** Keep the current one-DB, per-connection tenant schema model. Reuse the existing `pull_amocrm_core` job with `since_iso` for incremental updates, and add a scheduler tick that enqueues due active connections without running duplicate sync jobs.

**Tech Stack:** FastAPI, SQLAlchemy, RQ, Redis, PostgreSQL tenant schemas, Next.js, TypeScript.

---

### Task 1: Company Import In Existing Pull Job

**Files:**
- Modify: `packages/crm-connectors/src/crm_connectors/amocrm.py`
- Modify: `apps/worker/worker/jobs/crm_pull.py`
- Test: `tests/worker/test_real_export_filters.py`

- [ ] Implement `AmoCrmConnector.fetch_companies(access_token, since=None, limit=None)` using `/api/v4/companies`, `filter[updated_at][from]` for incremental pulls, and safe parsing of name, phone, website, responsible user, timestamps, and raw payload.
- [ ] Add `_pull_companies()` in `crm_pull.py` to upsert into tenant `companies` and `raw_companies`.
- [ ] Call `_pull_companies()` after users and before contacts/deals.
- [ ] Pass `company_map` into `_pull_deals()` and write `company_id` instead of `NULL`.
- [ ] Keep contact-company relation out of scope because tenant `contacts` has no `company_id` column and this pass avoids DB migrations.
- [ ] Extend worker tests to verify company filters, upsert behavior, and deal-company linking.

### Task 2: Incremental Sync Contract

**Files:**
- Modify: `apps/api/app/crm/router.py`
- Modify: `apps/worker/worker/jobs/crm_pull.py`
- Test: `tests/api/test_crm_full_export_billing.py`

- [ ] Change manual `/connections/{id}/sync` to enqueue `pull_amocrm_core` with `since_iso` from `metadata.last_pull_at` or `last_sync_at`.
- [ ] Do not set `cleanup_trial=True` on incremental sync.
- [ ] Do not reserve or charge first-export tokens for incremental sync in this pass.
- [ ] Preserve `active_export` metadata so dashboard filters remain the selected analytics slice.

### Task 3: Tariff-Based Auto Sync Scheduler

**Files:**
- Modify: `apps/worker/worker/scheduler.py`
- Test: `tests/worker/test_scheduler_sync_due.py`

- [ ] Add plan cadence mapping: `free/manual=24h`, `start=24h`, `team=1h`, `pro=15m`, `enterprise=15m`.
- [ ] On each scheduler tick, find active amoCRM connections with `metadata.last_pull_at` old enough for their plan.
- [ ] Skip connections that already have queued/running `pull_amocrm_core` jobs.
- [ ] Enqueue `pull_amocrm_core` with `since_iso`, `auto_sync=True`, and `job_row_id`.
- [ ] Store scheduler enqueue metadata in public `jobs.payload`; do not put secrets or tokens in payload.

### Task 4: Progress And Notifications

**Files:**
- Modify: `apps/worker/worker/jobs/_common.py`
- Modify: `apps/worker/worker/jobs/crm_pull.py`
- Modify: `apps/api/app/jobs/router.py`
- Modify: `apps/web/app/[locale]/app/connections/[id]/page.tsx`

- [ ] Add a helper to merge stage/progress into `jobs.result`.
- [ ] Update progress after pipelines, stages, users, companies, contacts, and deals.
- [ ] Insert a user notification on successful or failed export/sync.
- [ ] Show current job stage, approximate completion, last sync, and next auto sync in the connection page.

### Task 5: Deploy And Verify

**Files:**
- No source file ownership beyond changed files above.

- [ ] Run targeted Python tests.
- [ ] Deploy changed files to `/opt/code9-analytics`.
- [ ] Rebuild/restart `api`, `worker`, and `scheduler` only.
- [ ] Run a safe company backfill/incremental sync for `sm4estro` without deleting tenant schema.
- [ ] Verify tenant counts show non-zero `companies`/`raw_companies` and linked deal `company_id`.
- [ ] Verify no secrets appear in logs, job payloads, job results, or frontend responses.
