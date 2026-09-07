# Hirenomous Frontend Redesign — Teal/Gold/Navy Workable-Style System (Final)

## 0. HARD RULE — READ FIRST, FOLLOW AT ALL TIMES, NO EXCEPTIONS

**The backend must never be touched, in any form, under any circumstance.** This
overrides everything else below if they ever appear to conflict.

- Do not open, edit, refactor, or "clean up" anything inside `backend/`.
- Do not add, remove, rename, or change the signature/response shape of any API
  endpoint.
- `frontend/lib/api.ts`, `frontend/lib/interview-api.ts`, and
  `frontend/lib/auth-context.tsx` stay **byte-identical** in behavior — same
  endpoint URLs, methods, payloads, response parsing. Do not touch them unless a
  component truly cannot render without a trivial prop/type addition, and even
  then the function names, URLs, and return shapes must not change.
- Every screen must call the exact same endpoints, the exact same way, as before.
- Do not touch `.env`, `.env.example`, `next.config.mjs`, `package.json`,
  deployment configs, or anything outside `frontend/app`, `frontend/components`,
  and `frontend/app/globals.css`.
- No new features, no removed features, no changed business logic, no changed
  data flow, no changed routing structure — every route/folder name in
  `frontend/app` stays exactly as-is.
- If unsure whether something counts as "backend" or "logic," treat it as
  off-limits.

Re-read this section before calling the work done.

## 1. Context

Hirenomous's frontend is functionally complete but visually inconsistent:

- `globals.css` defines a violet `--primary` token, but most pages ignore it and
  hardcode their own colors ad hoc: campaigns hardcodes blue throughout
  (`bg-blue-*`/`text-blue-*`/`border-blue-*` on badges, tabs, and stat cards —
  **not** a status-color lookup object, just static classes), analytics is
  hardcoded teal, jobs/resumes/ai-recruiter hardcode raw hex, the landing page
  runs an entirely separate slate/blue/indigo palette, and the dashboard's
  Recharts area chart uses literal hex gradient stops.
- The dashboard chart also wraps oklch tokens in `hsl(var(--border))` /
  `hsl(var(--muted-foreground))` — invalid, since the tokens are oklch, not hsl
  components. Fix to raw `var(--x)`. Same chart, same data — rendering fix only.
- No shared component library beyond one unused `Button` — every card, table,
  badge, and modal is hand-rolled per page with duplicated class strings.
- Dark mode is declared (`.dark { color-scheme: dark; }`) but has no token
  overrides **and** nothing in the app ever applies the `dark` class to
  `<html>` — no toggle, no `next-themes`, no OS-preference wiring — and
  `viewport.colorScheme` is hardcoded to `'light'`. It is currently both
  unstyled and unreachable. Section 3 below fixes both halves of that.
- No webfont is loaded; body falls back to `font-family: Arial, Helvetica,
  sans-serif`.

Goal: reskin the entire product (marketing page, login, dashboard shell + all
dashboard pages, candidate interview flow) into one consistent
Workable/Landingfolio-style clean-SaaS system on the new teal/gold/navy palette,
without changing any route, endpoint call, request/response shape, form field,
or business-logic branch.

## 2. Token & foundation layer (`frontend/app/globals.css`)

Map the palette into the existing CSS-variable system (convert to oklch to match
the current format; keep the `@theme inline` indirection):

| Token | New color | Hex |
|---|---|---|
| `--primary` | deep teal | `#05746C` |
| `--accent` | soft teal | `#5FAFAE` |
| `--foreground` / dark-surface ink | navy | `#343454` |
| new `--warning` / gold accent | gold | `#E3AE42` |
| new `--warning-surface` / warm soft bg | light tan | `#EEC89D` |
| `--border` / `--muted-foreground` base | cool gray-blue | `#B4C0C6` |

- Keep `--destructive` as its current red — the palette has no red, and red
  still needs to read as "danger," distinct from gold/teal.
