# AGENT_INSTRUCTIONS.md

**Read this file in full before writing or modifying any code in this repository.** These rules are mandatory, not suggestions. If a change you are about to make conflicts with one of these rules, stop and flag it instead of silently deviating.

For project context (what this app does, file responsibilities, non-negotiable design decisions), read `KNOWLEDGE.md` first. For the reasoning behind the core architecture calls (why the LLM never decides, why OCR is synchronous, why state transitions are atomic), read the Architecture Decision Records in `docs/adr/`. This file covers how to write code. `KNOWLEDGE.md` and `docs/adr/` cover what the code does and why.

---

## 1. Code quality standards (apply to every file you touch)

- Write clean, maintainable code. Follow SOLID principles. In particular, keep one responsibility per file or function (see the file-responsibility table in `KNOWLEDGE.md`; do not merge concerns back together to save a file).
- **TypeScript: strict typing only. Never use `any`.** The existing `tsconfig.json` already enables `strict`, `noImplicitAny`, `noUncheckedIndexedAccess`, and more. Do not weaken these settings to make code compile.
- **Python: add type hints to every function signature** (parameters and return types), matching the style already used in `backend/*.py`.
- Follow the existing naming conventions: `snake_case` for Python, `camelCase` for TypeScript variables and functions, `PascalCase` for React components and Python classes.
- Use reusable, modular components. Before writing a new UI element, check `frontend/src/components/` for one that already fits or can be extended with props.
- Keep the folder structure flat, exactly as it is. Do not add new nested subfolders in `backend/` (it must stay a single flat directory of files). In `frontend/src/`, only `components/` and `pages/` subfolders are permitted. Do not add `hooks/`, `utils/`, `services/`, or similar new folders. Add such logic to the most relevant existing file instead, or ask before creating a new one.

## 2. Error handling and validation

- Every new backend endpoint must validate its inputs with a Pydantic schema (see `backend/schemas.py`). Never accept raw untyped dicts.
- Every new backend endpoint must return meaningful HTTP status codes on failure: 400 for bad input, 401 for auth failure, 403 for authorization failure, 404 for not found, 409 for conflicts, and 500 only as a last resort. Follow the pattern already used in `backend/auth.py` and `backend/documents.py`.
- Every new frontend API call must go through `frontend/src/api.ts` and handle the `ApiError` type. Never call `fetch` directly from a component.
- Cover edge cases explicitly: empty input, missing or null fields, oversized files, malformed responses, network failure. Do not assume the happy path.

## 3. Security

- Never log, store, or transmit plaintext passwords. Always hash with the existing `hash_password` and `verify_password` functions in `backend/auth.py`.
- Never hardcode a secret, API key, or credential in code. All secrets go through `backend/config.py` (Python), which reads environment variables, or `frontend/src/constants.ts` (TypeScript), which reads `import.meta.env`. Update `.env.example` whenever you add a new required environment variable.
- Every new protected endpoint must use the `get_current_merchant` or `require_role(...)` dependency from `backend/auth.py`. Never skip authentication or authorization on a route that touches merchant data.
- Validate and sanitize all file uploads (content type and size) the same way `backend/documents.py` already does. Do not trust client-supplied file metadata alone.

## 4. UI/UX and accessibility (WCAG-aligned)

- Every status indicator must be paired with a visible text label, never color alone (see `StatusBadge.tsx` for the pattern).
- Every form input must have a real, visible label (via the existing `InputField` component). No placeholder-only fields.
- Every interactive element must be keyboard-navigable and have appropriate `aria-*` attributes when its purpose is not obvious from the visible text alone.
- Every screen and component must handle and visibly render all four states where applicable: loading, empty, success, and error. Not just the success case. Follow the `AsyncState<T>` pattern in `types.ts` and how `DashboardPage.tsx` and `DocumentSlot.tsx` use it.
- Keep the UI responsive across mobile, tablet, and desktop breakpoints using Tailwind's existing utility classes. Do not introduce a separate CSS framework.

## 5. Performance

- Wrap presentational components in `memo()` the way `Button.tsx`, `InputField.tsx`, `StatusBadge.tsx`, `Alert.tsx`, and `DocumentSlot.tsx` already do, to avoid unnecessary re-renders.
- Use `useCallback` and `useMemo` for functions and values passed as props to memoized children, matching the pattern in `AuthContext.tsx` and `DashboardPage.tsx`.
- Do not introduce polling intervals shorter than necessary. The existing 4-second poll in `DashboardPage.tsx` is a deliberate balance between responsiveness and load. Match that order of magnitude for any new polling.

## 6. No hardcoded values

- Any new constant (URL, threshold, limit, label, regex pattern) belongs in `backend/config.py` or `frontend/src/constants.ts`. Never inline it in business logic or components.

## 7. Comments

- Add a short block comment at the top of any new file explaining its purpose (match the docstring style already used in every existing file).
- Add a block comment above any non-obvious logic (a regex, a business rule, a workaround) explaining why, not just what. The code itself should make the "what" clear through naming.
- Do not add line-by-line comments that restate what the code obviously does.

## 8. No mock implementations unless explicitly requested

- Do not replace a real integration (the Groq vision extraction in `ocr.py`, the Groq LLM calls in `verify.py`, bcrypt/JWT in `auth.py`) with a stub or mock without being explicitly asked to. Note: `ocr.py` and `verify.py` both use the same Groq API key. See `KNOWLEDGE.md` for the quota constraint and the multi-account fallback-key mechanism.
- The in-memory registries in `faults.py` (demo outage toggles) and `health.py` (metrics) are NOT mocks. They are a deliberate, documented architecture (ADR-007). Do not "improve" them into database tables without reading that ADR.
- The 5 external verification tables (`govt_database`, `ckyc_records`, `automated_verification`, `bank_account_validation`, `compliance_reviews`) are an intentional, explicitly-scoped exception. They simulate third-party systems this project cannot actually integrate with. Treat them as real database tables (they are), just populated with synthetic seed data.

## 9. Testing before you consider a change done

- Backend: run `python -m py_compile *.py` from `backend/` to catch syntax errors, then run the project's offline end-to-end suite `python test_features.py` from `backend/` (it throws away its own SQLite DB, patches the LLM, and makes no real API calls) before calling the change complete. New backend features should add checks there, following its existing sections.
- Frontend: run `npm run typecheck` (must pass with zero errors) and `npm run build` from `frontend/` before calling the change complete.
- If you change `backend/db.py`, regenerate `backend/schema.sql` to keep it in sync (see the generation snippet in `backend/schema.sql`'s header comment, or re-run the `CreateTable` / `CreateIndex` compilation against the SQLAlchemy metadata).
- If a change touches a core design decision (LLM authority, deferral behavior, state transitions, engine choice, demo-state architecture), update the matching record in `docs/adr/` and note it in `session_log.md`. Keeping the docs current is a project convention, not an afterthought.

## 10. When a request conflicts with these rules

If a future instruction would require breaking one of these rules (for example, adding an `any` type, skipping input validation, or hardcoding a secret), flag the conflict explicitly rather than silently complying or silently ignoring the new instruction.
