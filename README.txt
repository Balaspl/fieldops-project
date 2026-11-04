FieldOps 3-second auto-refresh update
=====================================

Apply this patch from the FieldOps project root. Extract the ZIP while
preserving its folder structure and allow it to overwrite the included files.

Included targets:
  - frontend/src/...
  - customer-mobile/app/...
  - customer-mobile/src/hooks/useFocusedAutoRefresh.ts

Behavior:
  - Read-only screen data refreshes every 3 seconds on the active screen.
  - Web polling pauses when the browser tab is hidden.
  - Customer-mobile polling is scoped to the focused route and pauses when
    the app is backgrounded.
  - Existing local form text, filters and in-progress actions are preserved;
    polling pauses on selected edit/submit screens or while an action is busy.
  - Polling does not repeat write actions. Existing WebSocket and technician
    heartbeat flows were left in place.

Validation:
  - TypeScript/TSX syntax transpilation: 241 files checked, 0 syntax errors.
  - Full dependency-aware type-check, unit tests and browser/Android runtime
    validation were not run from this ZIP extraction environment.

Scope note:
  The supplied ZIP included the frontend and customer-mobile source trees.
  It did not include a separate technician mobile source folder (if your
  repository has one), so this update does not modify that separate app.