- Add `--success` (derived from the primary/accent teal) and `--warning`
  (`#E3AE42`), registered in the `@theme inline` block alongside the existing
  `--color-*` aliases so `bg-success`, `text-warning`, etc. become available —
  every status-badge pattern in the app needs these two semantic tokens.
- Add real `:root` → `.dark` overrides for every token (background, foreground,
  card, popover, primary, secondary, muted, accent, success, warning,
  destructive, border, input, ring, sidebar) — navy-tinted dark surfaces, teal
  stays the accent, gold stays legible on dark.
- Repurpose the dead `.job-card`, `.icon-button`, `.brand-mark`,
  `.avatar`/`.avatar-blue`, `.pin-dot` utility classes to the new palette
  instead of leaving them orphaned (presentational-only, safe to restyle).
- Radius stays on the existing `--radius: .55rem` scale — reuse
  `--radius-lg`/`--radius-xl` consistently instead of one-off `rounded-2xl`
  literals; no new radius system.
- Add a webfont via `next/font/google` in `frontend/app/layout.tsx` (bundled
  with Next.js, zero new dependency): Geist Sans for UI text, Geist Mono for
  stat/numeric figures (dashboard KPIs, interview scores). Wire the font
  variable into `<html>`/`<body>` `className`; remove the
  `font-family: Arial, Helvetica, sans-serif` line from `globals.css`.
- Fix the dashboard chart's `hsl(var(--border))` / `hsl(var(--muted-foreground))`
  Recharts props to raw `var(--x)`, and remap its gradient `stopColor` literals
  (`#818cf8`, `#fb923c`, `#34d399`) to teal/gold/navy equivalents.
- Contrast guardrail: gold (`#E3AE42`) and tan (`#EEC89D`) are light, warm colors.
  Use them as accents/borders/soft surfaces paired with navy or ink text — never
  as a background for white or low-contrast text. Spot-check any new
  gold/tan-on-text combination against WCAG AA (4.5:1 for body text) before
  committing.

## 3. Make dark mode reachable (fixes the "declared but unreachable" gap)

The token overrides in Section 2 are inert unless something can actually apply
the `dark` class. Add a minimal, dependency-free toggle — this is a pure UI
addition, no data fetching, no auth, nothing touching `lib/*`, so it's fully
within the frontend-only scope:

- `frontend/components/theme-provider.tsx` — new client component. On mount,
  reads `localStorage.getItem('theme')`, falls back to
  `matchMedia('(prefers-color-scheme: dark)')`, applies/removes the `dark`
  class on `document.documentElement`, persists the choice to `localStorage`,
  and exposes the current theme + a `toggleTheme()` via React context.
- `frontend/components/theme-toggle.tsx` — a Sun/Moon icon button
  (lucide-react is already installed) calling `toggleTheme()`.
- Wrap `{children}` in `<ThemeProvider>` inside `frontend/app/layout.tsx`
  (already being touched for the webfont change).
- Add a small inline blocking script in that same layout's `<head>` that sets
  the class on `<html>` before first paint, to avoid a flash of the wrong theme.
  No package needed — a literal `<script dangerouslySetInnerHTML>` reading
  `localStorage`/`matchMedia` and setting `document.documentElement.className`.
- Change `viewport.colorScheme` in `app/layout.tsx` from `'light'` to
  `'light dark'` so native form controls/scrollbars follow the toggle too.
- Place the `ThemeToggle` in the dashboard topbar (`(dashboard)/layout.tsx`)
  and in the landing page nav (`app/page.tsx`).
- Do **not** add a toggle to `app/interview/[token]/page.tsx` — leave the
  candidate-facing interview flow light-only and untouched by this section, to
  minimize risk on that delicate surface (see Section 5).

## 4. Shared component layer

Build entirely from what's already installed (`@base-ui/react`,
`class-variance-authority`, `tailwind-merge`, `clsx`, `lucide-react`) — no new
npm packages, `package.json` is not touched.

