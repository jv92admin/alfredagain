# Post-Onboarding Education System Specification

**Date:** 2026-02-01
**Status:** Implemented (Phase 1)
**Scope:** Home dashboard, capabilities reference page, smart nudging, chat prompt prefill
**Depends on:** [onboarding-spec.md](onboarding-spec.md) (onboarding flow must be complete before this kicks in)

---

## Problem

After completing onboarding, users land on a marketing-style About page with no actionable next step. They have pantry items from onboarding but zero recipes, no meal plans, and no shopping lists. The empty state gives no guidance on what to do first or how Alfred's features connect.

## Solution

Two new pages and a set of modifications to existing views:

1. **Home Dashboard** (`/home`) — the new default landing page after onboarding
2. **Capabilities Page** (`/capabilities`) — standalone reference for Alfred's features
3. **Smart nudging** — contextual suggestions based on kitchen state
4. **Chat prompt prefill** — "Try it" buttons that navigate to chat with a pre-written prompt

---

## Implementation Summary

### What Changed

| File | Change |
|------|--------|
| `frontend/src/components/Views/HomeView.tsx` | **New.** Dashboard with stat cards, nudge cards, RecipeImportModal |
| `frontend/src/components/Views/CapabilitiesView.tsx` | **New.** Reference page with 6 anchored capability sections |
| `frontend/src/App.tsx` | Added `/home` and `/capabilities` routes. Post-onboarding redirect changed from `/about` to `/home`. Catch-all changed from `/` to `/home`. |
| `frontend/src/components/Layout/AppShell.tsx` | Added Home + Capabilities to sidebar nav. Logo made clickable (links to `/home`). Capabilities added to mobile hamburger menu. Added `end` prop to Chat NavLink. |
| `frontend/src/components/Layout/BrowseDrawer.tsx` | Added Capabilities to browse items |
| `frontend/src/components/Chat/ChatView.tsx` | Added prefill prompt support via `location.state.prefillPrompt` |
| `frontend/src/components/Views/AboutView.tsx` | Removed scrollytelling (How It Works) and @mentions sections. Added link to `/capabilities`. CTA now links to `/home`. |

### What Did NOT Change

- **No backend changes.** All data fetched from existing `/api/entities/{table}` endpoints.
- **No new database tables.** No `user_education` table, no progress tracking.
- **No lesson system.** Capabilities page is static reference content, not interactive tutorials.
- **BottomTabBar unchanged.** Neither `/home` nor `/capabilities` are in `browsePages` — both tabs appear muted on those routes (intentional).

---

## Home Dashboard (`/home`)

### Data Fetching

On mount, fires `Promise.allSettled` across 5 existing CRUD endpoints:

| Endpoint | Maps to |
|----------|---------|
| `/api/entities/recipes` | `counts.recipes` |
| `/api/entities/inventory` | `counts.inventory` |
| `/api/entities/shopping_list` | `counts.shopping` |
| `/api/entities/meal_plans` | `counts.meals` |
| `/api/entities/tasks` | `counts.tasks` |

Each returns `{ data: Entity[], count: number }`. Uses `.data.length` as primary, `.count` as fallback.

### Layout

1. **Greeting** — time-of-day based:
   - 5:00–11:59 → "Good morning!"
   - 12:00–16:59 → "Good afternoon!"
   - 17:00–20:59 → "Good evening!"
   - 21:00–4:59 → "Hey there!"

2. **Stat cards** — responsive grid (`grid-cols-2 sm:grid-cols-3 lg:grid-cols-5`):
   - Recipes | Pantry | Shopping | Meals | Tasks
   - Each card shows count + label, clicks through to the relevant view

3. **Nudge cards** — top 1–2 contextual suggestions (see Nudge Logic below)

4. **Quick actions** — "Chat with Alfred" and "What can Alfred do?" links

### Nudge Logic

Pure client-side function computed from counts on every render. No database storage.

| Priority | Condition | Title | Primary CTA | Secondary |
|----------|-----------|-------|-------------|-----------|
| 1 | `recipes === 0` | "Get your first recipe" | "Ask Alfred to Create" → chat prefill | "Import from URL" → RecipeImportModal |
| 2 | `inventory < 10` | "Your Pantry" | "Add Pantry Items" → `/inventory` | "Learn more" → `/capabilities#inventory` |
| 3 | `recipes > 5 && meals === 0` | "Plan your week" | "Plan Meals" → chat prefill | "Learn more" → `/capabilities#meal-planning` |
| 4 | `meals > 0 && shopping === 0` | "Build your shopping list" | "Generate Shopping List" → chat prefill | "Learn more" → `/capabilities#shopping` |
| — | All conditions false | "You're all set!" | "Chat with Alfred" → `/` | — |

Only the top 2 nudges are shown to avoid overwhelming users.

### Recipe Nudge Design Decision

The first recipe nudge uses **"Ask Alfred to Create" as the primary CTA** (not URL import). This teaches users the core interaction pattern: chat-first. URL import is secondary (outline button) for power users who already have a recipe bookmarked.

### Pantry Nudge Framing

Pantry is framed as **fuel for other features**, not a standalone chore:
> "Alfred works best when it knows what you have. This powers recipe suggestions that use your actual ingredients, shopping lists that skip what you already own, and meal plans that minimize waste."

