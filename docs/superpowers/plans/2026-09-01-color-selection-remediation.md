# Color Selection Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make time-aware wallpaper selection brightness-safe and make theme matching compare pixel prevalence against source-aware Wallust or Zed accent profiles.

**Architecture:** A single `SelectionContext` carries time and theme policy through every selection attempt. Wallpaper pixels produce versioned image distributions, while Wallust and Zed importers produce distinct source-aware theme profiles; the scorer combines hard brightness eligibility with hue-distribution and accent-coverage ranking.

**Tech Stack:** Python 3, GTK3, Pillow, NumPy, SQLite, pytest, Wallust 3.5.2 cache/config formats.

**Spec:** `docs/superpowers/plans/2026-09-01-color-selection-remediation-design.md`

## Global Constraints

- Commit and push the entire current worktree state before creating the feature branch `fix/color-selection-pipeline`.
- Preserve user-owned changes and deletions exactly in that checkpoint.
- Use test-driven development: demonstrate each new test fails for the intended reason before implementation.
- Brightness safety always wins over chromatic matching.
- If no brightness-safe wallpaper exists at night, keep the current wallpaper.
- Never infer image pixel prevalence from Wallust or Zed UI-role occurrence counts.
- Run independent review gates after each implementation task; only one worker may edit code at a time, while read-only reviewers and test analysts run in parallel.

---

## Multi-agent execution topology

At the start of each milestone, dispatch three non-blocking read-only agents in
parallel: a test-fixture analyst, a schema/API compatibility reviewer, and a
policy/adversarial-case reviewer. A single worker then owns the current code
task. After its tests pass, dispatch an independent correctness reviewer while
the orchestrator prepares the next task. Reviewer findings are resolved before
dependent tasks begin. Finish with three parallel gates: behavior, persistence,
and integration/UI-path consistency.

### Task 0: Checkpoint baseline and create durable issue notes

**Files:**
- Modify: git history only
- Verify: `PLAN.md`, current dirty paths, remote branch state

**Interfaces:**
- Consumes: user authorization to include all current changes.
- Produces: pushed baseline commit and branch `fix/color-selection-pipeline`.

- [ ] Record `git status --short`, `git diff --stat`, untracked files, and `git rev-parse HEAD`.
- [ ] Run the established core suite excluding `db_browser` and benchmarks; record exact pass/fail output without piping away pytest's status.
- [ ] Stage all current modifications, deletions, and untracked files and inspect `git diff --cached --stat` as a positive control.
- [ ] Commit the checkpoint and verify `git status --short` plus the new commit hash.
- [ ] Push the checkpoint to `origin/master` and verify the remote hash equals the local hash.
- [ ] Create and switch to `fix/color-selection-pipeline`; verify `git branch --show-current`.
- [ ] Ensure linked z-notes exist for the hub, Wallust evidence, Zed semantics, Milestone 1, Milestone 2, and all deferred issues listed in Task 8.

### Task 1: Define profile and policy interfaces

**Files:**
- Create: `variety/smart_selection/color_profiles.py`
- Modify: `variety/smart_selection/models.py`
- Test: `tests/smart_selection/test_color_profiles.py`

**Interfaces:**
- Produces: `ImageColorProfile`, `ThemeAccent`, `ThemeAccentProfile`, `ThemeSourceKind`, `SelectionContext`, and JSON round-trip helpers.

- [ ] Write failing tests for profile validation, normalized 12-bin histograms, semantic accent weights, provenance, and JSON round trips.
- [ ] Run `pytest tests/smart_selection/test_color_profiles.py -v` and confirm failures are missing-interface failures.
- [ ] Implement immutable dataclasses/enums with explicit schema versions and reject negative/non-finite weights.
- [ ] Run the test file and the existing model tests.
- [ ] Commit `feat(smart-selection): define color profile policy types`.

### Task 2: Compute and persist wallpaper pixel distributions