**Extend the existing `components/ui/button.tsx`** (not new — it already exists
and is fully token-based via `bg-primary`/`bg-destructive`/etc., so it will
inherit the repainted palette automatically) by adding `success` and `warning`
variants to `buttonVariants`, built on the new `--success`/`--warning` tokens
from Section 2. This closes a real asymmetry: candidates and interviews/`[id]`
both pair a "Select Candidate" action with a "Reject Candidate" action —
Reject already reads naturally as `destructive`, but Select has no matching
purpose-built variant today. Use the new `success` variant for "Select
Candidate" in both places (Section 5, steps 4 and 6) once it exists.

New files under `frontend/components/`:

- `components/ui/card.tsx` — Card/CardHeader/CardContent/CardFooter, replacing
  every hand-rolled `rounded-2xl border bg-card p-6 shadow-sm` block.
- `components/ui/badge.tsx` — `cva`-based status badge with variants (success,
  warning, info, destructive, neutral), replacing the separate hardcoded
  status-color logic in candidates (`getStatusColor`), interviews
  (`STATUS_STYLES`, `REC_STYLES`), and interviews/`[id]` (`scoreColor`,
  `barColor`).
- `components/ui/dialog.tsx` — built on `@base-ui/react/dialog` (already a
  dependency), replacing every hand-rolled `fixed inset-0` overlay modal (jobs
  create/edit, candidates detail, interviews `[id]` transcript/recording
  modals).
- `components/ui/table.tsx` — Table/TableHeader/TableRow/TableCell primitives
  for the data-table pages (dashboard, candidates, interviews, analytics,
  campaigns).
- `components/ui/progress.tsx` — replaces the literal `<div style={{width}}>`
  bars on the interview report page.
