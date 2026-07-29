---
name: tailwind-design-system
description: Provides a consistent Tailwind CSS design system (colors, spacing, typography, component patterns) for a clean, professional, data-dense financial dashboard UI in a dark theme.
---

# Tailwind Design System (Financial Dashboard)

This skill provides a standardized design system for styling the SilverSense application using Tailwind CSS, focusing on a premium financial dashboard aesthetic.

## Logic and Requirements

1. **Theme:**
   - **Dark Mode Only:** Optimized for low eye strain during long trading sessions.
   - **Color Palette:**
     - Backgrounds: Deep slate/charcoal (e.g., `bg-slate-900`, `bg-slate-800` for panels).
     - Text: High contrast off-whites (`text-slate-100`, `text-slate-300`).
     - Accents/Trading: Bright, distinguishable colors for action (e.g., `text-emerald-400` for bullish/profit, `text-rose-500` for bearish/loss, `text-cyan-400` for active/neutral highlights).

2. **Typography & Spacing:**
   - Clean, modern sans-serif fonts (e.g., Inter or Roboto).
   - **Data-Dense Layout:** Tighter spacing (`p-2`, `gap-2`, `text-sm`, `text-xs`) to display maximum information without feeling cluttered.

3. **Component Patterns:**
   - **Cards/Panels:** `bg-slate-800 rounded-lg border border-slate-700 shadow-md p-4`
   - **Data Tables:** Striped rows (`even:bg-slate-800`), sticky headers, monospace fonts for numbers.
   - **Badges:** Small rounded pills for status/sentiment (`bg-emerald-900/50 text-emerald-400 px-2 py-0.5 rounded-full text-xs`).

4. **Consistency:** Ensure all UI elements strictly adhere to these patterns. Avoid arbitrary utility values.

## Usage

Use this skill when building or styling UI components for the SilverSense dashboard to ensure a cohesive, professional appearance.
