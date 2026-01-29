# UI Layout Specification

Defines the intended layout contracts for Alfred's frontend. Any UI work that touches layout, scroll, or viewport sizing should reference this doc.

---

## Mobile Viewport Model

**Rule: On initial load, the entire UI fits in one screen. No scroll adjustment needed.**

The app uses `100dvh` (dynamic viewport height) as the root container height. This adapts to the mobile browser's address bar state, so the layout always fills exactly the visible area.

```
┌────────────────────────────────┐
│  Mobile Header (~52px)         │  flex-shrink-0
│  "Alfred"     [+ New] [Settings]
├────────────────────────────────┤
│                                │
│  Messages Area (flex-1)        │  overflow-y-auto (ONLY scroll container)
│  ┌──────────────────────────┐  │
│  │ Welcome message          │  │
│  └──────────────────────────┘  │
│                                │
│        (white space)           │
│                                │
├────────────────────────────────┤
│  ChatInput (~52px)             │  flex-shrink-0
│  [Ask Alfred anything...  ▶]   │
├────────────────────────────────┤
│  BottomTabBar (48px)           │  fixed bottom-0, z-sticky
│  [Chat]         [Browse]       │
└────────────────────────────────┘
```

### Component Height Budget (mobile)

| Component | Height | Sizing |
|-----------|--------|--------|
| Mobile Header | ~52px | `flex-shrink-0`, py-3 + text |
| Messages Area | remaining | `flex-1`, scrollable |
| ChatInput | ~52px | `flex-shrink-0`, py-3 + input |
| BottomTabBar | 48px (h-12) | `fixed bottom-0`, overlays content |
| **main padding-bottom** | 48px (pb-12) | Reserves space behind fixed tab bar |

### Viewport Height

- Root container: `h-dvh` (100dvh) -- adapts to mobile address bar
- Never use `h-screen` (100vh) on mobile -- 100vh includes the area behind the browser chrome, causing content to overflow the visible area
- Body: `min-height: 100dvh`

---

## Scroll Ownership

**Rule: Exactly one scroll container per view. Never nest scrollable areas.**

| View | Scroll Container | Notes |
|------|-------------------|-------|
| Chat | Messages area (`flex-1 overflow-y-auto`) | ChatInput stays fixed at bottom |
| Entity lists | `<main>` (`flex-1 overflow-auto`) | Standard page scroll |

### Auto-Scroll Behavior

- On initial load: **do not scroll**. Content must fit in viewport without scrolling.
- On new message (user sends or assistant responds): scroll to bottom only if user is already near the bottom (within 100px threshold).
- This prevents mobile Chrome/Safari from triggering address bar hide on load, which causes jarring layout shifts.

Implementation: `initialMessageCount` ref tracks mount-time message count. Scroll effect only fires when `messages.length > initialMessageCount.current`.

---

## Desktop Layout

```
┌──────────┬──────────────────────────┐
│ Sidebar  │                          │
│ (240px)  │  Page Content             │
│          │  (flex-1, overflow-auto)  │
│ Logo     │                          │
│ Nav      │  ┌─ Messages (scroll) ─┐ │
│ User     │  │                     │ │
│          │  └─────────────────────┘ │
│          │  [ChatInput]             │
└──────────┴──────────────────────────┘
```

- Sidebar: `w-[240px]`, hidden on mobile (`hidden md:flex`)
- No BottomTabBar on desktop (`md:hidden`)
- No mobile header on desktop (`md:hidden`)
- Main area: no bottom padding on desktop (`pb-12 md:pb-0`)

---

## Key CSS Decisions

| Decision | Value | Why |
|----------|-------|-----|
| Viewport unit | `dvh` not `vh` | 100vh includes browser chrome on mobile |
| Root overflow | `overflow-hidden` | Prevents body scroll; child containers own scroll |
| Tab bar position | `fixed` not flex child | Overlays content; doesn't affect flex layout |
| Tab bar space | `pb-12` on main | Prevents content from hiding behind fixed tab bar |
| Safe area | `safe-area-bottom` on tab bar | Handles notched devices (iPhone) |

---

## Anti-Patterns (things that have caused bugs)

1. **Using `h-screen` on mobile** -- 100vh overshoots the visible area when the address bar is visible
2. **Auto-scrolling on mount** -- Triggers Chrome address bar hide, causing layout shift and pushing header out of view
3. **Nested scroll containers** -- `overflow-auto` on main + `overflow-y-auto` on messages = confusing scroll behavior. Only one should scroll per view.
4. **Forgetting `pb-12` on mobile** -- Fixed tab bar overlaps the last content item
