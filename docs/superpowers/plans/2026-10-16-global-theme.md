# Global Theme Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every Puchoo.si route a persistent light/dark appearance, with an accessible control in the authenticated product top bar, while retaining the current animation system.

**Architecture:** A root `ThemeProvider` owns a `dark`/`light` preference, synchronizes it to the HTML `data-theme` attribute, and persists safely in local storage. A shared `ThemeToggle` is composed into the authenticated product top bar only. CSS semantic properties plus late light-theme overrides preserve each existing page’s visual hierarchy and motion.

**Tech Stack:** React 19, React context, lucide-react, CSS custom properties, Vitest, Testing Library, Vite.

**Spec:** `docs/superpowers/specs/2026-10-16-global-theme-design.md`

## Global Constraints

- Dark is the first-visit fallback and preserves the black-titanium reference.
- Persist only `dark` or `light` in browser local storage; storage failures must not break rendering.
- Theme applies through `data-theme` on `document.documentElement` before React paints and after every toggle.
- The toggle is available in the authenticated product top bar only; every
  route still renders using the selected global theme.
- Preserve all existing animation behavior in both themes; retain `prefers-reduced-motion` safeguards.
- Maintain WCAG AA contrast for normal text and primary controls in light mode.
- Do not introduce server-side profile state, schema changes, or theme dependencies.

## Review Focus

- Invalid or stale local-storage values must fall back to dark without an exception; Task 1 covers this.
- Storage access that throws must still allow a person to toggle the in-memory theme; Task 1 covers this.
- The HTML attribute must reflect a saved preference before a lazy-loaded route paints; Task 1 covers the bootstrap helper.
- Public and authentication routes must render with the selected global theme without exposing a duplicate control; Task 2 covers both shells.
- Reduced-motion users retain static alternatives while light-mode ambient effects remain visible; Task 3 covers CSS behavior and manual visual review.

### Task 1: Theme state and browser bootstrap

**Files:**
- Create: `frontend/src/context/ThemeContext.jsx`
- Create: `frontend/src/context/__tests__/ThemeContext.test.jsx`
- Modify: `frontend/src/main.jsx`

**Interfaces:**
- Produces: `ThemeProvider({ children })`, `useTheme() -> { theme: 'dark' | 'light', toggleTheme: () => void }`, and `applyStoredTheme(): 'dark' | 'light'`.
- Consumes: browser `document.documentElement` and local storage key `puchoo:theme`.

- [ ] **Step 1: Write failing theme-state tests**

```jsx
it('defaults to dark and applies it to the document root', () => {
  render(<ThemeProvider><Probe /></ThemeProvider>);
  expect(screen.getByText('dark')).toBeInTheDocument();
  expect(document.documentElement).toHaveAttribute('data-theme', 'dark');
});

it('restores a valid saved preference, toggles it, and persists the new value', () => {
  localStorage.setItem('puchoo:theme', 'light');
  render(<ThemeProvider><Probe /></ThemeProvider>);
  fireEvent.click(screen.getByRole('button', { name: 'Toggle theme' }));
  expect(document.documentElement).toHaveAttribute('data-theme', 'dark');
  expect(localStorage.getItem('puchoo:theme')).toBe('dark');
});
```

Add focused cases for an invalid value and a throwing storage implementation, both asserting a usable dark fallback. Add a bootstrap assertion that `applyStoredTheme()` sets the root attribute before React renders.

- [ ] **Step 2: Run the ThemeContext tests to verify they fail**

Run: `npm test -- --run src/context/__tests__/ThemeContext.test.jsx`

Expected: FAIL because the context and bootstrap helper do not exist.

- [ ] **Step 3: Implement `ThemeProvider`, `useTheme`, and `applyStoredTheme`**

In `ThemeContext.jsx`, accept only `dark` and `light`, guard every storage operation with `try/catch`, update `document.documentElement.dataset.theme`, and persist after a successful toggle. In `main.jsx`, call `applyStoredTheme()` immediately before `createRoot` so the saved preference is present before lazy route loading.

- [ ] **Step 4: Run the ThemeContext tests to verify they pass**

Run: `npm test -- --run src/context/__tests__/ThemeContext.test.jsx`

Expected: PASS.

- [ ] **Step 5: Commit the theme-state deliverable**

```bash
git add frontend/src/context/ThemeContext.jsx frontend/src/context/__tests__/ThemeContext.test.jsx frontend/src/main.jsx
git commit -m "feat: add persistent application theme state"
```

### Task 2: Shared control and route integration

**Files:**
- Create: `frontend/src/components/ThemeToggle.jsx`
- Modify: `frontend/src/components/layout/TopBar.jsx`
- Modify: `frontend/src/pages/__tests__/role-surfaces.test.jsx`
- Create: `frontend/src/components/__tests__/ThemeToggle.test.jsx`

