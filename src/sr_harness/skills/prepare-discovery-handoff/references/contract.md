# Version 1 handoff schema

Store discovery_contract.json at workspace root, separate from the strict context.data/manifest.json. All names below refer to actual arrays, not display names or nested variable descriptions. Example names are illustrative; adapt them to the user's task.

```json
{
  "version": 1,
  "task_type": "regression",
  "target": "response",
  "features": ["observable"],
  "roles": {
    "response": "target", "observable": "predictor",
    "object_id": "group", "source_row": "identifier",
    "response_error": "uncertainty", "partition": "split"
  },
  "group": "object_id",
  "source_id": "source_row",
  "uncertainty": "response_error",
  "split": "partition",
  "objective": "weighted_squared_error",
  "selection": {"rules": [], "counts": {}, "response_dependent": []}
}
```

Every listed array must be one-dimensional and aligned with the target. partition must contain both literal strings train and validation and no external rows. Groups must not cross those partitions. Keep auxiliaries in context.data on disk even if the UI selects only target and predictors. The built-in observational evaluator loads these arrays directly. UI feature selection is not an evaluation policy. References to missing arrays fail validation.

Allowed roles: target, predictor, coordinate, identifier, group, uncertainty, split, diagnostic, definition_component. Only predictor and coordinate roles explicitly included in features are formula-eligible. Bookkeeping axes must have identifier role. Record derived-variable provenance in additional fields and mark components that would reconstruct the target as definition_component. The checker cannot infer a physical definition from arbitrary column names.

For task_type binned_distribution or unbinned_distribution also declare measure (e.g. which variable and whether density is per unit variable or per logarithmic unit), support (bounds and selection/completeness justification), and objective poisson_deviance or negative_log_likelihood. Preserve bin edges/counts/exposure or raw observations as auxiliaries. Select the observational evaluator using the existing evaluator dropdown, confirm target/features in variable roles, and use the declared objective as the ranking metric to minimize; preparation and reload leave the existing evaluator unchanged. Covariance arrays may be stored as two-axis arrays in the manifest and referenced with covariance; independent external data remain separate.

The contract validator is an audit tool, not a security boundary. Merely saving this file does not change generic agents, statistics, formula tools or session settings. Explicitly select the observational evaluator and tools: they validate frozen rows, expression roles and scientific readiness. The optional frontend workflow checks the requested ranking metric before starting. Generic SRAgent startup has no contract-specific gate or hidden message injection. These checks do not certify physical sample selection or a completed scientific replication.

For an unbinned distribution the target array is the measured variate, and f(target) denotes a density, not a prediction of the target value. features may be empty. The formula eligibility gate allows this self-coordinate only for an explicitly declared unbinned_distribution; the built-in observational evaluator and matching ranking are required. The default regression evaluator cannot interpret this expression. Use evaluate_observational_formula for candidate density expressions after explicitly selecting the observational evaluator, and submit_observational_formula for submission. Ordinary evaluate_formula retains its regression semantics.

## Built-in objective fields

- Regression: objective mse, weighted_squared_error, or gaussian_nll. Weighted objectives require uncertainty (positive 1-D standard errors) or covariance (positive-definite full matrix). A fixed nonnegative extra_scatter adds variance; it is not inferred from validation. uncertainty_lower and uncertainty_upper support asymmetric weighted residuals; asymmetric Gaussian NLL is not implemented.
- Unbinned: objective negative_log_likelihood, features [], support {"lower": L, "upper": U} with finite L<U. The expression is normalized in the declared target measure. All observations must lie inside the documented support. Nonconstant selection_probability is explicitly unsupported; without a calibrated selection model interpret only the selected observed sample, not the intrinsic population.
- Binned: objective poisson_deviance; density_coordinate names a declared feature, bin_lower, bin_upper and exposure name aligned arrays. Target contains integer counts. The candidate is a nonnegative density integrated over each bin and multiplied by exposure, not a prediction at the bin center.

Censoring, fitted intrinsic scatter, errors in predictor coordinates and arbitrary survey selection functions are not implemented. Do not claim these were handled merely because a contract validated. Expose required extensions as limitations.

The data-preparation tool calibrate_observation_scatter(apply=false) previews a training-only extra variance estimate and effective weight sample size. apply=true freezes extra_scatter and extra_scatter_calibration provenance. Its fixed affine baseline does not prescribe the discovery formula; misspecification can inflate the estimate. Use only when the task permits this noise-model assumption, before any candidate comparison.

Affine-in-parameter regression candidates use a weighted, column-scaled SVD solver; nonlinear candidates retain the bounded local optimizer. Formula results expose fit_diagnostics, including convergence, budget and evaluations. A finite returned formula with budget_exhausted=true is only the best evaluated candidate, not a converged fit.

## Scientific readiness and density coordinates

The optional replication_status defaults to ready. If the requested inference lacks required measurements, use insufficient_measurements and list concrete missing inputs in blocked_reason. A valid blocked contract is a completed data audit: report its reasons in the preparation handoff, and the observational evaluator refuses that task. Ordinary data loading and generic sessions remain unchanged. After correcting measurements, validate the updated contract again and ask the user to confirm the updated handoff and existing task settings. Changing the scientific target to an auxiliary task requires a distinct, documented scope; removing a status to bypass the gate is not a correction.

The unbinned evaluator integrates with respect to the numerical target coordinate dx. The measure field documents this convention; it does not automatically change variables. A transformed density must include the correct Jacobian when returned to that coordinate. quadrature_scale can be linear (default) or log (strictly positive support). Log nodes include an x Jacobian inside the integration weights, so the evaluated density remains per dx, not per dlog(x). Both 128- and 256-node integrals must agree; narrow or nonsmooth candidates may be rejected rather than silently misnormalized.

The dedicated observational_statistics tool reads frozen training rows and declares that partition. Ordinary statistics_analysis always summarizes its supplied live context, even when this file exists; it must not be described as training-only unless its caller supplied a training view. Validation remains for model comparison; external observations are never part of diagnostic context. A statistics tool does not enforce which constants an agent later hard-codes: numerical hyperparameter selection using validation must still be disclosed.
