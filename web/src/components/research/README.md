# Original research workbench

The migration baseline is upstream `origin/main` at `1ee6cff`, including the
observational evaluator selector and bounded timeline-event previews.

`platform-markup.tsx` and `tree-markup.tsx` retain the original DOM structure,
control IDs and layout. The style strings retain the original styles, themes,
responsive rules and panel behavior. React mounts these surfaces and the account
dialog. The original scientific interaction controllers own each surface's DOM;
React does not concurrently reconcile their dynamic timelines, plots or graphs.
Their listeners, timers and observers are disposed with the React surface.

`transport.ts` translates the original presentation operations into explicit,
owned `/api/conversations/{id}/harness/...` requests. No legacy HTTP routes,
Cookie-selected Harness sessions, global fetch overrides or shared filesystem
have been introduced. Search records use cursor polling in both embedded and
standalone tree viewers. The tree's formula renderer uses bundled KaTeX, with no
external CDN request.

The three original model/settings dialogs retain their workflow and tool/skill
controls. Only provider/key inputs are replaced with complete database model
profiles. Account and model management opens as a dialog rather than replacing
the research workspace. Keys remain managed by the Next.js backend.

Unmodified presentation references live in `tests/fixtures/original`. Playwright
compares the original and React panel bounds and phase surfaces, then exercises
uploads, Agent conversations, evaluator editing, search, tree navigation,
pause/resume, persisted selection, language/theme, archive and export through the
authenticated backend.
