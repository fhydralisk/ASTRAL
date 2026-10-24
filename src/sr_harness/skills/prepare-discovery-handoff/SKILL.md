---
name: prepare-discovery-handoff
description: Use when handing observational tables or distributions between data preparation, evaluator construction and symbolic regression. Defines executable variable roles and splits, distinguishes metadata from predictors, and prevents switching scientific objectives merely to obtain a good fit.
---

# Scientific data and search handoff

Read references/contract.md to write or consume discovery_contract.json. The user's research question determines population, measurement target, transfer domain and completeness requirements. Do not infer these from a paper's expected formula. The contract describes a scientific task, never a preferred expression.

## Data preparation owns measurement and representation

Save short repeatable processing stages, inspect a pilot and expand only after measurement checks. Preserve source IDs, uncertainties and observation groups on disk. Keep metadata out of predictor roles. Store external test observations separately from development context.data. Do not compare candidate expressions on them.

Choose representation before target selection: a conditional mean is not a population distribution. For a distribution, retain observations and selection information, or counts with edges, widths and exposure. Never substitute mean mass for an unidentifiable mass-function parameter, or regress derived energy on the columns that define it. Failed parameter estimation (e.g. fits at every optimizer bound) is a failed measurement, not permission to rename the target.

Before treating a published summary as a measured response, verify its generating population, bin widths, normalization and upstream corrections. Filtering rows of a precomputed population summary does not recompute it for the new population. Preserve an explicit provenance limitation when these definitions cannot be recovered.

Record scientific selection rules, input/output counts and cuts on target or target uncertainty. Selection based on chemistry/kinematics is a domain decision requiring justification and sensitivity checks, not a generic instruction to isolate the tightest relation. High correlation means poor conditioning, not exact algebraic dependence.

Do not equate a histogram turnover with a demonstrated detection-completeness threshold: an intrinsic distribution can also turn over. Record any threshold inferred from training data as an assumption, evaluate plausible alternatives, and seek injection/recovery or instrument selection evidence when available. Freeze support before inspecting validation or external distributions. Parenthesized errors and rounding resolution are different; parse the documented convention and keep uncertainty separate from numerical precision.

When independent symmetric response errors describe only formal measurement precision and the task permits extra scatter, preview calibrate_observation_scatter after writing the contract. It fits a generic affine baseline on all allowed training inputs, reports weight concentration and a nuisance residual scale. This scale includes baseline misspecification: it is not a physical intrinsic-scatter measurement. If this observation-model assumption is justified, apply it before SR so every candidate uses the same frozen variance. Do not calibrate on validation or after looking at candidate rankings.

Missing required measurements are a valid preparation outcome. Save available data and set replication_status to insufficient_measurements with concrete blocked_reason entries. A structurally valid blocked contract may be loaded and inspected; the observational evaluator must decline its scientific evaluation. Generic workspace operations remain available. Do not change the status merely to make the workflow proceed. An auxiliary prediction task needs its own explicitly stated scope.

Write the versioned contract and run validate_context_data plus validate_discovery_contract. Validation checks consistency, not the scientific appropriateness of the cuts. No final formula selection at this stage. Return a concise handoff summary naming the measured target, allowed predictors, fixed split, objective, unresolved limitations and next action; do not include a preferred expression. For distributions, include the integration measure and fixed support. Also provide a short, copyable SR User Prompt containing those declarations and the remaining scientific question, without prescribing a formula. Ask the user to confirm target/features in the existing variable-role controls and set the declared objective as the ranking metric (minimize). A missing handoff is a request for clarification, not permission to guess a target or split.

## Built-in evaluator owns executable experimental design

Preparing or reloading data does not change the active evaluator or the generic agents. Select ObservationalEvaluator in the existing evaluator dropdown and enable evaluate_observational_formula, submit_observational_formula and observational_statistics in the existing search settings; disable forced generic initial diagnostics. Scientific examples preset these capabilities, but the user must still confirm the actual target/features and ranking metric after preparation, then paste or edit the handoff in the ordinary SR User Prompt and use the ordinary send button. No evaluator-construction agent or separate review/start workflow is required. The contract is configuration for this optional extension, not a global workspace policy. Read references/contract.md for supported objectives and fields. Auxiliary arrays remain on disk, separate from predictors. Frozen train/validation rows and group disjointness are checked; parameter fitting uses training rows only.

Supported tasks are regression (MSE, weighted squared error, Gaussian NLL), finite-support unbinned density (normalized NLL), and integrated binned counts (Poisson deviance). Selection, measurement and population decisions still belong to data preparation and the user's scientific question. Missing instrument completeness is not supplied by a normalized observed-sample likelihood. Nonconstant selection models and censoring require a separately reviewed extension; do not silently replace them with MSE or assume completeness.

Only for an explicitly requested unsupported extension, read references/evaluator-api.md and scripts/observational_losses.py. Test exact split membership, weighting, normalization and train-only fitting on tiny manual examples. Never reward a paper's expected expression. Report unsupported requirements instead of manufacturing a successful handoff.

## SR agent owns candidate search and uncertainty of conclusions

Read the handoff supplied in the editable User Prompt; the generic SR agent does not append hidden contract messages. Check target, permitted variables and explicitly selected evaluator against that handoff before expensive search. Use evaluate_observational_formula for candidate trials, submit_observational_formula for the final candidate, and observational_statistics for training-only summaries. The formula tools require an explicitly selected ObservationalEvaluator; ordinary evaluate_formula and statistics_analysis retain their original regression/live-data behavior. Identifiers, uncertainty, split labels and target-definition components are not eligible predictors. A physical coordinate may be a predictor when explicitly declared, even if stored as an array axis. Formula eligibility uses declared roles, not guesses based on names.

Compare constant and simple baselines, then a bounded set of data-motivated alternatives. Diagnose residuals and conditioning; do not use complex expressions to explain faulty extraction. Keep error differences in context of sampling uncertainty. Freeze expression, full precision coefficients and all analysis choices before requesting external assessment. Report predictive accuracy, distinguishability of functional forms and physical interpretation separately. Do not change the objective or use external results to select the winner.

## Reusable numerical helpers

Read scripts/observational_losses.py when constructing a weighted, count or unbinned evaluator. It supplies checked weighted residuals, Poisson deviance and selection-normalized density likelihood without a scientific function family. Copy only the needed functions into the workspace evaluator, test them on a tiny manual calculation, and use the same objective for train fitting and validation ranking. The helpers do not choose completeness, bins or a population. Unweighted MSE may remain a diagnostic, but must not silently remain the ranking objective for a declared distribution task.
