# Obsidian Control Plane Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a professional pitch-black redesign of History and Settings while preserving every current backend-connected action.

**Architecture:** Keep React state and API functions unchanged. Add only semantic presentation hooks to the existing page components, then define the design system and responsive motion in the existing global stylesheet.

**Tech Stack:** React 19, CSS, lucide-react, Vite

**Spec:** `docs/superpowers/specs/2026-10-08-obsidian-control-plane-design.md`

## Global Constraints

- No backend, route, API contract, dependency, or product-feature changes.
- Do not commit or push.
- Preserve keyboard access, responsive behavior, and reduced-motion support.

## Review Focus

- Long questions, emails, workspace names, and invite codes must wrap or truncate without horizontal overflow.
- Viewer and personal-workspace variants must not leave broken bento columns.
- Empty, loading, and error states must retain readable contrast and stable layout.
- Interactive controls must retain visible focus and disabled states.
- Motion must stop under `prefers-reduced-motion: reduce`.

---

### Task 1: Semantic presentation hooks

**Files:**
- Modify: `frontend/src/pages/History.jsx`
- Modify: `frontend/src/pages/Settings.jsx`

**Interfaces:**
- Consumes: existing `fetchApi`, auth context, app context, and navigation behavior.
- Produces: presentation-only class hooks and labels consumed by Task 2 CSS.

- [ ] Add decorative, record-index, and security-posture markup without changing handlers or state.
- [ ] Run `npm run lint` from `frontend`; expect exit 0.

### Task 2: Obsidian responsive design system

**Files:**
- Modify: `frontend/src/index.css`

**Interfaces:**
- Consumes: Task 1 class hooks and all existing component classes.
- Produces: responsive desktop/mobile styling and reduced-motion fallbacks.

- [ ] Implement the pitch-black canvas, two-column History ledger, adaptive Settings bento layout, interaction states, and animations.
- [ ] Run `npm run lint` and `npm run build` from `frontend`; expect exit 0.

### Task 3: Integrated verification

**Files:**
- Verify only; fix scoped regressions in the files above if found.

**Interfaces:**
- Consumes: completed UI implementation.
- Produces: verified desktop/mobile pages with preserved backend-connected behavior.

- [ ] Run the full existing automated suite.
- [ ] Preview and inspect History and Settings at desktop and mobile widths.
- [ ] Exercise non-destructive controls and verify browser console/layout health.
- [ ] Run `git diff --check`; expect exit 0.

