# Build brief — "Lingua": language detect + translate frontend

Paste this whole file to your coding agent as the task.

---

## Task

Build a single-page frontend where a user types text in any language and can either (a) check which language it is, or (b) translate it into a chosen target language. Plain HTML + CSS + vanilla JS (or React if the repo already uses it). No build step required.

## Visual style — "Modernist"

Flat, architectural, Swiss-grid. Everything set in **Archivo** (Google Fonts, weights 400/600/800). Near-mono: ink on a light ground with one red accent. **Zero border radius anywhere. 2px rules, never hairlines. Everything flush left — including button labels and headlines. No shadows except the tokens below, no gradients, no emoji, no icons other than Lucide.**

Define these CSS variables in `:root` and use them instead of literal values:

```css
@import url('https://fonts.googleapis.com/css2?family=Archivo:wght@400;600;800&display=swap');

:root {
  --color-bg: #f3f2f2;
  --color-surface: #eae9e9;
  --color-text: #201e1d;
  --color-accent: #ec3013;
  --color-divider: color-mix(in srgb, #201e1d 40%, transparent);

  --color-neutral-200: #eae7e7;
  --color-neutral-300: #d7d3d3;
  --color-neutral-600: #7d7979;
  --color-neutral-700: #605d5d;
  --color-neutral-800: #444141;
  --color-neutral-900: #2d2b2b;

  --color-accent-200: #ffe0d9;
  --color-accent-600: #dd2b0f;
  --color-accent-700: #ae1800;
  --color-accent-800: #7c1405;

  --font-heading: "Archivo", system-ui, sans-serif;  /* weight 800 */
  --font-body: "Archivo", system-ui, sans-serif;

  --space-1: 4px; --space-2: 8px; --space-3: 12px;
  --space-4: 16px; --space-6: 24px; --space-8: 32px;

  --radius-md: 0px;
}
```

Rules that matter:
- Body: `background: var(--color-bg); color: var(--color-text); font-family: var(--font-body); margin: 0`.
- Section separation is a `2px solid var(--color-divider)` rule, not whitespace.
- Inputs: `background: var(--color-surface); border: 2px solid var(--color-text); border-radius: 0`.
- Primary button: solid `var(--color-accent)` fill, white 600-weight label, **left-aligned**; hover `--color-accent-600`, active `--color-accent-700`.
- Secondary button: transparent fill, `2px solid var(--color-text)`; hover `--color-neutral-200`, active `--color-neutral-300`.
- Focus: `:focus-visible { outline: 2px solid var(--color-accent); outline-offset: 2px; }` — never the browser default.
- Accent red is for the primary action and small uppercase emphasis only. Small labels are 11px, uppercase, `letter-spacing: .12em`, color `--color-neutral-700`.
- Body copy at accent color must use `--color-accent-700` (contrast).

## Layout (top to bottom, single column, `max-width: 860px`, flush left, padding `--space-8 --space-6`)

1. **Header bar** — full width, `border-bottom: 2px solid var(--color-divider)`, padding `--space-4 --space-6`. Left: wordmark "LINGUA" (heading font, 800, 18px, uppercase). Right: small uppercase label "Detect & Translate".
2. **Headline** — heading font 800, `clamp(32px, 6vw, 52px)`, `line-height: 1.02`, `letter-spacing: -.02em`. Copy: "Type anything. We'll name it or turn it." Below it one paragraph, 15px, `max-width: 48ch`, `--color-neutral-800`: "Paste a phrase in any language. Check which language it is, or translate it into the language you pick."
3. **Input block** (above it a 2px top rule):
   - Small uppercase label "YOUR TEXT".
   - `<textarea>` 5 rows, full width, 17px, `line-height: 1.45`, padding `--space-4`, vertical resize only. Placeholder: `Wo ist der nächste Bahnhof?`
   - Control row (flex, wrap, `gap: --space-4`, aligned to bottom):
     - Labelled `<select>` "TRANSLATE INTO", `appearance: none`, min-width 200px. Options: English, Spanish, French, German, Japanese, Mandarin Chinese, Arabic, Hindi, Portuguese, Russian, Korean, Italian. Default English.
     - Secondary button **"Check language"**.
     - Primary button **"Translate"**.
   - Both buttons disabled while a request is in flight.
4. **Status / error** — while loading, a small uppercase `--color-accent-700` line "WORKING…". On error, a 14px message in a `--color-accent-200` box with `border-left: 2px solid var(--color-accent)`, text `--color-accent-800`.
5. **Result panel** (only after a result; 2px top rule above it) — a bordered 2-cell grid (`grid-template-columns: repeat(auto-fit, minmax(180px, 1fr))`, `background: var(--color-surface)`, `border: 2px solid var(--color-text)`, cells split by a 2px divider):
   - Cell 1 kicker "LANGUAGE" (detect) or "TRANSLATION — {TARGET}" (translate); below it the answer in heading font 800, 28px.
   - Cell 2 kicker "DETAIL"; below it one or two sentences of explanation, 15px.
6. **Recent** (only when history exists) — heading "RECENT" (13px uppercase 800). Up to 4 rows, newest first, each a flex row with `border-top: 2px solid var(--color-divider)`: a fixed 84px accent-colored uppercase tag (`Detected` or the target language), the input text, the output text.

## Behavior

- Empty/whitespace input on either action → inline error "Enter some text first." No request.
- `Check language` → identify the language of the input; show the language name as the answer and a short note (script/dialect clue) plus confidence in the detail cell.
- `Translate` → translate the input into the selected target; the translation is the answer, detail reads "From {source} to {target}." plus one short note on tone/register.
- Every completed action prepends a row to Recent (cap 4).
- Network/parse failure → error message "That request didn't go through. Try again in a moment." and re-enable the buttons.
- Fully responsive: single column, nothing fixed-width except the 860px max, controls wrap on narrow screens.

## Model calls

Use whatever LLM access the app has (server route, SDK, or `window.claude.complete` if in a sandboxed artifact). Ask for JSON only and parse the first `{...}` block out of the response, falling back to the raw text if parsing fails.

Detect — system prompt:
```
Reply with JSON only: {"language": "English name of the language", "confidence": "high|medium|low", "note": "one short sentence — script, dialect, or a clue that gave it away"}
```
user: `Identify the language of this text:\n\n"""<TEXT>"""`

Translate — system prompt:
```
Reply with JSON only: {"translation": "the translation, nothing else", "source": "English name of the detected source language", "note": "one short sentence on tone, register, or a word that needed a judgement call"}
```
user: `Translate into <TARGET>:\n\n"""<TEXT>"""`

Keep the key on the server if a backend exists; never ship it in client code.

## Acceptance checklist

- [ ] Archivo loaded; no other typeface renders.
- [ ] No rounded corners, no shadows, no centered text anywhere.
- [ ] All dividers and input borders are 2px.
- [ ] Button labels flush left; primary is the red one.
- [ ] Keyboard focus shows the 2px red outline on textarea, select, both buttons.
- [ ] Empty-input error, loading state, result panel, and Recent list all behave as described.
- [ ] Works down to 360px wide without horizontal scroll.
