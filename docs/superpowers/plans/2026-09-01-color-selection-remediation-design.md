# Color Selection Remediation Design

**Date:** 2026-09-01
**Status:** Ratified for implementation

## Objective

Make wallpaper selection obey time-of-day brightness safety and match actual
theme chroma without treating generated terminal roles as image-frequency
samples.

## Verified facts

- Runtime configuration currently omits saved time-adaptation settings and
  does not propagate reloaded configuration into the selection engine and
  time adapter.
- Theme selection can fall back from an empty constrained result to an
  unrestricted wallpaper, including a bright wallpaper at night.
- Modern pixel records route through a scorer that ignores hue identity; red,
  orange, and yellow can therefore score alike, as can blue, cyan, and purple.
- Wallust 3.5.2 on this host uses `fastresize`, `lchmixed`, `dark16`, automatic
  threshold selection, `saturation = 80`, and contrast checking.
- LchMixed groups resized pixels by Improved CIEDE2000 distance, retains up to
  sixteen representatives ordered by dominance, and then sorts representatives
  for palette construction. Cache serialization drops the histogram counts.
- Dark16 uses only six selected representatives for chromatic ANSI slots.
  `color1/color9` through `color6/color14` are dark/bright forms of the same
  six sources. `color0`, `color7`, `color8`, and `color15` are derived UI
  background/foreground/contrast colors.
- The local Zed Wallust template uses `color4` heavily for accent/focus,
  `color1` for destructive/error roles, `color2` for success/string roles,
  `color3` for warnings/numbers, and `color5`/`color6` for other syntax roles.
  Bright slots occur primarily in the integrated terminal. Template reference
  counts measure implementation verbosity, not visible screen area.

## Domain model

The implementation keeps three concepts separate:

1. `ImageColorProfile`: measurements of a wallpaper itself. It contains a
   chroma-weighted 12-bin OKLCH hue histogram, median luminance, P10/P90
   luminance, chroma, and a metrics version. Histogram mass comes from pixels.
2. `ThemeAccentProfile`: hues supported by a UI theme. It contains deduplicated
   chromatic anchors with semantic weights, background/foreground luminance,
   source kind, and optional wallpaper provenance. It never claims its weights
   are pixel prevalence.
3. `SelectionContext`: the single runtime policy object containing the active
   time period, hard brightness bounds, optional theme profile, relaxation
   stage, and configuration revision.

## Source-aware theme decoding

### Wallust themes

Dispatch decoding by the configured Wallust palette algorithm; do not hardcode
Dark16 rules as universal rules for Light16, HardDark, or ANSI palettes.

For Dark16:

- Collapse `1/9` through `6/14` by provenance into six anchors.
- Prefer the un-darkened members `9..14`, or the raw Wallust representatives
  when available.
- Exclude `0`, `7`, `8`, and `15` from hue voting. Preserve them as appearance
  and contrast metadata.
- If the originating wallpaper is known, its `ImageColorProfile` is the
  primary color target. The six anchors are a secondary accent-compatibility
  signal.
- Without provenance, compare candidates against the six-anchor accent set.
  Equal anchor priors are the conservative fallback. Dominance order may be
  used only as an explicitly versioned rank-decay heuristic; it is not a
  recovered population distribution.

Template-derived semantic weights may rank how well a wallpaper supports the
rendered desktop, but remain separate from wallpaper prevalence. Raw reference
counts are not accepted directly because repeated KDE sections and graph
gradients inflate them. Tests will use classified semantic role families:
accent/focus, destructive, success, warning, syntax-secondary, and terminal.

### Imported Zed themes

- Extract background and foreground for appearance/contrast only.
- Prefer explicit Zed UI and syntax roles over ANSI slots.
- Deduplicate perceptually near-identical colors before weighting.
- Classify chromatic roles into the same semantic role families.
- Use ANSI `1..6`/`9..14` only as fallback accent evidence. Do not assume they
  are Wallust pairs unless Wallust provenance is present.