### RecipeImportModal

Imported from `../Recipe` and rendered directly in HomeView with local `showImportModal` state. On success, calls `fetchCounts()` to refresh the dashboard. User stays on the home page throughout.

---

## Capabilities Page (`/capabilities`)

### Structure

Single scrollable page with 6 anchored sections. Each section is a `<section id="...">` element, deep-linkable via URL hash (e.g., `/capabilities#meal-planning`).

### Sections

| ID | Title | Has "Try" Prompt | Has View Link |
|----|-------|------------------|---------------|
| `recipe-import` | Getting Recipes | "Suggest a simple dinner recipe using my current pantry" | `/recipes` |
| `inventory` | Your Pantry | "What ingredients am I running low on?" | `/inventory` |
| `meal-planning` | Meal Planning | "Help me plan 4 dinners for this week using my saved recipes" | `/meals` |
| `shopping` | Shopping Lists | "Build a shopping list for my planned meals" | `/shopping` |
| `cook-mode` | Cook Mode | — (requires recipe selection, not a text prompt) | — |
| `mentions` | @Mentions | — (explaining a feature, not actionable via prompt) | — |

### "Try Asking Alfred" Prompts

Each section (where applicable) includes a subtle prompt line at the bottom:

```
────────────────────────────────────────────
"Suggest a simple dinner recipe using my pantry"  [ Try → ]
```

Clicking "Try" navigates to `/` with the prompt prefilled in the chat input via React Router navigation state.

### Deep Linking

On mount, checks `useLocation().hash`. If present, scrolls to the matching `<section id>` element with `scrollIntoView({ behavior: 'smooth' })` after a 100ms delay (allows render to complete).

---

## Chat Prompt Prefill Mechanism

### How It Works

Navigation state carries the prompt:

```tsx
// From HomeView or CapabilitiesView
navigate('/', { state: { prefillPrompt: 'Help me plan meals...' } })

// In ChatView, on mount
useEffect(() => {
  const state = location.state as { prefillPrompt?: string } | null
  if (state?.prefillPrompt) {
    setInput(state.prefillPrompt)
    chatNavigate('/', { replace: true, state: {} })
  }
}, [location.state])
```

The prompt is **prefilled but not auto-sent** — the user sees it in the input field and can edit before sending. Navigation state is cleared immediately to prevent re-triggering on refresh.

### Prompt Catalog

| Source | Prompt Text |
|--------|-------------|
| Home: no recipes | "Suggest a simple dinner recipe using my current pantry" |
| Home: low inventory | (navigates to `/inventory`, no chat prompt) |
| Home: no meal plan | "Help me plan 4 dinners for this week using my saved recipes" |
| Home: no shopping | "Build a shopping list for my planned meals" |
| Capabilities: recipe-import | "Suggest a simple dinner recipe using my current pantry" |
| Capabilities: inventory | "What ingredients am I running low on?" |
| Capabilities: meal-planning | "Help me plan 4 dinners for this week using my saved recipes" |
| Capabilities: shopping | "Build a shopping list for my planned meals" |

---

## Routing Changes

| Route | Before | After |
|-------|--------|-------|
| Post-onboarding redirect | `/about` | `/home` |
| Catch-all (`*`) | `/` (Chat) | `/home` |
| `/home` | — | HomeView (new) |
| `/capabilities` | — | CapabilitiesView (new) |
| `/about` | Full scrollytelling page | Simplified (hero, problem, not-AI, maker note, CTA) |

### Navigation Updates

| Location | Change |
|----------|--------|
| Desktop sidebar | Added Home (first) + Capabilities (after Preferences) |
| Desktop logo | Clickable, links to `/home` |
| Mobile logo | Clickable, links to `/home` |
| Mobile hamburger menu | Added Capabilities |
| Mobile BrowseDrawer | Added Capabilities item |
| Mobile BottomTabBar | Unchanged (Chat \| Browse) |
| Chat NavLink | Added `end` prop to prevent `/` matching all routes |

---

## About Page Simplification

### Removed
- Section 3: "How It Works" sticky scrollytelling (STEPS array, PhoneFrame component, desktop sticky + mobile stacked layouts)
- Section 4: "Assistant" section with @mentions demo and PhoneFrame

### Kept
- Section 1: Hero gradient
- Section 2: Problem/Solution cards ("The Chaos" / "The Calm")
- Section 4→3: "Not AI-First" bullet list
- Section 6→5: Maker Note from V
- Section 7→6: CTA (target changed from `/` to `/home`)

### Added
- New Section 3: Link card → "See what Alfred can do →" linking to `/capabilities`

---

## Phase 2 (Deferred)

These are explicitly **not built** and should only be considered after observing real user behavior:

| Item | When to Consider |
|------|-----------------|
| Interactive lesson system (step-by-step tutorials) | If users consistently fail to complete first recipe |
| Progress tracking (`user_education` table) | If lesson system is built |
| Personalized chat greeting based on kitchen state | If current nudge system doesn't drive engagement |
| Dismissible home dashboard | If returning users find the dashboard redundant |
| Onboarding → first recipe guided flow | If drop-off between onboarding and first recipe is high |