**Files:**
- Modify: `variety/smart_selection/palette.py`
- Modify: `variety/smart_selection/models.py`
- Modify: `variety/smart_selection/database.py`
- Test: `tests/smart_selection/test_palette.py`
- Test: `tests/smart_selection/test_database.py`

**Interfaces:**
- Consumes: `ImageColorProfile`.
- Produces: `compute_image_color_profile(path) -> ImageColorProfile` and persisted profile fields.

- [ ] Add failing solid-color, adjacent-hue, multicolor-area, grayscale, bright-patch, and migration tests.
- [ ] Prove the tests fail against the current scalar-only storage.
- [ ] Extend the existing downsampled pixel pass to calculate a chroma-weighted 12-bin OKLCH histogram plus median/P10/P90 without another full decode.
- [ ] Add the next schema migration and merge-safe SQL serialization; retain existing fields during partial upserts.
- [ ] Add background backfill through existing indexing/extraction paths, keyed by metrics version.
- [ ] Run targeted palette/database tests and migration tests.
- [ ] Commit `feat(smart-selection): persist wallpaper color distributions`.

### Task 3: Decode Wallust palettes by algorithm provenance

**Files:**
- Modify: `variety/smart_selection/wallust_config.py`
- Modify: `variety/smart_selection/palette.py`
- Modify: `variety/smart_selection/themes.py`
- Test: `tests/smart_selection/test_wallust_config.py`
- Test: `tests/smart_selection/test_palette.py`
- Add fixtures under: `tests/smart_selection/fixtures/wallust/`

**Interfaces:**
- Produces: `decode_wallust_theme(palette, config, raw_cache=None, provenance=None) -> ThemeAccentProfile`.

- [ ] Add exact Dark16 fixtures from sanitized cache structures and failing tests proving `1/9..6/14` collapse to six anchors while `0/7/8/15` add no hue mass.
- [ ] Add failing tests for unknown palette algorithms and absent provenance; unknown algorithms must use generic perceptual deduplication, not Dark16 slot assumptions.
- [ ] Implement a decoder registry keyed by normalized Wallust palette family.
- [ ] Implement Dark16 provenance mapping, raw-representative preference, background/foreground metadata, and optional originating image profile linkage.
- [ ] Preserve dominance order only as metadata; do not synthesize population counts.
- [ ] Run Wallust, palette, and theme tests.
- [ ] Commit `feat(theming): decode Wallust palette provenance`.

### Task 4: Import Zed themes as semantic accent profiles

**Files:**
- Modify: `variety/smart_selection/themes.py`
- Test: `tests/smart_selection/test_themes.py`
- Add fixtures under: `tests/smart_selection/fixtures/zed/`

**Interfaces:**
- Produces: `decode_zed_theme(theme_json) -> ThemeAccentProfile`.

- [ ] Add failing fixtures for explicit UI/syntax roles, ANSI-only themes, achromatic surfaces, repeated normal/bright colors, and the current padded-role fallback.
- [ ] Assert background/foreground never vote as hues, near-identical accents are deduplicated, and fallback import never pads to sixteen entries.
- [ ] Implement role classification for accent/focus, destructive, success, warning, syntax-secondary, and terminal fallback.
- [ ] Prefer explicit roles; use ANSI chromatic colors only when role data is unavailable.
- [ ] Run all theme import and parsing-safety tests.
- [ ] Commit `feat(theming): build semantic Zed accent profiles`.

### Task 5: Implement distribution and accent-coverage scoring

**Files:**
- Modify: `variety/smart_selection/palette.py`
- Create: `variety/smart_selection/color_scoring.py`
- Modify: `variety/smart_selection/selection/constraints.py`
- Test: `tests/smart_selection/test_color_scoring.py`
- Test: `tests/smart_selection/selection/test_constraint_applier.py`

**Interfaces:**
- Produces: `image_distribution_similarity(candidate, target) -> float`, `theme_accent_coverage(candidate, theme) -> float`, and `color_compatibility(candidate, context) -> float`.

