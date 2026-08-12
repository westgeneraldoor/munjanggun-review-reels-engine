# Durable Render Jobs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make official production renders survive Codex/tool wait limits and expose durable, evidence-bound progress through `render-start` and `render-status`.

**Architecture:** The orchestrator validates the existing hard gate, creates a one-use receipt and an immutable-bound job record, then detaches a fixed repository worker. The worker alone constructs the approved renderer command, updates `render_job.json` atomically, preserves all failure evidence, and records the final MP4 hash only after success. `render-status` refreshes progress from the job's own frame directory without launching or mutating any production artifact.

**Tech Stack:** Python 3.11 standard library, Node.js renderer, `unittest`, Windows detached process flags with POSIX session fallback.

## Global Constraints

- The official agent production path is `render-start` followed by `render-status`; synchronous `render` remains compatibility-only.
- A caller cannot inject an arbitrary renderer command into a production job.
- Job evidence lives only at `<package>/_work/render_jobs/<job-id>/` and is written atomically.
- Every job binds package, HTML/artifact approval, sync/privacy inputs, receipt, output path, and final preset hashes/values.
- States are exactly `queued`, `running`, `succeeded`, or `failed`; progress is `rendered_frames / expected_frames`.
- A failed job preserves its consumed receipt, partial frame directory, log, and failure record. Retry requires a new job ID, receipt, and output filename.
- Version 1 does not resume partial frames.
- Post-render QA is permitted only after `succeeded` includes final MP4 bytes and SHA-256.

---

### Task 1: Durable job record and progress model

**Files:**
- Create: `video_engine_v2/render_job.py`
- Create: `tests/test_render_job.py`

**Interfaces:**
- Produces: `create_job_record(...) -> Path`, `read_job(path) -> dict`, `update_job(path, **changes) -> dict`, `refresh_progress(path) -> dict`, `sha256_file(path) -> str`.
- The record stores immutable `bindings`, lifecycle fields, renderer/worker PIDs, frame paths, log path, expected/rendered frames, output evidence, and failure evidence.

- [ ] **Step 1: Write failing tests for atomic creation, path containment, exact state vocabulary, progress counting, and output evidence.**
- [ ] **Step 2: Run `python -m unittest tests.test_render_job -v`; expect import or missing-interface failures.**
- [ ] **Step 3: Implement the minimal model with `NamedTemporaryFile`, `fsync`, and `os.replace`; reject paths outside the package job root.**
- [ ] **Step 4: Re-run `python -m unittest tests.test_render_job -v`; expect all Task 1 tests to pass.**
- [ ] **Step 5: Commit `test: define durable render job state`.**

### Task 2: Detached worker and official CLI

**Files:**
- Create: `scripts/render_review_v2_job.py`
- Modify: `scripts/produce_review_v2.py`
- Modify: `tests/test_render_job.py`
- Modify: `tests/test_produce_review_v2.py`

**Interfaces:**
- Produces: `build_render_command(job) -> list[str]`, `run_job(job_path) -> int`, `spawn_detached_worker(job_path) -> int`.
- CLI adds `render-start` with the existing render inputs and `render-status --package --job-id`.
- The worker accepts only `--job`; all executable/script/preset values are fixed by repository code and validated bindings.

- [ ] **Step 1: Add failing tests proving the parent returns before a real short child finishes, a success records MP4 bytes/hash, a failure preserves frames/log/receipt, and parser commands exist.**
- [ ] **Step 2: Run the two targeted test modules; expect missing worker/CLI failures.**
- [ ] **Step 3: Implement cross-platform detached launch (`DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW` on Windows, `start_new_session=True` elsewhere), UTF-8 environment, fixed worker invocation, and atomic lifecycle updates.**
- [ ] **Step 4: Implement `render-start` by reusing `validate_render_gate`/`write_gate_receipt`, deriving expected frames from the verified sync duration at 30 fps, creating the job, spawning the worker, and printing machine-readable JSON.**
- [ ] **Step 5: Implement `render-status` with contained job lookup, current frame count, PID liveness check, and machine-readable JSON; never delete or resume artifacts.**
- [ ] **Step 6: Run `python -m unittest tests.test_render_job tests.test_produce_review_v2 -v`; expect pass.**
- [ ] **Step 7: Commit `feat: add durable background render jobs`.**

### Task 3: Authority docs and regression gates

**Files:**
- Modify: `AGENTS.md`
- Modify: `README.md`
- Modify: `docs/review_video_publish_workflow_v2.md`
- Modify: `docs/review_reels_one_shot_contract_v2.md`
- Modify: `docs/render_qa_rules_v2.md`
- Modify: `tests/test_authority_documents.py`

**Interfaces:**
- Live authority docs expose the same `render-start` and `render-status` commands and describe synchronous `render` as diagnostics/compatibility only.
- Authority tests prevent a return to a fixed foreground wait as the official agent path.

- [ ] **Step 1: Add failing authority tests requiring both new commands, job-state/evidence language, and the compatibility-only label for synchronous render.**
- [ ] **Step 2: Run the targeted authority tests; expect failures against current live docs.**
- [ ] **Step 3: Update only the existing live authority documents; do not create another standard document.**
- [ ] **Step 4: Re-run targeted authority tests; expect pass.**
- [ ] **Step 5: Commit `docs: make background jobs the render standard`.**

### Task 4: Full verification and delivery

**Files:**
- Verify all modified files and generated Git metadata only.

**Interfaces:**
- Produces a clean feature branch and CI-backed pull request; no customer media or local output is staged.

- [ ] **Step 1: Run `python -m unittest discover -s tests`.**
- [ ] **Step 2: Run `npm run validate` and `git diff --check`.**
- [ ] **Step 3: Inspect staged paths and confirm no `.env`, `reviews/`, `output/`, media, fonts, dependencies, or job evidence is tracked.**
- [ ] **Step 4: Push `codex/background-render-job`, create a ready PR, wait for CI, and merge only after green verification.**
