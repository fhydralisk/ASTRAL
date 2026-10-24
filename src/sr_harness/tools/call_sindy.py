# Copyright (c) 2026-present, Yumeow. Licensed under the MIT License.
"""Sparse symbolic-regression tool backed by PySINDy."""
import re
import logging
import numpy as np
import sr_harness_engine as engine
from typing import Dict, Any, List
from .base_tool import BaseTool, ToolMetadata, is_numeric_array

_logger = logging.getLogger(f'sr_harness.{__name__}')


@BaseTool.register('call_sindy')
class SINDyTool(BaseTool):
    """Sparse regression symbolic-discovery tool powered by PySINDy (STLSQ)."""
    metadata = ToolMetadata(name="call_sindy")

    def execute(
        self,
        x: List[str] = None,
        y: str = None,
        poly_degree: int = 3,
        include_trig: bool = False,
        threshold: float = 0.1,
        max_samples: int = 5000,
        show_diagnostics: bool = True,
    ) -> Dict[str, Any]:
        """Run SINDy sparse regression (STLSQ) over polynomial and optional trigonometric bases.

        Constructs a library of polynomial/interaction terms (up to ``poly_degree``) and optional
        Fourier terms (``sin``, ``cos``), then prunes small coefficients using Sequentially
        Thresholded Least Squares. Fast and well-suited for additive polynomial, interaction, and
        harmonic laws. Returns a submission-eligible candidate when ``y`` is the default target
        variable and ``x`` does not depend on ``y``.

        Args:
            x: Input variable names or expressions, e.g., ``["x1", "x2"]``. Defaults to all numeric non-target variables.
            y: Target variable name or expression, e.g., ``"y"`` or ``"y - x1"``. Defaults to the discovery target.
            poly_degree: Maximum polynomial degree in the candidate library (1-5, default 3).
            include_trig: Whether to append ``sin``/``cos`` Fourier terms to the feature library.
            threshold: STLSQ coefficient cutoff (0.01-1.0, default 0.1). Larger values yield sparser formulas.
            max_samples: Maximum number of rows subsampled for fitting (default 5000).
            show_diagnostics: Whether to include residual diagnostics in the evaluation output.

        Returns:
            Dict[str, Any]: Fitted formula evaluation, SINDy configuration, and any warnings.
        """
        data = self.context.train_split.data
        y = y if y is not None else self.context.target
        if y is None:
            raise ValueError("y is required when context.target is not configured")
        y = y.strip().strip('"').strip("'")
        x = x or [var for var in data if var != y and is_numeric_array(data[var])]
        exceptions = []

        poly_degree = max(1, min(poly_degree, 5))
        threshold = max(0.01, min(threshold, 1.0))

        try:
            eq_y = self.parse_formula(y)
            data_y = eq_y.eval(data).flatten()
            if not is_numeric_array(data_y):
                raise ValueError(f"Target '{y}' did not produce numeric values.")
        except Exception as e:
            raise ValueError(
                f"Failed to compute target '{y}': {str(e)}" +
                "\nOther exceptions: " + "; ".join(exceptions)
            )
        y_vec = data_y

        features = {'exprs': [], 'arrays': [], 'internal_names': [], 'original_exprs': []}
        for idx, xi in enumerate(x, 1):
            try:
                eq_x = self.parse_formula(xi)
                data_x = eq_x.eval(data).flatten()
                if not is_numeric_array(data_x):
                    raise ValueError(f"Feature '{xi}' did not produce numeric values.")
                features['exprs'].append(eq_x)
                features['arrays'].append(data_x)
                features['internal_names'].append(f"x{idx}")
                features['original_exprs'].append(xi)
                assert data_x.shape == data_y.shape, f"Feature '{xi}' shape {data_x.shape} does not match target shape {data_y.shape}."
            except Exception as e:
                exceptions.append(f"Failed to compute feature '{xi}': {str(e)}")
        if len(features['exprs']) == 0:
            raise ValueError(
                "No valid input variables available for fitting.\n" +
                "Other exceptions: " + "; ".join(exceptions)
            )
        X_matrix = np.column_stack(features['arrays'])

        if len(y_vec) > max_samples:
            rng = np.random.default_rng(42)
            idx = rng.choice(len(y_vec), size=max_samples, replace=False)
            X_fit = X_matrix[idx]
            y_fit = y_vec[idx]
        else:
            X_fit = X_matrix
            y_fit = y_vec

        try:
            formula_str = self._run_sindy(
                X_fit, y_fit, features['internal_names'], poly_degree, include_trig, threshold
            )
            if not formula_str:
                raise ValueError("SINDy returned an empty formula.")
            formula_str = self._restore_feature_names(formula_str, features['internal_names'], features['original_exprs'])
            eq_f = self.parse_formula(formula_str)
            evaluation = self.evaluate(f=eq_f, y=eq_y, show_diagnostics=show_diagnostics)
        except Exception as e:
            evaluation = self.failed_evaluation()
            exceptions.append(f"SINDy fitting failed: {type(e).__name__}: {e}")

        return {
            **evaluation,
            "config": {
                "method": "SINDy",
                "poly_degree": poly_degree,
                "include_trig": include_trig,
                "threshold": threshold,
                "max_samples": max_samples,
            },
            "exceptions": exceptions,
        }

    def _run_sindy(
        self,
        X,
        y,
        x_names: List[str],
        poly_degree: int,
        include_trig: bool,
        threshold: float,
    ) -> str:
        """Run PySINDy static regression and return a cleaned formula."""
        import pysindy as ps

        feature_libs = [ps.PolynomialLibrary(degree=poly_degree, include_interaction=True)]
        if include_trig:
            feature_libs.append(ps.FourierLibrary(n_frequencies=2))

        lib = ps.ConcatLibrary(feature_libs) if len(feature_libs) > 1 else feature_libs[0]
        model = ps.SINDy(
            feature_library=lib,
            optimizer=ps.STLSQ(threshold=threshold, alpha=0.05),
        )
        # Use SINDy's fit with x_dot=y to perform static regression y = f(X)
        model.fit(X, t=1, x_dot=y.reshape(-1, 1), feature_names=x_names)

        equations = model.equations()
        if not equations:
            return "0"
        return self._clean_formula(equations[0], x_names)

    def _clean_formula(self, equation_str: str, x_names: List[str]) -> str:
        """Clean up SINDy output formula for SRHarness Engine."""
        formula = equation_str.strip()
        # Remove leading/trailing whitespace around operators
        formula = re.sub(r'\s+', ' ', formula)
        formula = re.sub(r'\+\s+-', '-', formula)

        # SINDy outputs like " 1.000 x1^2 +  3.000 x1 x2"
        # Parse terms: coefficient * feature_product
        terms = []
        # Split on + and - while keeping the sign
        parts = re.split(r'(?=[+-])', formula)
        for part in parts:
            part = part.strip()
            if not part:
                continue
            # Match coefficient and variables
            match = re.match(r'^([+-]?\s*[\d.]+)\s+(.+)$', part)
            if match:
                coef_str = match.group(1).replace(' ', '')
                coef = float(coef_str)
                var_part = match.group(2).strip()
                if abs(coef) < 1e-10:
                    continue
                # Clean variable part: "x1^2" -> "x1**2", "x1 x2" -> "x1*x2"
                var_part = var_part.replace('^', '**')
                var_part = re.sub(r'(\w)\s+(\w)', r'\1*\2', var_part)
                # Round near-integer coefficients
                if abs(coef - round(coef)) < 0.005 and abs(coef) < 1000:
                    coef = int(round(coef))
                if coef == 1:
                    terms.append(var_part)
                elif coef == -1:
                    terms.append(f"-{var_part}")
                else:
                    terms.append(f"{coef}*{var_part}")
            else:
                # Just a constant or something we can't parse
                try:
                    val = float(part)
                    if abs(val) > 1e-10:
                        terms.append(str(val))
                except ValueError:
                    if part.strip():
                        terms.append(part.strip())

        if not terms:
            return "0"
        formula = " + ".join(terms)
        formula = formula.replace("+ -", "- ")
        return formula

    def _restore_feature_names(
        self,
        formula: str,
        internal_names: List[str],
        original_expressions: List[str],
    ) -> str:
        """Replace SINDy feature names with original variables or expressions."""
        restored = formula
        replacements = dict(zip(internal_names, original_expressions))
        placeholders = {name: f"__sindy_feature_{idx}__" for idx, name in enumerate(replacements)}
        restored = self._replace_square_calls(restored)
        for name in sorted(replacements, key=len, reverse=True):
            restored = re.sub(rf"\b{re.escape(name)}\b", placeholders[name], restored)
        for name, expr in replacements.items():
            expr = expr.replace("^", "**").replace("np.", "")
            restored = restored.replace(placeholders[name], f"({expr})")
        try:
            restored = self.parse_formula(restored).to_str()
        except:
            _logger.warning(f"Failed to parse restored formula {restored!r}, returning unparsed version.")
        return restored

    @staticmethod
    def _replace_square_calls(formula: str) -> str:
        """Replace square(expr) with (expr)**2, preserving nested parentheses."""
        token = "square("
        while token in formula:
            start = formula.find(token)
            arg_start = start + len(token)
            depth = 1
            idx = arg_start
            while idx < len(formula) and depth:
                if formula[idx] == "(":
                    depth += 1
                elif formula[idx] == ")":
                    depth -= 1
                idx += 1
            if depth:
                break
            arg = formula[arg_start:idx - 1]
            formula = f"{formula[:start]}({arg})**2{formula[idx:]}"
        return formula

    @classmethod
    def format_result_dict(cls, result: Dict[str, Any]) -> str:
        """Format the SINDy evaluation result and library settings for the Agent.

        Args:
            result: Result dictionary returned by :meth:`execute`.

        Returns:
            str: Formatted SINDy fit summary.
        """
        if result["formula"] == "(None)":
            warnings = "; ".join(result.get("exceptions", [])) or "No further error detail was provided."
            return f"SINDy did not produce a valid formula. Details: {warnings}"
        config = result["config"]
        parts = [cls.format_evaluation_result(result, title="SINDy fitted formula")]
        parts.append(
            f"Search configuration: polynomial degree up to {config['poly_degree']}; "
            f"trigonometric features {'enabled' if config['include_trig'] else 'disabled'}; "
            f"coefficient sparsity threshold={config['threshold']}."
        )
        if result.get('exceptions'):
            parts.append(f"Warnings: {'; '.join(result['exceptions'])}")
        return "\n".join(parts)
