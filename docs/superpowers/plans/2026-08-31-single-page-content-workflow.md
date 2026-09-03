# Single-Page Content Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a clear, state-driven workflow summary and next action to the existing single-page content preview without changing business logic.

**Architecture:** A pure presentation-state builder maps existing draft, media, publishing mode, and bundle state to four UI steps plus one next action. The Jinja template consumes this state and uses native `details/summary` sections so the current stage is open and all other stages remain available without page proliferation.

**Tech Stack:** Python 3.12, FastAPI, Jinja2, semantic HTML, CSS, pytest

**Spec:** `docs/superpowers/specs/2026-08-31-single-page-content-workflow-design.md`

## Global Constraints

- Preserve all existing routes, database models, media behavior, and publishing service rules.
- Voice remains optional.
- Manual and automatic modes must mirror current `PublishingService` behavior.
- Do not add a frontend framework or dependency.
- The workflow remains usable without JavaScript.

---

### Task 1: Presentation-state builder

**Files:**
- Create: `app/content/workflow.py`
- Create: `tests/content/test_workflow.py`

**Interfaces:**
- Produces: `build_content_workflow(*, draft_status: str, publishing_mode: str, has_original_image: bool, has_edited_image: bool, image_editor_available: bool, has_voice: bool, has_bundle: bool, product_edit_url: str) -> ContentWorkflowState`
- Produces: immutable `WorkflowStep`, `WorkflowAction`, and `ContentWorkflowState` dataclasses.

- [x] Write failing tests for manual approval, manual image generation, automatic packaging, missing image, rejected revision, and ready bundle.
- [x] Run `pytest tests/content/test_workflow.py -q` and verify failure because the module is absent.
- [x] Implement the smallest pure mapping that makes the scenarios pass.
- [x] Run `pytest tests/content/test_workflow.py -q` and verify all scenarios pass.

### Task 2: Route and semantic workflow UI

**Files:**
- Modify: `app/content/routes.py`
- Modify: `app/templates/content/detail.html`
- Modify: `tests/admin/test_content_ui.py`

**Interfaces:**
- Consumes: `ContentWorkflowState` from Task 1.
- Produces: template context key `workflow`.

- [x] Write failing integration tests asserting the overview, one `aria-current="step"`, correct next-action target, and current `details` section opened.
- [x] Run the focused UI tests and verify the new assertions fail against the current page.
- [x] Build `workflow` in `_render_detail` from existing entities and pass it to Jinja.
- [x] Add the status overview and next-action card, then wrap the four existing studios in semantic `details/summary` without changing their forms.
- [x] Run focused UI and route tests and verify they pass.

### Task 3: Focused styling and responsive behavior

**Files:**
- Modify: `app/static/css/app.css`
- Modify: `app/templates/base.html`

**Interfaces:**
- Consumes: `.workflow-overview`, `.workflow-task-list`, `.workflow-step`, `.workflow-next-action`, and `.workflow-section` markup from Task 2.

- [x] Add a failing UI assertion for stable class hooks and status text that does not rely only on color.
- [x] Run the focused test and verify failure.
- [x] Add restrained RTL styles using existing spacing, color, radius, and typography tokens; keep touch targets at least 44px and add mobile stacking.
- [x] Bump the CSS cache key and rerun focused tests.

### Task 4: Full verification

**Files:**
- Test only; no production changes unless verification exposes a regression.

- [x] Run the complete pytest suite.
- [x] Run Ruff, JavaScript syntax checks, Jinja compilation, and `git diff --check`.
- [ ] Test the workflow live in the local browser for initial/manual, approved/image-ready, and bundle-ready states at desktop and narrow widths. (Browser access to localhost was blocked; equivalent route/DOM states are covered by automated tests.)
- [x] Record exact verification results in the handoff.