- [ ] Add failing deterministic tests requiring blue > cyan > purple for a blue target when non-hue metrics are equal, and all three > warm candidates.
- [ ] Add tests proving a duplicated Dark16 pair cannot double its score and a neutral theme remains hue-agnostic.
- [ ] Implement circular adjacent-bin transport/distance and asymmetric accent coverage; document coefficient values with fixture calibration results.
- [ ] Remove automatic modern-record dispatch that ignores `use_oklab=False`; route all production callers through the new explicit scorer.
- [ ] Run scorer, constraint, and adaptive color E2E tests.
- [ ] Commit `fix(smart-selection): score hue distributions and theme accents`.

### Task 6: Unify time policy and enforce hard brightness safety

**Files:**
- Modify: `variety/VarietyWindow.py`
- Modify: `variety/smart_selection/selector.py`
- Modify: `variety/smart_selection/selection/engine.py`
- Modify: `variety/smart_selection/selection/constraints.py`
- Modify: `variety/smart_selection/time_adaptation.py`
- Test: `tests/smart_selection/test_selector.py`
- Test: `tests/smart_selection/selection/test_selection_engine.py`
- Test: `tests/smart_selection/e2e/test_color_mode_e2e.py`

**Interfaces:**
- Produces: `SmartSelector.update_config(config)` and one `SelectionContext` per attempt.

- [ ] Add failing tests that saved fixed/custom time settings reach `TimeAdapter`, reload replaces every consumer's config, and no hardcoded alternate bucket policy remains.
- [ ] Add failing night tests for median and P90 ceilings, missing metrics, chromatic relaxation, and empty safe pools retaining the current wallpaper.
- [ ] Make `TimeAdapter` the sole period/target authority and build `SelectionContext` from its output.
- [ ] Enforce night median <= target + 0.15 and P90 <= target + 0.40 before scoring.
- [ ] Implement two selection stages: brightness plus chromatic threshold, then the same brightness filter with soft chromatic ranking. Return an explicit no-candidate result after both fail.
- [ ] Update the controller to keep the current wallpaper on explicit no-candidate.
- [ ] Run all time, selector, selection-engine, and color-mode E2E tests.
- [ ] Commit `fix(smart-selection): enforce unified time and brightness policy`.

### Task 7: Milestone 1 integration gate

**Files:**
- Test only

**Interfaces:**
- Consumes: Tasks 1-6.
- Produces: Milestone 1 verification record.

- [ ] Run the core suite excluding `db_browser` and benchmarks and capture the unpiped exit status.
- [ ] Run focused adversarial fixtures for stark-white night images, missing metrics, red-theme/blue-wallpaper mismatch, six-pair Dark16 duplication, and imported Zed contrast colors.
- [ ] Dispatch independent behavior, algorithm/provenance, and persistence reviewers in parallel.
- [ ] Resolve all high-severity findings through a single code-owning worker and rerun affected tests.
- [ ] Commit `test(smart-selection): complete milestone one verification` if gate fixes or fixtures changed.

### Task 8: Milestone 2 alternate-path and UI consistency

**Files:**
- Modify: `variety/VarietyWindow.py`
- Modify: `variety/ThemeBrowserPage.py`
- Modify: `variety/smart_selection/database.py`
- Modify: relevant selection and E2E tests

**Interfaces:**
- Consumes: production `SelectionContext` and scorer from Milestone 1.
- Produces: consistent policy across alternate selection and preview paths.

- [ ] Route album selection, unseen-download selection, and direct-next paths through hard brightness eligibility.
- [ ] Revalidate prepared-queue candidates when period, configuration revision, or active theme profile changes.
- [ ] Replace Theme Browser's legacy stripped-record scoring with the production scorer and context.
- [ ] Backfill incomplete profiles without overwriting existing non-null metrics.
- [ ] Update the stale schema-version assertion to the actual migrated version.
- [ ] Add integration tests for every alternate path and UI/runtime score agreement.
- [ ] Run the core suite and independent behavior, persistence, and UI-consistency review gates.
- [ ] Commit `fix(smart-selection): align alternate paths and theme preview`.

