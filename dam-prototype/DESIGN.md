# DAM Workspace — Design System

> Vilavi PIM Digital Asset Management. Internal tool for e-commerce operations team.
> Bilingual: Chinese + English. Non-technical users. 2000+ product SKUs.

---

## 1. Visual Theme & Atmosphere

**Direction: Refined Functional**

The interface is a tool, not a decoration. Assets are the hero — the UI recedes.
Clean, restrained, professional. Zero learning curve. Works in warehouses and offices.

- **Tone**: Calm competence. Fast. Trustworthy. Invisible.
- **Differentiation**: The one thing users remember is "it just works" — zero friction
- **Dark mode**: Auto-follows system preference for varied lighting environments

---

## 2. Color Palette

All colors defined as CSS custom properties for runtime theming.

### Light Mode

| Token | Hex | Usage |
|-------|-----|-------|
| `--bg` | `#FFFFFF` | Page background |
| `--bg-sidebar` | `#F1F5F9` | Left navigation panel |
| `--surface` | `#FFFFFF` | Cards, modals, detail panel |
| `--surface-hover` | `#F8FAFC` | Hover state on cards/rows |
| `--border` | `#E2E8F0` | Dividers, card borders, inputs |
| `--border-focus` | `#2563EB` | Focus ring on inputs |
| `--text` | `#0F172A` | Primary text, headings |
| `--text-secondary` | `#64748B` | Labels, metadata, secondary info |
| `--text-muted` | `#94A3B8` | Placeholders, disabled text |
| `--primary` | `#2563EB` | Primary buttons, links, active states |
| `--primary-hover` | `#1D4ED8` | Button hover |
| `--primary-light` | `#EFF6FF` | Selected bg, active filter pills |
| `--success` | `#16A34A` | Confirmed, active, uploaded |
| `--warning` | `#F59E0B` | Pending, AI-suggested, needs review |
| `--error` | `#EF4444` | Errors, missing files, rejected |
| `--tag-bg` | `#F1F5F9` | Manual tag pill background |
| `--tag-text` | `#334155` | Manual tag pill text |
| `--tag-ai-bg` | `#FEF9C3` | AI-suggested tag background (yellow tint) |
| `--tag-ai-text` | `#A16207` | AI-suggested tag text |
| `--shadow-sm` | `0 1px 2px rgba(0,0,0,0.05)` | Subtle elevation |
| `--shadow` | `0 1px 3px rgba(0,0,0,0.1), 0 1px 2px rgba(0,0,0,0.06)` | Card elevation |
| `--shadow-lg` | `0 10px 15px rgba(0,0,0,0.1), 0 4px 6px rgba(0,0,0,0.05)` | Modal/dialog |

### Dark Mode

| Token | Hex | Usage |
|-------|-----|-------|
| `--bg` | `#0F172A` | Page background |
| `--bg-sidebar` | `#1E293B` | Left navigation panel |
| `--surface` | `#1E293B` | Cards, modals, detail panel |
| `--surface-hover` | `#334155` | Hover state |
| `--border` | `#334155` | Dividers, card borders |
| `--text` | `#F8FAFC` | Primary text |
| `--text-secondary` | `#94A3B8` | Secondary text |
| `--text-muted` | `#64748B` | Placeholders |
| `--primary` | `#3B82F6` | Primary (brighter for dark bg) |
| `--primary-light` | `#1E3A5F` | Selected bg |
| `--tag-bg` | `#334155` | Manual tag pill bg |
| `--tag-text` | `#CBD5E1` | Manual tag pill text |
| `--tag-ai-bg` | `#422006` | AI tag pill bg |
| `--tag-ai-text` | `#FDE68A` | AI tag pill text |

---

## 3. Typography

### Font Stack

```css
font-family: "Inter", "Noto Sans SC", "PingFang SC", "Microsoft YaHei",
             -apple-system, BlinkMacSystemFont, sans-serif;
```

| Role | Font | Weight | Size | Line-height |
|------|------|--------|------|-------------|
| Page title | Inter | 600 | 18px | 1.3 |
| Section heading | Inter | 500 | 14px | 1.4 |
| Body text | Inter | 400 | 13px | 1.5 |
| Small / metadata | Inter | 400 | 11px | 1.4 |
| Monospace / codes | JetBrains Mono | 400 | 12px | 1.5 |

### CJK Fallback

Chinese text renders in Noto Sans SC → PingFang SC (Mac) → Microsoft YaHei (Windows).
Inter takes Latin glyphs; CJK fonts take Han characters. Weights are matched (400↔400, 500↔500, 600↔700 in CJK).

---

## 4. Component Styles

### Buttons

| Variant | BG | Text | Border | Hover |
|---------|-----|------|--------|-------|
| Primary | `var(--primary)` | `#FFF` | none | `var(--primary-hover)` |
| Secondary | `transparent` | `var(--text)` | `var(--border)` | `var(--bg)` |
| AI (gradient) | `linear-gradient(135deg, #7C3AED, #2563EB)` | `#FFF` | none | opacity 0.9 |
| Ghost | `transparent` | `var(--text-secondary)` | none | `var(--surface-hover)` |
| Danger | `var(--error)` | `#FFF` | none | darker red |

- Border-radius: 6px
- Padding: 6px 14px (sm: 4px 10px)
- Font-size: 13px, weight 500
- Transition: all 0.15s ease

### Inputs

