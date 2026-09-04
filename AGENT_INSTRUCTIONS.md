# AGENT_INSTRUCTIONS.md

**Read this file in full before writing or modifying any code in this repository.** These rules are mandatory, not suggestions. If a change you're about to make conflicts with one of these rules, stop and flag it instead of silently deviating.

For project context (what this app does, file responsibilities, non-negotiable design decisions), read `KNOWLEDGE.md` first. For the rationale behind the core architecture calls (why the LLM never decides, why OCR is synchronous, why state transitions are atomic, etc.), read the Architecture Decision Records in `docs/adr/`. This file covers *how* to write code; `KNOWLEDGE.md`/`docs/adr/` cover *what* the code does and *why*.

---

## 1. Code quality standards (apply to every file you touch)

- Write clean, maintainable, scalable code. Follow SOLID principles — in particular, keep one responsibility per file/function (see the file-responsibility table in `KNOWLEDGE.md`; don't merge concerns back together to save a file).
- **TypeScript: strict typing only. Never use `any`.** The existing `tsconfig.json` already has `strict: true`, `noImplicitAny`, `noUncheckedIndexedAccess`, etc. enabled — do not weaken these settings to make code compile.
- **Python: use type hints on every function signature** (parameters and return types), matching the style already used in `backend/*.py`.
- Follow the existing naming conventions: `snake_case` for Python, `camelCase` for TypeScript variables/functions, `PascalCase` for React components and Python classes.
- Use reusable, modular components — before writing a new UI element, check `frontend/src/components/` for one that already fits or can be extended with props.
- Keep the folder structure flat, exactly as it is. Do not introduce new nested subfolders in `backend/` (it must stay a single flat directory of files). In `frontend/src/`, only `components/` and `pages/` subfolders are permitted — do not add `hooks/`, `utils/`, `services/`, etc. as new folders; add such logic to the most relevant existing file instead, or ask before creating a new one.

## 2. Error handling & validation

- Every new backend endpoint must validate its inputs with a Pydantic schema (see `backend/schemas.py`) — never accept raw untyped dicts.
- Every new backend endpoint must handle and return meaningful HTTP status codes on failure (400 for bad input, 401 for auth failure, 403 for authorization failure, 404 for not found, 409 for conflicts, 500 only as a last resort). Follow the pattern already used in `backend/auth.py` and `backend/documents.py`.
- Every new frontend API call must go through `frontend/src/api.ts` and handle the `ApiError` type — never call `fetch` directly from a component.
- Cover edge cases explicitly: empty input, missing/null fields, oversized files, malformed responses, network failure. Don't assume the happy path.

## 3. Security

- Never log, store, or transmit plaintext passwords. Always hash with the existing `hash_password`/`verify_password` functions in `backend/auth.py`.
- Never hardcode a secret, API key, or credential in code. All secrets go through `backend/config.py` (Python) reading from environment variables, or `frontend/src/constants.ts` reading from `import.meta.env` (TypeScript). Update `.env.example` whenever you add a new required environment variable.
- Every new protected endpoint must use the `get_current_merchant` or `require_role(...)` dependency from `backend/auth.py` — never skip authentication/authorization on a route that touches merchant data.
- Validate and sanitize all file uploads (content type, size) the same way `backend/documents.py` already does — do not trust client-supplied file metadata alone.

## 4. UI/UX and accessibility (WCAG-aligned)

- Every status indicator must be paired with a visible text label, never color alone (see `StatusBadge.tsx` for the pattern).
- Every form input must have a real, visible `<label>` (via the existing `InputField` component) — no placeholder-only fields.
- Every interactive element must be keyboard-navigable and have appropriate `aria-*` attributes when its purpose isn't obvious from visible text alone.
- Every screen/component must handle and visibly render all four states where applicable: **loading, empty, success, and error** — not just the success case. Follow the `AsyncState<T>` pattern in `types.ts` and how `DashboardPage.tsx` / `DocumentSlot.tsx` use it.
- Keep the UI responsive across mobile/tablet/desktop breakpoints using Tailwind's existing utility classes — don't introduce a separate CSS framework.

## 5. Performance

- Wrap presentational components in `memo()` the way `Button.tsx`, `InputField.tsx`, `StatusBadge.tsx`, `Alert.tsx`, and `DocumentSlot.tsx` already do, to avoid unnecessary re-renders.
- Use `useCallback`/`useMemo` for functions/values passed as props to memoized children, matching the pattern in `AuthContext.tsx` and `DashboardPage.tsx`.
- Don't introduce polling intervals shorter than necessary; the existing 4-second poll in `DashboardPage.tsx` is a deliberate balance between responsiveness and load — match that order of magnitude for any new polling.

## 6. No hardcoded values

- Any new constant (URL, threshold, limit, label, regex pattern) belongs in `backend/config.py` or `frontend/src/constants.ts` — never inline in business logic or components.

## 7. Comments

- Add a short block comment at the top of any new file explaining its purpose (match the docstring style already used in every existing file).
- Add a block comment above any non-obvious logic (a regex, a business rule, a workaround) explaining *why*, not just *what* — the code itself should make the "what" clear through naming.
- Do not add line-by-line comments restating what the code obviously does.

## 8. No mock implementations unless explicitly requested

- Do not replace a real integration (Groq vision extraction in `ocr.py`, the Groq LLM calls in `verify.py`, bcrypt/JWT in `auth.py`) with a stub or mock without being explicitly asked to. (Note: `ocr.py` and `verify.py` both use the same Groq API key — see `KNOWLEDGE.md` for the quota constraint and the multi-account fallback-key mechanism.)
- The in-memory registries in `faults.py` (demo outage toggles) and `health.py` (metrics) are NOT mocks — they are deliberate, documented architecture (ADR-007). Don't "improve" them into database tables without reading that ADR.
- The 5 external verification tables (`govt_database`, `ckyc_records`, `automated_verification`, `bank_account_validation`, `compliance_reviews`) are an intentional, explicitly-scoped exception — they simulate third-party systems this project cannot actually integrate with. Treat them as real database tables (they are), just populated with synthetic seed data.

## 9. Testing before you consider a change done

- Backend: run `python -m py_compile *.py` from `backend/` to catch syntax errors, then run the project's offline end-to-end suite `python test_features.py` from `backend/` (throws away its own SQLite DB; patches the LLM; makes no real API calls) before calling the change complete. New backend features should add checks there, following its existing sections.
- Frontend: run `npm run typecheck` (must pass with zero errors) and `npm run build` from `frontend/` before calling the change complete.
- If you change `backend/db.py`, regenerate `backend/schema.sql` to keep it in sync (see the generation snippet in `backend/schema.sql`'s header comment, or re-run the `CreateTable`/`CreateIndex` compilation against the SQLAlchemy metadata).
- If a change touches a core design decision (LLM authority, deferral semantics, state transitions, engine choice, demo-state architecture), update the matching record in `docs/adr/` and note it in `session_log.md` — keeping the docs current is a project convention, not an afterthought.

## 10. When a request conflicts with these rules

If a future instruction (from me or from Claude) would require breaking one of these rules — e.g., adding an `any` type, skipping input validation, hardcoding a secret — flag the conflict explicitly rather than silently complying or silently ignoring the new instruction.
