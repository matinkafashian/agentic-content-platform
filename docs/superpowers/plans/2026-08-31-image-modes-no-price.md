# No-Price Content and Image Modes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove price from the user-facing product/content flow and add simple studio and cinematic GPT Image 2 edit modes.

**Architecture:** Keep the legacy database column mapped under a compatibility-only name with a zero default, while removing price from forms, schemas, prompts, captions, and views. Send the complete uploaded image to one GPT Image 2 edit request with a mode-specific prompt; do not segment or composite the product.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, Pydantic, Jinja2, httpx, pytest.

**Spec:** `docs/superpowers/specs/2026-08-31-image-modes-no-price-design.md`

## Global Constraints

- Do not add subject extraction, masks, local compositing, or another image service.
- Preserve all unrelated existing worktree changes.
- Write and observe each behavior test fail before changing production code.
- Do not continue to Bale integration.

---

### Task 1: Remove price from product and caption behavior

**Files:**
- Modify: `tests/catalog/test_product_model.py`
- Modify: `tests/catalog/test_product_service.py`
- Modify: `tests/content/test_content_schemas.py`
- Modify: `tests/content/test_template_provider.py`
- Modify: `tests/admin/test_product_routes.py`
- Modify: `app/catalog/models.py`
- Modify: `app/catalog/schemas.py`
- Modify: `app/catalog/routes.py`
- Modify: `app/catalog/service.py`
- Modify: `app/content/schemas.py`
- Modify: `app/content/providers.py`
- Modify: `app/content/openai_provider.py`
- Modify: `app/content/service.py`
- Modify: `app/templates/products/form.html`
- Modify: `app/templates/products/index.html`
- Modify: `app/templates/products/detail.html`
- Modify: `app/templates/content/new.html`
- Modify: `app/templates/content/detail.html`
- Modify: `app/templates/dashboard/index.html`

**Interfaces:**
- Produces: `ProductCreate` and `ProductFacts` without price; captions ending in a support inquiry CTA.

- [ ] Write route, schema, and caption tests asserting price input/output is absent and support inquiry remains.
- [ ] Run the focused tests and verify they fail because current behavior still requires and renders price.
- [ ] Remove price from public schemas/forms/views and map the legacy DB column as compatibility-only zero-valued storage.
- [ ] Remove price from text-model instructions and compose the fixed inquiry CTA with the brand support handle.
- [ ] Run focused catalog/content/admin tests and verify they pass.

### Task 2: Add studio and cinematic prompt contracts

**Files:**
- Modify: `tests/media/test_openai_image_editor.py`
- Modify: `app/media/openai_image_editor.py`

**Interfaces:**
- Produces: `ImageEditInput` validation and `build_product_edit_prompt(edit_input)` for `studio` and `cinematic` modes.

- [ ] Write prompt tests proving studio copy is verbatim and cinematic copy is grounded in the provided topic/message.
- [ ] Run the focused tests and verify they fail because the mode contract does not exist.
- [ ] Implement the two validated mode inputs and mode-specific prompt construction without masks or compositing.
- [ ] Pass the full original image to the existing `/v1/images/edits` request exactly once.
- [ ] Run media tests and verify they pass.

### Task 3: Add the two-mode UI and route validation

**Files:**
- Modify: `tests/admin/test_content_routes.py`
- Modify: `tests/admin/test_content_ui.py`
- Modify: `app/content/routes.py`
- Modify: `app/templates/content/detail.html`
- Modify: `app/static/js/app.js`
- Modify: `app/static/css/app.css`

**Interfaces:**
- Consumes: `OpenAIImageEditor.edit(..., mode, background_style, overlay_text, topic, message)`.
- Produces: a single image form that conditionally exposes only the selected mode fields.

- [ ] Write route/UI tests for required fields, correct editor input, and conditional field markup.
- [ ] Run the focused tests and verify they fail because the current form only supports background style.
- [ ] Update the route to validate the selected mode and preserve existing safe OpenAI error handling.
- [ ] Update the single-page UI with a mode selector and small conditional field groups.
- [ ] Run route/UI tests and verify they pass.

### Task 4: Regression and live diagnosis

**Files:**
- Modify only files proven necessary by a reproduced failure.

**Interfaces:**
- Consumes: existing application test suite and configured OpenAI image API.
- Produces: evidence that all automated tests pass and a reproducible live image result or a logged root cause.

- [ ] Run the complete test suite and lint changed files.
- [ ] Start the app and execute one studio image request through the real web route.
- [ ] If it fails, capture the route log/request ID and add a failing regression test before fixing it.
- [ ] Verify the generated image can be opened in the existing full-image viewer.