- `components/ui/select.tsx`, `components/ui/input.tsx`,
  `components/ui/tabs.tsx` — reskin the native `<select>`/`<input>`/custom-tab
  patterns used across most pages (including resumes' tabs and dropzone).
- `components/page-header.tsx` — reusable "hero-style header": eyebrow label +
  bold title + short supporting line + primary action button, used identically
  on every dashboard page's top section and, in a fuller marketing-hero form,
  on the landing page.
- `components/stat-tile.tsx` and `components/stat-strip.tsx` — the KPI-card
  pattern (dashboard, analytics, campaigns) and the compact stat-strip pattern
  for the landing page + analytics header.
- `components/empty-state.tsx` — consistent empty-state treatment for
  tables/lists with no rows.
- `components/status-pill.tsx` — thin wrapper over Badge mapping each domain
  status string (candidate status, interview status/recommendation, campaign
  call status) to one variant, replacing the ad hoc per-page color logic with
  one shared source of truth per domain.

These are additive and purely presentational — imported into existing pages in
place of inline markup, no change to any prop/behavior contract with the
backend.

## 5. Page-by-page application

Applied in this order. Each pass only swaps JSX structure/classNames for the
new tokens/primitives and preserves every existing state variable, handler,
conditional branch, and API call verbatim:

1. **`app/(dashboard)/layout.tsx`** — sidebar/topbar restyled with new tokens,
   brand glyph → a teal-on-tan icon mark, `ThemeToggle` added to the topbar;
   same nav array/active-state logic/mobile toggle untouched.
2. **`app/(dashboard)/dashboard/page.tsx`** — stat tiles → `StatTile`, funnel
   row and table restyled, chart gradient stops + `hsl()` bug fixed per
   Section 2, hero-style `PageHeader`.
3. **`app/(dashboard)/jobs/page.tsx`** — `.job-card` → new `Card`, create/edit
   modal → `Dialog`. LinkedIn/Naukri/SharePoint integration buttons **keep
   their real brand hex** — correct, not part of the app's palette.
4. **`app/(dashboard)/candidates/page.tsx`** — filters/table → shared `Table`,
   `getStatusColor` → `StatusPill`, detail view → `Dialog`; every
   status-keyed conditional branch (interested/interview/completed/selected/
   rejected) kept exactly, only its wrapping markup changes.
5. **`app/(dashboard)/campaigns/page.tsx`** — heaviest off-brand page. There is
   no status-color map here — just replace every static `bg-blue-*`/
   `text-blue-*`/`border-blue-*` class (badges, tab pills, stat cards, buttons)
   with the equivalent teal/gold/navy tokens or the new `Badge`/`StatTile`
   components; tabs → `Tabs`.
6. **`app/(dashboard)/interviews/page.tsx` + `interviews/[id]/page.tsx`** —
   `STATUS_STYLES`/`REC_STYLES`/`scoreColor`/`barColor` → `StatusPill` +
   `Progress`; `[id]` page's inline JSX split into `ScoreCard`/`BreakdownBar`/
   `TranscriptModal`/`RecordingModal` sub-components, same data/handlers.
7. **`app/(dashboard)/resumes/page.tsx`** — dropzone/tabs restyled, hardcoded
   `#7a49fb` gradient and violet-tinted shadow replaced with teal/gold
   equivalents.
8. **`app/(dashboard)/ai-recruiter/page.tsx`** — config form + chat simulator
   restyled, the `#f8fafc` repeating-gradient "notebook line" background
   remapped to a token-driven equivalent.
9. **`app/(dashboard)/analytics/page.tsx`** — currently the most bare (no
   charts/stat cards despite the name) and already accidentally teal; bring
   onto the shared system and give it a `StatStrip` header. No new data/metrics
   invented — only existing table/filter data surfaced more richly.
10. **`app/(dashboard)/settings/page.tsx`** — cleanest page already (fully
    token-based); light visual pass only.
11. **`app/page.tsx`** — full rebuild onto the token system (currently a
    disconnected slate/blue/indigo palette): hero (eyebrow + headline +
    supporting line + CTA), `ThemeToggle` in the nav, feature blocks with
    icon-in-rounded-square accents, a stat/logo strip, alternating content
    sections per the Landingfolio/Workable reference, footer. Same routes/
    links (`/dashboard`, `/login`), same copy intent.
12. **`app/login/page.tsx`** — already token-consistent; visual polish only
    (brand mark, spacing, type), auth POST logic untouched.
13. **`app/interview/[token]/page.tsx` + `app/interview/layout.tsx`** — most
    delicate surface: only reskin wrapper markup/classNames around the
    existing phase state machine (loading/device-check/interview/complete/
    error), remap the stray `emerald-*` literals to the new `--success` token,
    and do not touch any ref, id, ARIA attribute, `MediaRecorder`/
    `getUserMedia` wiring, or the `interviewApi` calls. No theme toggle here
    (see Section 3) — light-only.

## 6. Verification

- Run `npm run dev` in `frontend/` and click through every route above in a
  real browser: landing → login → dashboard shell nav → each dashboard page →
  a job detail modal → a candidate detail modal → an interview report page →
  the candidate interview flow at `/interview/[token]` (device-check screen at
  minimum; full recording flow requires camera/mic permission but should
  render correctly).
- Click the new `ThemeToggle` and confirm the dashboard shell, at least one
  data-table page, and the landing page all render correctly in dark mode —
  this is now literally testable since the toggle makes dark mode reachable.
- Confirm every network call target is unchanged: spot-check jobs, candidates,
  interviews, and voice-call list/detail calls in the browser Network tab
  match the same endpoints/methods as before the redesign.
- Confirm `frontend/lib/api.ts`, `frontend/lib/interview-api.ts`,
  `frontend/lib/auth-context.tsx` are byte-identical to their pre-redesign
  state (or only carry the trivial prop/type addition the hard rule allows).
- Confirm `package.json` has no diff (no new dependencies were needed).
- Responsive pass: collapse the viewport to mobile width and confirm the
  sidebar toggle, dashboard cards, and every data table still work and don't
  overflow, on at least the dashboard shell, candidates, and the landing page.
- Keyboard/focus pass: tab through and press Escape on the new `Dialog`,
  `Select`, and `Tabs` components (built on `@base-ui`) to confirm focus trap
  and keyboard support work — don't just assume the primitive handles it.
- Confirm the new `success` button variant renders correctly on "Select
  Candidate" in both candidates and interviews/`[id]`, visually paired with
  the existing `destructive` "Reject Candidate" button.
