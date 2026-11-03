# Frontend terminal verification

## Automated evidence

The implementation was checked from integration base `397251fbef08b63ad1b5db45def3488b4b64d4bc` on 2026-11-03. Results after the #394 test additions:

| Check | Result | Evidence |
|---|---|---|
| Frontend tests | Passed | `npm test -- --reporter=dot`; 12 files, 58 tests |
| Frontend lint | Passed | `npm run lint` |
| Type check | Passed | `npm run typecheck` |
| Static production build | Passed | `npm run build`; `/`, `/swing`, and `/long-term` exported |
| Bundle-size comparison | Completed from local build artifacts | `_next/static` emitted JavaScript: development base `397251f` 1,166,324 bytes → PR source 1,166,357 bytes (+33); CSS: 46,675 → 46,765 bytes (+90); combined delta +123 bytes. This compares built local artifacts and does not represent deployed gzip transfer size. |
| Route configuration | Covered | `frontend/src/app/static-export.test.ts` verifies static export |
| Authentication flows | Covered | `frontend/src/features/auth/sign-in.test.tsx` verifies sign in, registration, reset, verification/admission, pending, denied, and expired feedback; denied and expired feedback remain announced and protected workspace links stay hidden |
| Swing workflow | Covered | `frontend/src/app/swing/page.test.tsx` covers loading, empty, unavailable, retryable, failed, selection, chart-only unavailability, evidence, table data, and keyboard resizing |
| Long-Term workflow | Covered | `frontend/src/features/long_term/workspace.test.tsx` and `frontend/src/app/long-term/page.test.tsx` cover objective/company selection, annual evidence, partial dividend facts, deep links, and retryable publication errors |
| Desktop Long-Term navigation rail | Passed | `frontend/src/features/long_term/workspace.test.tsx` verifies the Long-Term CSS applies the same 216 px left offset as the fixed desktop rail at 1200 px and wider. |

The palette values in `frontend/src/app/globals.css` were checked against canvas, surface, and raised surfaces. The lowest text contrast among the foreground tokens is failure text on the raised surface at 5.50:1; muted text is at least 7.95:1. These calculations do not replace checking every rendered state in a browser.

## Browser and assistive technology evidence

| Check | Result | Evidence |
|---|---|---|
| Swing screenshots | Captured against deployed development base `397251fbef08b63ad1b5db45def3488b4b64d4bc` on 2026-11-03 | [375 px](frontend-terminal-verification/375-swing.jpg) and [1440 px](frontend-terminal-verification/1440-swing.jpg). Both show the published list and selected recommendation; chart data was still loading/unavailable. These are deployed-base screenshots, not PR-head screenshots. |
| Long-Term and auth screenshots | Captured against deployed development base on 2026-11-03 | [451 px Long-Term](frontend-terminal-verification/451-long-term.jpg) shows the loaded company list and annual evidence. [1440 px Long-Term before the fix](frontend-terminal-verification/1440-long-term-before-fix.jpg) exposes the heading being covered by the fixed rail; PR code now offsets this page by 216 px at desktop widths. A post-fix PR-head screenshot could not be captured because local server binding is denied. [451 px admitted auth](frontend-terminal-verification/auth-admitted-451.jpg) and [1440 px admitted auth](frontend-terminal-verification/auth-admitted-1440.jpg) show admitted workspace links only; neither is the credential-entry screen. |
| Responsive overflow | Passed on deployed development base at 375, 768, 1024, and 1440 CSS px | Parent operator checked Swing, Long-Term, and the sign-in route's admitted screen. At every route/width, `documentElement.scrollWidth` and `body.scrollWidth` matched `innerWidth`; no horizontal overflow was observed. Data endpoints were loading/unavailable during this pass. `/sign-in` resolved to the admitted screen, so the credential-entry screen was not checked. |
| 200% zoom | Simulated effective width only; browser zoom not checked | At an effective 720 CSS px viewport (1440 px divided by 200%), the deployed Swing, Long-Term, and sign-in shell had root/body `scrollWidth` equal to 720. The tab automation API could not change the browser zoom setting, so this is not a 200% browser-zoom result. |
| Keyboard-only focus order and focus retention | Partially checked | On deployed Swing, the first 12 keyboard stops were Sign out, brand link, Swing, Long-Term, search, filters, period controls, and price-table disclosure; the order was coherent and controls were focusable. On loaded Long-Term, the observed order was Sign out, brand, Swing, Long-Term, Growth scores tab, then company buttons. Unit tests also cover auth tab movement, Long-Term tab selection, and the Swing pane-resize affordance. Focus retention after workflow changes, full auth traversal, and mobile navigation were not manually checked. |
| Screen-reader announcements and chart data access | Automated semantics covered; manual check pending | Tests assert live status roles and a chart data table. No screen-reader pass was completed. |
| Reduced motion | Source review completed | The active Swing and Long-Term routes use no animations or transitions. The only `animate-pulse` found is the loading placeholder in the legacy `frontend/src/components/workspace-shell.tsx`, which these routes do not use. |
| Credential-entry screenshot | Not captured | The available auth screenshot shows admitted access. The credential-entry state still needs visual review. |
| Owner visual acceptance tied to PR head | Pending | The screenshots above are from the deployed base commit. Owner visual acceptance must reference the final reviewed PR head and note the remaining visual checks. |

Automated checks and responsive overflow measurements are regression evidence, not WCAG 2.2 AA certification. The desktop Long-Term offset has a CSS-source regression test. Its post-fix rendering, 200% browser zoom, screen-reader checks, and remaining owner visual acceptance are still open for final review.
