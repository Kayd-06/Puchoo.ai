# Obsidian Control Plane Design

## Scope

Redesign the authenticated History and Settings pages as a future-facing, pitch-black SaaS control plane without changing their data fetching, permissions, mutations, or backend contracts.

## Visual direction

- Use a true black canvas, graphite panels, hairline borders, and restrained cyan, blue, emerald, amber, and red state colors.
- Favor a precise operational hierarchy: compact uppercase labels, large editorial page titles, readable card titles, and monospaced record identifiers.
- History uses a responsive two-column ledger with compact metrics, a command toolbar, and state-specific edge treatments.
- Settings uses a responsive bento arrangement: invitation and identity panels share the primary row when invitations are available; personal workspaces balance identity and history panels.
- Animation includes staged page entrance, slow ambient field movement, card edge sweeps, state pulses, and tactile hover/focus transitions.
- `prefers-reduced-motion: reduce` disables all non-essential animation and transforms.

## Functional constraints

- Preserve all existing History fetch, filter, search, clear, continue, SQL disclosure, and record-delete behavior.
- Preserve all existing Settings viewer restrictions, invitation generation/rotation/copy, email-change verification, and history navigation.
- Do not add dependencies, routes, APIs, features, or backend changes.
- Keep controls keyboard accessible, preserve semantic landmarks and ARIA, and maintain mobile layouts down to 320px.

## Verification

- Run frontend lint and production build.
- Run the existing automated test suite because shared CSS and page markup can expose regressions.
- Inspect History and Settings at desktop and mobile widths, including loading/empty/error-safe layout, focus states, dialogs, and reduced-motion behavior.

