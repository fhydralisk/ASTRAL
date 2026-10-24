---
name: validate-observational-discovery
description: Use when preparing astronomical observations for symbolic regression, discovering empirical relations in noisy parameter tables, or assessing whether a fitted formula is a reproducible physical discovery. Covers measurement provenance, independent validation, compact baselines and observational failure checks without prescribing a target law.
---

# Validate observational discovery

Keep literature answers and external test labels outside the discovery workspace. Do not use a paper title to choose a target expression. This workflow establishes evidence; it does not supply a theoretical formula. When the optional observational evaluator/tools are chosen, use prepare-discovery-handoff for their explicit configuration and editable User Prompt. Saving its metadata file alone does not activate constraints in the generic agents or tools.

## Establish a trustworthy measurement

1. Inventory files and metadata before loading arrays. Record units, physical axis meanings, calibration state, masks, time reference and object/instrument identifiers. Distinguish calibrated observations from raw voltages and published model-derived parameters.
2. Inspect one small slice and verify its axes against the header. Reshape can change grouping but cannot substitute for a permutation of physical axes. Preserve a testable mapping from a native array index to a canonical coordinate. Do not infer axis order from equal dimension lengths.
3. Apply documented scale/offset and weight semantics exactly once. Reject unsupported formats rather than guessing. Estimate backgrounds and noise from independently selected off-signal regions; keep uncertainty, masking and detection rules with the measurements.
4. Save a small executable processing stage and a pilot parameter table first. Check finite coverage, units, signal-to-noise, uncertainty and sensitivity to masks/window choices before expanding to the full dataset. Process files/chunks sequentially to bound memory.
5. For transient measurements, compare detection S/N with integrated S/N; a large mismatch requires checking the baseline, noise weights, masks and pulse window. Preserve diagnostic plots and failed processing versions.
6. Preserve object, observation and instrument groups as metadata. Multiple channels or bursts from the same source are not independent objects. Never declare an empirical discovery from algebraic definitions, shared denominators, instrumental coordinates, or a parameter already fitted under the proposed law.

Use short tool calls. `workspace_shell` is not a general Unix shell; use Python pathlib/glob instead of pipelines. Write scripts in small stages. After editing context.data, call validate_context_data and repair every error. A readable table is not proof of a scientifically valid reduction.

## Discover and compare

- Freeze a split by independent object/observation before tuning. Fit coefficients, preprocessing, clipping thresholds and feature selection using training data only. Repeated use of validation is model selection, not an untouched test. Tiny samples may support description only.
- Start with constant and additive linear baselines. Audit exact/near identities between predictors, correlations, dynamic ranges and matrix conditioning before adding terms. Remove redundant coordinates or state why they are retained.
- Use a small, data-motivated set of transformations and report alternatives. Do not force a log, power law, exponential or high-degree polynomial simply because the subject suggests it. Positive-domain transforms require coverage checks; dimensional logarithms require an explicit reference unit.
- Compare out-of-sample error alongside expression size, coefficient stability and residual structure. Bootstrap or cross-validate at the independent sampling unit where feasible. Prefer a simpler candidate when error differences are within sampling uncertainty. Narrow input ranges can make distinct forms observationally indistinguishable.
- Preserve full floating-point coefficients in executable outputs and re-evaluate the serialized expression. Center/scale ill-conditioned designs and retain the transformation, rather than cancelling huge rounded coefficients.
- Stop when complexity grows without robust predictive improvement. Noise does not imply missing terms. A good fit is neither uniqueness nor causality.

## Deliver a falsifiable result

Save processing code, a table with units and provenance, the split/selection policy, machine-readable candidate expressions, constant/linear comparison, uncertainty and failure checks. Freeze the chosen expression before external testing. Clearly separate successful data reduction, predictive fit, structural recovery, and physical interpretation. If a required observable is absent or calibration ambiguous, state the missing evidence instead of inventing a result.

## PSRFITS metadata helper

For PSRFITS, read `scripts/inspect_psrfits.py` with read_skill. Copy its `inspect` function into a short workspace_code_executor stage and save the returned records before extracting samples. The helper reads headers only; it never chooses a scientific target or silently converts polarizations. Check POL_TYPE for every file, not just the first: IQUV and AABBCRCI require different handling. A conversion also depends on receptor basis and convention metadata. Stop or flag ambiguity if those are unverified.

Format references: [SKAO PSRFITS definition](https://developer.skao.int/projects/ska-pst/en/main/data_products/data_formats/psrfits_files.html) and [PSRCHIVE polarization conventions](https://arxiv.org/abs/0912.1662). These specify storage and conventions, not an empirical discovery law.