**Interfaces:**
- Consumes: `useTheme()` from `ThemeContext.jsx`.
- Produces: `ThemeToggle({ className?: string })`, a button with an accessible next-theme label and current pressed state.

- [ ] **Step 1: Write failing control and shell-integration tests**

```jsx
it('announces the next theme and toggles the root theme when activated', () => {
  render(<ThemeProvider><ThemeToggle /></ThemeProvider>);
  fireEvent.click(screen.getByRole('button', { name: 'Switch to light mode' }));
  expect(document.documentElement).toHaveAttribute('data-theme', 'light');
  expect(screen.getByRole('button', { name: 'Switch to dark mode' })).toBeInTheDocument();
});

it('shows a theme control in the authenticated top bar', () => {
  renderRoute(<TopBar />);
  expect(screen.getByRole('button', { name: 'Switch to light mode' })).toBeInTheDocument();
});
```

Add lightweight rendering tests for `AuthShell` and the landing page to prove they remain safe under `ThemeProvider` and do not show a duplicate theme control.

- [ ] **Step 2: Run the control tests to verify they fail**

Run: `npm test -- --run src/components/__tests__/ThemeToggle.test.jsx src/pages/__tests__/role-surfaces.test.jsx`

Expected: FAIL because the shared control and route integrations do not exist.

- [ ] **Step 3: Implement `ThemeToggle` and compose it into the authenticated product top bar**

Use `Sun` and `Moon` from `lucide-react`; expose `aria-label="Switch to light mode"` in dark mode and `aria-label="Switch to dark mode"` in light mode. Place the control before product notifications only. Keep both dynamically rendered root page variants under `ThemeProvider` in `main.jsx` so every route shares the selected appearance.

- [ ] **Step 4: Run the control tests to verify they pass**

Run: `npm test -- --run src/components/__tests__/ThemeToggle.test.jsx src/pages/__tests__/role-surfaces.test.jsx`

Expected: PASS.

- [ ] **Step 5: Commit the shared-control deliverable**

```bash
git add frontend/src/components/ThemeToggle.jsx frontend/src/components/__tests__/ThemeToggle.test.jsx frontend/src/components/layout/TopBar.jsx frontend/src/pages/__tests__/role-surfaces.test.jsx
git commit -m "feat: add theme toggle to every application shell"
```

### Task 3: Theme-aware visual system and motion

**Files:**
- Modify: `frontend/src/index.css`
- Modify: `frontend/src/styles/site.css`

**Interfaces:**
- Consumes: `html[data-theme='dark']` and `html[data-theme='light']` set by Task 1.
- Produces: semantic CSS properties and light-theme overrides for the product shell, authenticated views, public landing, and authentication views.

- [ ] **Step 1: Capture the observable visual baseline**

Run: `npm run dev`

Before changing CSS, inspect the existing dark desktop and narrow mobile views for `/`, `/login`, `/signup`, `/forgot-password`, `/ask`, `/connect`, `/history`, and `/settings`. Record the navigation, menu, form, error, empty, loading, focus, and animation states that light mode must preserve. This is a visual test rather than a source-text assertion: CSS selector snapshots would not prove the rendered contrast or motion works.

- [ ] **Step 2: Add semantic tokens and light-mode overrides**

Define dark and light values for app/surface/raised backgrounds, primary/muted text, borders, focus, shadow, and ambient accents near the root CSS variables. Add a short color/background/border/shadow transition that is neutralized by the current reduced-motion rules. Then append focused `html[data-theme='light']` overrides for app chrome, Ask Data/results, History, Settings, Connect Data, auth forms, landing/editorial sections, and legal pages. Preserve all keyframes and replace only their hard-coded palette use where contrast would fail.

- [ ] **Step 3: Manually inspect the visual states**

Run: `npm run dev`

Check desktop and narrow mobile layouts in both themes for `/`, `/login`, `/signup`, `/forgot-password`, `/ask`, `/connect`, `/history`, and `/settings`. Check active navigation, menus, inputs, disabled states, errors, empty states, loading states, hover/focus rings, and visible ambient/entrance motion. Repeat with reduced motion enabled and confirm nonessential motion is suppressed.

- [ ] **Step 4: Commit the visual-system deliverable**

```bash
git add frontend/src/index.css frontend/src/styles/site.css
git commit -m "feat: add polished light theme across application surfaces"
```

### Task 4: Whole-app verification

**Files:**
- Modify: no production files expected

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces: fresh test/build evidence for the full theme feature.

- [ ] **Step 1: Run the full frontend suite**

Run: `npm test -- --run`

Expected: PASS with no failed tests.

- [ ] **Step 2: Build the production frontend**

Run: `npm run build`

Expected: PASS with a generated Vite production bundle.

- [ ] **Step 3: Check patch hygiene**

Run: `git diff --check`

Expected: no whitespace errors; report unrelated pre-existing worktree changes separately.