### Task 9: Build and pass the independent calibration oracle

**Files:**
- Create: `tests/smart_selection/oracle/manifest.json`
- Create: `tests/smart_selection/oracle/generate_synthetic.py`
- Create: `tests/smart_selection/oracle/build_report.py`
- Create: `tests/smart_selection/oracle/report_template.html`
- Create: `tests/smart_selection/test_color_oracle.py`
- Create: `tests/smart_selection/fixtures/calibration/README.md`
- Create: `misc/color-selection-calibration/` outputs (git-ignored durable review artifacts)

**Interfaces:**
- Consumes: production extractor/scorer and curated wallpaper/theme fixtures.
- Produces: independent exact fixtures, blind consensus labels, a held-out
  ranking gate, and a browser-rendered visual report.

- [ ] Write the manifest schema first, including stable IDs, source hashes,
  expected exact measurements or pairwise winner, reviewer IDs, consensus,
  ambiguity, tuning/holdout split, Wallust version, and scorer version.
- [ ] Generate solid, proportional split, hue-boundary, grayscale, and
  dark-with-bright-region images. Calculate expected areas and luminance
  percentiles directly from construction parameters, without importing
  production extraction or scoring modules.
- [ ] Add failing tests comparing production extraction with those independent
  answers and proving the metamorphic properties in the design spec.
- [ ] Commit sanitized Wallust input/raw-cache/final-palette bundles and compare
  decoder output with source-derived expected provenance. Mark the optional
  installed-Wallust differential test with `pytest.mark.wallust`.
- [ ] Select a stratified real corpus covering warm/cool hue families,
  monochrome images, multicolor images, dark scenes, bright skies, Wallust
  themes with provenance, and generic Zed themes.
- [ ] Build randomized pairwise review pages that show theme surfaces and
  accents beside two equal-size wallpaper crops while hiding filenames,
  production scores, and previous votes.
- [ ] Have three independent visual-review agents inspect screenshots at
  original visual detail and record expectations before any agent sees scorer
  results. Admit only 2-of-3 consensus, non-ambiguous labels to the golden set.
- [ ] Freeze a deterministic tuning/holdout split by stable manifest ID. Tune
  coefficients only on the tuning partition.
- [ ] Generate an HTML report containing expected versus actual ranking,
  selected/rejected/boundary examples, luminance diagnostics, and disagreement
  cases. Serve it locally and use Playwright screenshots plus DOM checks to
  prove every manifest entry rendered; do not use accessibility snapshots as
  visual evidence.
- [ ] Require 100% hard-safety and metamorphic checks and >=90% held-out
  pairwise agreement. Any failed safety case blocks release; ranking failures
  require scorer correction or an explicit, independently reviewed label
  correction recorded in the z-note hub.
- [ ] Save screenshots, report, votes, corpus hash, command output, and
  reviewer synthesis under `misc/color-selection-calibration/`; link the
  resulting evidence note from the plan hub.
- [ ] Commit `test(smart-selection): add visual calibration oracle`.

### Task 10: Final verification and handoff

**Files:**
- Modify: plan checkboxes and z-note hub status only

**Interfaces:**
- Produces: reviewed branch ready for integration.

- [ ] Run `git diff --check` and the full core suite with an unpiped status.
- [ ] Compare failures outside the core suite with the recorded baseline; do not attribute missing Playwright, benchmark plugin, or db-browser dependency failures to this sprint without evidence.
- [ ] Run three final reviewers in parallel: requirements traceability,
  oracle/test-quality and adversarial coverage, and code/data migration safety.
- [ ] Resolve actionable findings and rerun affected gates.
- [ ] Update the implementation hub and linked z-notes with commits, test evidence, residual risks, and exact deferred work.
- [ ] Push `fix/color-selection-pipeline` and verify the remote hash equals local HEAD.
