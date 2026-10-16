# Global Light and Dark Theme Design

## Goal

Add a persistent, accessible light/dark toggle for every Puchoo.si route. Dark
mode remains the default and retains the supplied black-titanium reference.
Light mode is a deliberate warm-white and graphite counterpart, not a flat
color inversion. Existing motion remains enabled in both themes unless the
person has requested reduced motion at the operating-system level.

## Scope

- Marketing, authentication, legal, and authenticated workspace routes.
- A visible sun/moon toggle in the authenticated product top bar only.
- Theme persistence in browser local storage, with dark as the first-visit
  fallback.
- Theme-aware colors, gradients, borders, controls, panels, and motion accents
  across the product shell and each route-specific surface.

The change does not introduce a server preference, user-profile schema field,
or a new animation system.

## Architecture

`ThemeProvider` owns the selected theme (`dark` or `light`) and exposes a
toggle through `useTheme`. It initializes from `localStorage` and uses dark
when no valid persisted value exists. Whenever the selection changes, the
provider writes it back and sets `data-theme` on `document.documentElement`.

The provider wraps the root in `main.jsx`, before the route-specific dynamic
module is rendered. This makes it available to the independent marketing page
as well as the routed product application. A small shared `ThemeToggle`
component uses that context and renders a labelled, keyboard-accessible button
whose icon and label describe the *next* theme.

`ThemeToggle` appears in the authenticated product top bar. It has a fixed
touch target and a visible focus ring. Public and authentication pages apply
the selected theme but do not expose a separate control.

## Visual System

The existing dark palette stays black-titanium: near-black backgrounds,
warm-neutral framing, off-white text, and restrained gold/blue/green accents.

Light mode uses warm paper backgrounds, graphite text, white panels, soft
stone borders, and muted bronze/blue/green accents. The contrast target is at
least WCAG AA for normal text and primary interactive controls.

Semantic custom properties define the shared theme values: application and
surface backgrounds, raised surfaces, primary and muted text, borders,
interactive hover/focus colors, panel shadows, and ambient/glow colors.
The current route-specific dark declarations are supplemented with light-theme
overrides for the shell, Ask Data, results, History, Settings, Connect Data,
marketing, authentication, and legal screens. This keeps page-specific visual
hierarchy intact while removing unreadable hard-coded dark combinations in
light mode.

Color/background/border/shadow transitions use a short transition on the
document surface and theme-aware components. Existing animations--including
page entrances, ambient stars/signals, scans, shimmer, hover lifts, and
loading motion--remain unchanged. Their colors resolve through the new theme
properties so they remain visible and polished on the light canvas. Existing
`prefers-reduced-motion` behavior continues to disable motion.

## Data Flow and Error Handling

Theme selection is client-only. Invalid local-storage values are ignored and
replaced by the dark fallback. Access to storage is guarded so private-browser
or storage-restricted environments still render and toggle in memory without
throwing.

The application sets the initial HTML theme before the first React render, then
the provider reconciles and persists it. This prevents an initial light flash
on a saved dark preference and keeps the root attribute correct for CSS even
when a page is lazy loaded.

## Verification

- Unit tests exercise the default, toggle, persistence, and root attribute.
- Product-surface tests confirm the top-bar toggle is available and changes
  the global theme.
- Public/auth-surface tests confirm those pages render safely under the global
  theme provider without exposing a second toggle.
- CSS semantics tests confirm both theme selectors cover the main shell and
  route-specific canvases, plus reduced-motion support remains present.
- Run the complete frontend test suite and production build. Manually inspect
  desktop and mobile views in both themes, checking contrast and active,
  hover, focus, empty, error, and loading states.
