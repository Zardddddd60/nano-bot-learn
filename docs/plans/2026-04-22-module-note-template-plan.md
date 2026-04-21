# Module Note Template Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a reusable lightweight module-note template and reference it from `AGENTS.md`.

**Architecture:** Keep the change documentation-only. Create one markdown template under `docs/` and update `AGENTS.md` so future module notes follow the same compact structure.

**Tech Stack:** Markdown, repository conventions

---

### Task 1: Add the reusable template

**Files:**
- Create: `docs/_template_module_note.md`

**Step 1: Write the template**

Include these sections only:
- Module path
- Related Python points
- Module purpose
- Paths
- Storage / protocol
- Key concepts
- Basic flow
- What to remember

**Step 2: Verify the file content**

Run: `sed -n '1,220p' docs/_template_module_note.md`
Expected: the template is present and compact.

### Task 2: Reference the template from AGENTS.md

**Files:**
- Modify: `AGENTS.md`

**Step 1: Update the learning-note convention**

Add one line under the development workflow that future notes should follow the template at `docs/_template_module_note.md`.

**Step 2: Verify the file content**

Run: `sed -n '1,220p' AGENTS.md`
Expected: the template reference is visible in the workflow section.

### Task 3: Final verification

**Files:**
- Verify: `docs/_template_module_note.md`
- Verify: `AGENTS.md`

**Step 1: Review the final diff**

Run:
- `sed -n '1,220p' docs/_template_module_note.md`
- `sed -n '1,220p' AGENTS.md`

Expected: both files reflect the agreed lightweight note format.
