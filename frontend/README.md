# React + Vite

This template provides a minimal setup to get React working in Vite with HMR and some Oxlint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the Oxlint configuration

If you are developing a production application, we recommend using TypeScript with type-aware lint rules enabled. Check out the [TS template](https://github.com/vitejs/vite/tree/main/packages/create-vite/template-react-ts) for information on how to integrate TypeScript and Oxlint's TypeScript related rules in your project.

## Scoped conversation persistence (audit F06/F07)

Ask Data snapshots are keyed by authenticated user, canonical tenant, role and
workspace. The retired v1 cache is discarded. History continuation carries that
same identity plus the saved record ID, and requires a one-use session ticket.
Choosing a conversation retires earlier request writers for that scoped view.
A reload can restore legitimate scoped context; a browser history entry cannot
consume the same ticket again or apply another workspace's context.

After a successful single/bulk DELETE, including HTTP 202 `cleanup_pending`, a
metadata-only deletion journal in localStorage invalidates the affected views,
sessionStorage snapshots and continuation tickets. Other same-origin tabs receive
storage events; fresh module hydration checks the durable markers too. Request
generations prevent late responses from restoring invalidated views. A failed
DELETE preserves the current view. Unrelated workspaces and saved records remain
available. A scope's requests already in flight when deletion occurs are ignored
conservatively; retry the question if needed. Ordinary Enter submission still runs
guarded read-only SQL and safe repairs automatically.

Limits: this is browser view invalidation, not cancellation of accepted server
execution or retroactive erasure of delivered data. Server-side deletion durability
and truthful 202 responses are the separate F11/F12 backend change (PR #62).
Other devices/browsers, offline tabs, or browsers blocking storage are not promised
immediate invalidation. If journal writes fail, this document clears its local
views and stops persisting snapshots, but cannot reliably notify other tabs or
preserve the new marker across restart. Markers contain IDs/nonces, not question
text or results; they are retained without automatic expiry to avoid resurrecting
old session snapshots. Clearing site storage removes this browser metadata too.

Regression tests use DOM integration tests, synthetic requests, storage events,
and fresh module imports. They do not replace real browser/multi-tab validation.
Before release, use two real accounts/roles and two workspaces in a staging browser:
continue A, switch to B, navigate back/reload, delete single/all in another tab,
and resolve slow requests after deletion. Confirm unrelated results remain and a
failed DELETE does not erase the view. Test storage-disabled behavior separately.
