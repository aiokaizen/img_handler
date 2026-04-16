# Designs

Library of effect designs for `img_handler`, focused on Pinterest-style food recipe imagery (nomadmouse.com). Patterns extracted from `ideas/` reference images (Emma's Cake Studio, Stephanie's Sweets, Etsy, etc.). This file is the history / roadmap — one entry per design, updated as each ships.

## Status legend

- `planned` — design identified, not started
- `in-progress` — actively being built / iterated
- `shipped` — effect available via CLI preview and HTTP endpoint

## Shared conventions

### Output canvas sizes

All designs target Pinterest-optimized vertical aspect ratios, selectable per render:

- `pin_2x3` → 1000×1500 (standard pin)
- `pin_1x2` → 1000×2000 (tall pin)

### Color model (three-hex palette)

Every effect takes three hex colors; any omitted are auto-derived from the top image:

- **primary** — dominant recipe color (band tint, accent rules, decorative strokes)
- **secondary** — title text color
- **tertiary** — subtitle / brand / URL strip color

Auto-extraction: downscale top image to 100px, quantize to 5 clusters (median-cut), drop near-white/near-black, pick highest-frequency remaining as primary. Secondary defaults to contrast-derived text color from primary luminance. Tertiary defaults to next visually-distinct cluster, falling back to contrast-derived.

### Two-image inputs

All triptych designs take two separate images (`file_top`, `file_bottom`). Typical pairing: whole dish + sliced/served cross-section, or overhead + 3/4 angle.

### Fonts (v1)

DejaVu Serif Bold (title) + DejaVu Sans (subtitle/brand). Not final — reference pins use condensed sans (Bebas/Anton) or display serif (Playfair). Font-bundling is a later iteration once one design is visually validated.

## Design catalog

### 1. `frosted_glass_triptych` — in-progress (focus)

References: Blood Orange Cake, Blueberry Lemon Yogurt Bark, Mulberry Cake, Vintage Christmas Cake, Raffaello Cake.

**Layout:** top photo (upper half) · centered frosted-glass rounded-rect band spanning the seam · bottom photo (lower half).

**Band characteristics:**

- Width ~88% of canvas; height auto-sized to fit text, capped at ~32% of canvas height.
- Fill = gaussian blur of the underlying canvas region + semi-transparent primary-color tint overlay.
- Thin primary-color outline at low alpha.
- Large rounded corners (~12% of min band dimension).

**Text:**

- Title (large serif, centered) in `secondary`.
- Optional subtitle below in `tertiary`, separated by a thin accent rule in `primary` (Raffaello-style).
- Optional brand text bottom-right in `tertiary`.

**Params:** `file_top`, `file_bottom`, `title`, `subtitle?`, `brand?`, `primary_hex?`, `secondary_hex?`, `tertiary_hex?`, `output_size`.

### 2. `black_bar_triptych` — planned

Reference: Lemon Blackberry Cake (Stephanie's Sweets).

**Layout:** top photo · solid opaque bar · bottom photo. Differs from #1 in that the band is fully opaque (typically dark) and supports two accent lines:

- A script/brush accent line above the main title ("Blackberry Jam Filling").
- A URL strip below the main title in an inverted color band (white strip with dark text).

**Extra params:** `accent_text?`, `url_text?`, `band_fill_hex?` (override default black).

### 3. `stroked_stamp_triptych` — planned

References: Chocolate Éclair Cake, Blueberry Swirl Yogurt Bites.

**Layout:** top photo · blurred middle strip (no discrete panel) with heavily stroked all-caps text stamped directly · bottom photo.

**Characteristics:**

- No rounded box. Middle strip is a gaussian-blurred slice of the underlying canvas seam.
- Text uses thick stroke (6–10% of font size) in contrast color over white fill.
- Title only — no subtitle typically.

**Extra params:** `stroke_width_ratio?` (default 0.08 of font size).

### 4. `solid_band_triptych` — planned

Reference: Blueberry Lemon Yogurt Bark (solid-band variant — lightweight sibling of frosted).

**Layout:** top photo · solid neutral-color rounded-rect band (no blur, no tint transparency) · bottom photo. Cheapest version of the triptych for when the aesthetic calls for a clean, flat band.

**Extra params:** `band_fill_hex?` (default near-white cream).

### 5. `recipe_ingredient_card` — planned

Reference: Juicy Pineapple Heaven Cake (Etsy digital download).

**Layout:** single hero photo (top ~45%) · ornamental scalloped card filling the bottom half with title, "What You Need:" accent, and 3–5 bulleted ingredients (optional mini accent photo top-right of the card).

**Characteristics:**

- Ornamental scalloped border in `primary` with a cream fill.
- Display-serif title.
- Italic/script accent line ("What You Need:").
- Bulleted ingredient list with bold numeric quantities and regular-weight remainders ("**1 box** yellow cake mix").

**Extra params:** `ingredients` (list), `ingredients_title?` (default "What You Need:"), `accent_font_style?` ("script" | "italic").

## Delivery plan

1. Ship `frosted_glass_triptych` end-to-end (CLI preview → visual validation → API endpoint).
2. Extract shared layout / color / font utilities as patterns stabilize.
3. Ship next design (likely #2 `black_bar_triptych`) reusing utilities.
4. Repeat for #3–#5.

## Shared infrastructure

- `api_functions/effects/__init__.py` — effect registry (decorator-based), protocol, lookup helpers.
- `api_functions/effects/colors.py` — hex parsing, dominant-color extraction, three-color palette derivation.
- `api_functions/effects/layout.py` — canvas builders (`pin_2x3`, `pin_1x2`), cover-crop for panel fitting.
- `api_functions/effects/<effect_name>.py` — one file per effect, uses `@register_effect(...)` to self-register.
- `api_functions/effects_api.py` — request wrappers (validation, save, public URL) sitting between FastAPI and the pure-image effect functions.
- `scripts/preview_effects.py` — CLI that picks random pairs from `assets/` and renders all registered effects for side-by-side review.
- `assets/` — user-provided folder of paired food photos for iteration (not in git).

## API shape

One POST endpoint per effect, under `/images/effects/<effect_name>`. All endpoints accept multipart form-data, return the same response shape as `/images/upload` (stored filename + protected URL + signed public URL).

Example:

```
POST /images/effects/frosted_glass_triptych
  file_top: <image>
  file_bottom: <image>
  title: "Blood Orange Cake"
  subtitle: "Bright, zesty, simple to bake"
  brand: "nomadmouse.com"
  primary_hex: "#f4b5c2"        (optional — auto-extracted if omitted)
  secondary_hex: "#3d2d24"      (optional)
  tertiary_hex: "#7a6658"       (optional)
  output_size: "pin_2x3"        (default pin_2x3; also pin_1x2)
```

## Non-goals (for now)

- Custom font bundling.
- Multi-effect chaining.
- Video integration.
- Dominant-color-only API endpoint (can revisit if the frontend wants to preview).