- Do not pad a profile to sixteen entries by duplicating roles.

## Matching policy

Brightness is a safety constraint; color is a preference:

1. Apply hard brightness eligibility first.
2. At night, require median luminance <= `target_lightness + 0.15` and P90 <=
   `target_lightness + 0.40`, clamped to 1.0. Missing required brightness
   metrics make a candidate ineligible until backfilled.
3. Rank eligible candidates using pixel-distribution similarity plus theme
   accent coverage. Use a circular transport/distance measure across adjacent
   hue bins so nearby hues match without collapsing all warm or cool hues.
4. First attempt brightness plus chromatic threshold. If empty, relax only the
   chromatic threshold and retain color as a soft ranking signal.
5. If no brightness-safe candidate exists, keep the current wallpaper. Never
   perform an unrestricted random fallback.

## Persistence and backfill

- Add versioned image histogram/profile fields and versioned theme-profile
  serialization.
- Piggyback image-profile backfill on existing indexing and Wallust extraction.
- Preserve existing non-null pixel metrics during partial palette upserts.
- Store source kind and provenance explicitly so a generic Zed import cannot be
  decoded using Wallust-specific rules.

## Milestones

Milestone 1 delivers runtime configuration correctness, hard brightness safety,
source-aware profiles, histogram matching, safe relaxation, and core tests.

Milestone 2 routes albums/download/direct-next paths through the same policy,
revalidates prepared queues at transitions, aligns Theme Browser scoring,
hardens merge-safe backfill, and repairs stale schema tests.

## Acceptance criteria

- A night selection cannot return a candidate exceeding either hard luminance
  ceiling, including through fallback paths covered in Milestone 1.
- Empty night-safe pools retain the current wallpaper.
- A blue target ranks blue above cyan, purple, red, orange, and yellow in
  deterministic fixtures with equal non-hue metrics.
- Dark16 pair duplication, neutral roles, and saturation/contrast transforms do
  not create extra hue mass.
- Imported Zed surface/text colors do not vote as chromatic accents.
- Theme provenance selects the appropriate decoder and matching strategy.
- New schema migrations, partial upserts, backfill, and configuration reloads
  have regression tests.

## Independent oracle and pre-release calibration

Passing implementation-derived unit tests is necessary but insufficient. The
release gate therefore uses evidence that is produced independently of the
scoring implementation:

1. Procedurally generated images provide exact pixel-area and luminance
   answers. Expected histograms and percentiles are calculated from the image
   construction manifest, not by calling production extraction code.
2. Wallust differential fixtures contain an input image, the exact Wallust
   version/configuration, raw cache, rendered palette, and expected slot
   provenance derived from Wallust source. Optional live-Wallust tests detect
   upstream format or behavior drift.
3. Metamorphic tests specify relationships rather than implementation numbers:
   duplication invariance, achromatic neutrality, hue-rotation equivariance,
   adjacent-bin continuity, matching-area monotonicity, and hard-brightness
   monotonicity.
4. A curated real-wallpaper/theme corpus is judged blind. Three independent
   visual reviewers see theme swatches plus randomized wallpaper pairs without
   production scores or identities. Only 2-of-3 consensus comparisons enter
   the golden oracle; ambiguous pairs remain in a review set.
5. A held-out portion of the consensus corpus is never used to tune scorer
   coefficients. Release requires 100% safety/invariant compliance and at
   least 90% pairwise agreement on the held-out, unambiguous comparisons.
6. A browser-rendered calibration report shows theme surfaces/accents beside
   selected, rejected, and boundary wallpapers. Playwright captures fixed-size
   screenshots and verifies that every manifest entry rendered; screenshot
   review is performed independently of DOM/accessibility snapshots.

Golden labels are versioned with reviewer provenance, Wallust version, scorer
version, corpus hash, and whether an item was used for tuning or held out.
Changing a label requires a recorded calibration decision, not merely changing
the test to match new output.