- Border: 1px `var(--border)`, radius 6px
- Padding: 6px 10px, font-size 13px
- Background: `var(--bg)`, color: `var(--text)`
- Focus: border → `var(--primary)`, ring 2px `var(--primary-light)`
- Placeholder: `var(--text-muted)`

### Tags / Pills

- Border-radius: 12px (fully rounded)
- Padding: 2px 8px, font-size 12px
- Manual tags: bg `var(--tag-bg)`, text `var(--tag-text)`
- AI tags: bg `var(--tag-ai-bg)`, text `var(--tag-ai-text)`, border 1px dashed `var(--warning)`

### Cards (Thumbnails)

- Border-radius: 6px
- Border: 2px transparent → `var(--primary)` on hover/selected
- Box-shadow: `var(--shadow)` → `var(--shadow-lg)` on hover
- Selected: border `var(--primary)` + outer ring 2px `var(--primary-light)`
- Aspect-ratio: 1 (square)
- Overflow: hidden
- Image: `object-fit: cover`, 100% width/height

### Checkbox (selection)

- Position: top-left of card, 6px inset
- Size: 20px circle
- Hidden by default, visible on `.selected` card
- BG: `var(--primary)`, checkmark: white

---

## 5. Layout Principles

### Master Layout

```
+--Sidebar--+--Content Area-----------------------------------+
| 220px     | Toolbar: 52px height, sticky top                |
| flex-col  +--------------------------------------------------+
| filters   | Grid: CSS Grid auto-fill minmax(160px, 1fr)     |
| tags      | Gap: 12px, padding: 16px                         |
| search    |                                                  |
+-----------+--Detail Panel (320px, slide from right)----------+
```

### Sidebar (220px)

- Background: `var(--bg-sidebar)`
- Border-right: 1px `var(--border)`
- Sections: Asset Type, Tags, Product Search, Sort
- Section headers: 11px uppercase, `var(--text-muted)`, letter-spacing 0.5px
- Collapsible via hamburger toggle (future)

### Grid Area

- Fills remaining space, overflow-y: auto
- Batch action bar appears between toolbar and grid when 2+ selected
- Empty state centered with icon + CTA button
- Scroll: smooth, momentum-preserving

### Detail Panel (320px)

- Slides from right edge
- Border-left: 1px `var(--border)`
- Header: sticky top, filename + close button
- Body: preview image → fields → tags → product link → metadata
- Collapses to 0 when no asset selected

### Toolbar (52px)

- Background: `var(--surface)`
- Border-bottom: 1px `var(--border)`
- Flex row, gap 10px, padding 0 16px
- Left: page title + asset count
- Right: action buttons (Upload, AI Auto-Tag, Deselect)

---

## 6. Depth & Hierarchy

Three elevation levels only:

| Level | Shadow | Usage |
|-------|--------|-------|
| 0 | none | Content area, sidebar |
| 1 | `var(--shadow-sm)` | Cards (default) |
| 2 | `var(--shadow)` | Cards (hover), detail panel, toolbar |
| 3 | `var(--shadow-lg)` | Modals, upload dialog, toasts |

Z-index stack:
- Grid: 0
- Detail panel: 10
- Toolbar: 10
- Batch bar: 15
- Upload overlay: 100
- Toast: 200

---

## 7. Do's and Don'ts

### DO
- Use CSS variables for ALL colors — never hardcode hex values
- Auto-detect dark mode via `prefers-color-scheme`
- Use the defined font stack — never system fonts
- Keep cards square (aspect-ratio: 1) for visual consistency
- Use `var(--primary-light)` for selected states, not opacity tricks
- Show count badges next to filter labels (e.g., "Images 12")
- Use `transition: all 0.15s` for hover/click feedback
- Chinese labels for UI elements; English for file names is OK

### DON'T
- Never use purple gradients on white backgrounds
- Never use Inter/Roboto/Arial/system fonts as primary — Inter is ok as Latin font
- Never use glassmorphism effects
- Never hide the detail panel close button
- Never truncate filenames without ellipsis
- Never auto-save without visual feedback (use toasts)
- Never block the grid with the detail panel — slide over, don't push

---

## 8. Responsive Behavior

### Breakpoints (min-width)

| Width | Behavior |
|-------|----------|
| ≥ 1024px | Full layout: sidebar + grid + detail panel |
| 768–1023px | Sidebar collapsed (icon-only, 48px), grid fills space |
| < 768px | Sidebar hidden, grid 2 columns, detail panel full-width overlay |

### Grid Columns (auto-fill)

- Default: `minmax(160px, 1fr)` — typically 5-6 columns at 1440px
- Tablet: `minmax(140px, 1fr)` — typically 3-4 columns
- Mobile: `minmax(120px, 1fr)` — 2 columns

---

## 9. Agent Prompting Guide

When generating or modifying the DAM frontend:

1. **ALWAYS reference `--var()`** for colors — never hardcode `#2563EB` in a component
2. **Use the font stack**: `font-family: var(--font-sans)` (define `--font-sans` once)
3. **Cards follow the card pattern**: square, 6px radius, transparent→blue border on hover
4. **Detail panel slides from right**: 320px, `position: relative` in flex layout, not `position: fixed`
5. **Empty states matter**: show icon + message + CTA, not a blank area
6. **Batch bar appears between toolbar and grid**: conditional `v-if="selected.length > 1"`
7. **Toasts**: bottom-right, slide up, auto-dismiss 3s, max 3 visible
8. **Dark mode**: always test both light and dark in the same change

---

**Version**: 1.0 | **Created**: 2026-06-09
