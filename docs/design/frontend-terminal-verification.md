# Frontend terminal verification

## Automated evidence

The implementation was checked from integration base `397251fbef08b63ad1b5db45def3488b4b64d4bc` on 2026-11-03. Results after the #394 test additions:

| Check | Result | Evidence |
|---|---|---|
| Frontend tests | Passed | `npm test -- --reporter=dot`; 12 files, 57 tests |
| Frontend lint | Passed | `npm run lint` |
| Type check | Passed | `npm run typecheck` |
| Static production build | Passed | `npm run build`; `/`, `/swing`, and `/long-term` exported |
| Route configuration | Covered | `frontend/src/app/static-export.test.ts` verifies static export |
| Authentication flows | Covered | `frontend/src/features/auth/sign-in.test.tsx` verifies sign in, registration, reset, verification/admission, pending, denied, and expired feedback; denied and expired feedback remain announced and protected workspace links stay hidden |
| Swing workflow | Covered | `frontend/src/app/swing/page.test.tsx` covers loading, empty, unavailable, retryable, failed, selection, chart-only unavailability, evidence, table data, and keyboard resizing |
| Long-Term workflow | Covered | `frontend/src/features/long_term/workspace.test.tsx` and `frontend/src/app/long-term/page.test.tsx` cover objective/company selection, annual evidence, partial dividend facts, deep links, and retryable publication errors |

The palette values in `frontend/src/app/globals.css` were checked against canvas, surface, and raised surfaces. The lowest text contrast among the foreground tokens is failure text on the raised surface at 5.50:1; muted text is at least 7.95:1. These calculations do not replace checking every rendered state in a browser.

## Browser and assistive technology evidence

| Check | Result | Evidence |
|---|---|---|
| PR-head screenshots at 375, 768, 1024, and 1440 px | Not captured | This environment denied local app server binding (`listen EPERM` on ports 3000 and 8765), so the PR build could not be opened in a browser here. |
| 200% zoom and horizontal overflow | Pending browser check | Requires rendering the PR head at 200% zoom. |
| Keyboard-only focus order and focus retention | Partially covered by automated keyboard tests; manual review pending | Unit tests cover auth tabs, Long-Term tabs, and Swing pane resize. Full browser traversal remains to be recorded. |
| Screen-reader announcements and chart data access | Automated semantics covered; manual review pending | Status roles and the chart data table are asserted in tests; no screen reader was available for this check. |
| Owner visual acceptance tied to PR head | Pending | Must be recorded against the final reviewed PR head and its screenshots. |

Automated checks are regression evidence, not WCAG 2.2 AA certification. Do not mark the browser/manual checks passed until screenshots and observations are recorded against the final PR head.
