"""Built-in observational objectives driven by an explicit data contract.

No paper-specific function families or coefficients. This trusted implementation
loads auxiliary arrays itself, avoiding generated evaluator source and metadata
being promoted to predictors. Candidate expressions are evaluated by the engine.
"""
from __future__ import annotations

import argparse
from functools import lru_cache

import numpy as np
from scipy.linalg import cho_factor, cho_solve
from scipy.optimize import minimize
import sr_harness_engine as engine

from .default_evaluator import DefaultEvaluator
from . import utils
from ..core.context_data import load_context_data
from .observational_contract import (
    read_contract, audit_contract, candidate_role_errors, require_search_ready,
)


@lru_cache(maxsize=12)
def _quadrature(order):
    return np.polynomial.legendre.leggauss(order)


class ObservationalEvaluator(DefaultEvaluator):
    """Frozen grouped splits, weighted regression and normalized distribution losses."""

    def __init__(self, *, stable_affine_fit=True, max_fit_evaluations=1000):
        self.stable_affine_fit = stable_affine_fit
        self.max_fit_evaluations = max_fit_evaluations
        self.last_fit_diagnostics = None
        self._signature = None
        self._contract = None
        self._data = None

    def _load(self, context):
        if context.workspace is None:
            raise ValueError('ObservationalEvaluator requires a workspace and discovery_contract.json')
        root = context.workspace.path
        directory = root / 'context.data'
        paths = [root/'discovery_contract.json', directory/'manifest.json', *sorted(directory.glob('*.npy'))]
        signature = (str(root), tuple((str(p), p.stat().st_mtime_ns, p.stat().st_size) for p in paths))
        if signature != self._signature:
            c = read_contract(context.workspace)
            if c is None:
                raise ValueError('Create and validate discovery_contract.json first')
            require_search_ready(c)
            data = load_context_data(directory, workspace=context.workspace)['data']
            report = audit_contract(c, data)
            if not report['valid']:
                raise ValueError('; '.join(report['errors']))
            if not c.get('split'):
                raise ValueError('Declare a frozen train/validation split; no random fallback is allowed')
            objective = c.get('objective', 'mse')
            if objective not in {'mse', 'weighted_squared_error', 'gaussian_nll', 'negative_log_likelihood', 'poisson_deviance'}:
                raise ValueError(f'Unsupported observational objective: {objective}')
            if c['task_type']=='regression' and objective not in {'mse','weighted_squared_error','gaussian_nll'}:
                raise ValueError('Regression requires a regression objective')
            if c['task_type']=='unbinned_distribution' and objective!='negative_log_likelihood':
                raise ValueError('Unbinned density requires negative_log_likelihood')
            if c['task_type']=='binned_distribution' and objective!='poisson_deviance':
                raise ValueError('Binned counts require poisson_deviance')
            if c['task_type']=='unbinned_distribution':
                lo,hi=self._support(c)
                if np.any((data[c['target']] < lo) | (data[c['target']] > hi)):
                    raise ValueError('Observations outside declared support; apply and document selection first')
                if c.get('selection_probability'):
                    raise ValueError('Nonconstant selection needs an explicit observation/grid selection model; unsupported rather than assumed complete')
            self._contract, self._data, self._signature = c, data, signature
        return self._contract, self._data

    def validate_expression(self, f, y, context):
        """Validate a candidate only when this observational evaluator is selected.

        This policy belongs to the extension. Generic agents and tools do not
        inspect the contract or change their behavior because a file exists.
        """
        if not isinstance(f, engine.Expression) or not isinstance(y, engine.Expression):
            raise TypeError('f and y must be symbolic expressions')
        contract, _ = self._load(context)
        if context.target != contract['target'] or y.to_str() != contract['target']:
            raise ValueError('Evaluate the contract target, not a transformed substitute')
        variables = {node.name for node in f.iter_preorder() if isinstance(node, engine.Variable)}
        errors = candidate_role_errors(contract, variables, context.target)
        if errors:
            raise ValueError('; '.join(errors))
        missing = variables - set(context.data)
        if missing:
            raise ValueError(f'Candidate inputs missing from selected context: {sorted(missing)}')

    def _validate_partition(self, context, *, fitting=False):
        """Reject stale, relabelled or modified partition views on direct calls."""
        contract, data = self._load(context)
        label = getattr(context.args, 'observational_partition', None)
        if fitting and label != 'train':
            raise ValueError('Fit is only permitted on the frozen training partition')
        if label not in {'train', 'validation'}:
            raise ValueError('Evaluate a frozen train/validation view from ObservationalEvaluator.split')
        expected = np.flatnonzero(data[contract['split']] == label)
        indices = np.asarray(getattr(context.args, 'observational_indices', []))
        if not np.array_equal(indices, expected):
            raise ValueError('Partition indices differ from the frozen observational split')
        for name in [contract['target'], *contract['features']]:
            if name not in context.data or not np.array_equal(context.data[name], data[name][expected]):
                raise ValueError(f'Partition array differs from frozen context.data: {name}')

    @staticmethod
    def _support(c):
        support=c['support']
        if not isinstance(support,dict):
            raise ValueError('Support requires numeric lower and upper bounds')
        lo,hi=float(support['lower']),float(support['upper'])
        if not np.isfinite([lo,hi]).all() or not lo<hi:
            raise ValueError('Support must be a finite increasing interval')
        return lo,hi

    def split(self, context):
        c,data=self._load(context)
        if context.target!=c['target']:
            raise ValueError('Selected target differs from contract')
        n=len(data[c['target']])
        for name,values in context.data.items():
            if name not in data or not np.array_equal(values,data[name]):
                raise ValueError(f'Live array differs from frozen context.data: {name}')
            if np.asarray(values).shape != (n,):
                raise ValueError('Select the target and scientific predictors before evaluating; auxiliaries stay on disk')
        result={}
        for label in ('train','validation'):
            indices=np.flatnonzero(data[c['split']]==label)
            view=context.with_data({name:value[indices] for name,value in context.data.items()})
            view.args=argparse.Namespace(**vars(context.args))
            view.args.observational_indices=indices
            view.args.observational_partition=label
            result[label]=view
        return result

    @staticmethod
    def _values(f, values, parameters=None):
        with np.errstate(all='ignore'):
            prediction=np.asarray(engine.evaluate(f,values,parameters=parameters),dtype=float)
        n=len(next(iter(values.values())))
        return np.broadcast_to(prediction,(n,))

    def _density(self,f,context,parameters=None):
        c,_=self._load(context)
        target=c['target'];lo,hi=self._support(c)
        observed=self._values(f,{target:context.data[target]},parameters)
        if not np.isfinite(observed).all() or np.any(observed<=0):
            raise ValueError('Density must be finite and positive at observations')
        integrals=[]
        for order in (128,256):
            nodes,weights=_quadrature(order)
            scale=c.get('quadrature_scale','linear')
            if scale=='log':
                if lo<=0:raise ValueError('Log-spaced quadrature requires strictly positive support')
                width=np.log(hi)-np.log(lo)
                x=np.exp(np.log(lo)+(nodes+1)*width/2)
                integration_weights=weights*x*width/2
            elif scale=='linear':
                x=lo+(nodes+1)*(hi-lo)/2
                integration_weights=weights*(hi-lo)/2
            else:
                raise ValueError('quadrature_scale must be linear or log')
            values=self._values(f,{target:x},parameters)
            if not np.isfinite(values).all() or np.any(values<0):
                raise ValueError('Density must be finite and nonnegative over support')
            integrals.append(float(np.dot(integration_weights,values)))
        z=integrals[-1]
        if not np.isfinite(z) or z<=0:
            raise ValueError('Density normalization must be positive and finite')
        relative=abs(integrals[0]-z)/z
        if relative>1e-5:
            raise ValueError('Density quadrature did not converge at 128/256 nodes; use a smoother candidate or refine the protocol')
        losses=-np.log(observed)+np.log(z)
        return losses,z,relative

    def _regression_loss(self,f,context,parameters=None,*,include_diagnostics=False):
        """Return the unchanged objective, optionally with fixed-error q/n diagnostics.

        q/n uses the declared observation variances/covariance, including frozen
        extra scatter. It is not adjusted for fitted degrees of freedom and is
        neither an intrinsic-scatter estimate nor an automatic stopping rule.
        """
        c,data=self._load(context)
        indices=np.asarray(context.args.observational_indices)
        y=np.asarray(context.data[c['target']],float)
        pred=self._values(f,context.data,parameters)
        if not np.isfinite(pred).all():raise ValueError('Nonfinite prediction')
        residual=pred-y
        if c.get('objective','mse')=='mse':
            result=(float(np.mean(residual**2)),pred)
            return (*result,{}) if include_diagnostics else result
        extra=float(c.get('extra_scatter',0))
        if not np.isfinite(extra) or extra<0:raise ValueError('extra_scatter must be fixed, finite and nonnegative')
        if c.get('covariance'):
            cov=np.asarray(data[c['covariance']],float)[np.ix_(indices,indices)]
            if not np.allclose(cov,cov.T,rtol=1e-10,atol=1e-12):raise ValueError('Covariance must be symmetric')
            cov=cov+extra**2*np.eye(len(indices))
            factor=cho_factor(cov,lower=True)
            q=float(residual@cho_solve(factor,residual))
            logdet=2*np.log(np.diag(factor[0])).sum()
        else:
            if c.get('uncertainty_lower') and c.get('uncertainty_upper'):
                if c['objective']=='gaussian_nll':
                    raise ValueError('Asymmetric errors require a normalized asymmetric likelihood; use weighted_squared_error or an explicit extension')
                lower=np.asarray(data[c['uncertainty_lower']])[indices]
                upper=np.asarray(data[c['uncertainty_upper']])[indices]
                sigma=np.where(residual>=0,upper,lower)
            elif c.get('uncertainty'):
                sigma=np.asarray(data[c['uncertainty']])[indices]
            else:raise ValueError('Weighted objective requires uncertainty or covariance arrays')
            if not np.isfinite(sigma).all() or np.any(sigma<=0):raise ValueError('Errors must be finite and positive')
            variance=sigma**2+extra**2
            q=float(np.sum(residual**2/variance));logdet=float(np.log(variance).sum())
        loss=q/len(y)
        if c['objective']=='gaussian_nll':loss=.5*(q+logdet+len(y)*np.log(2*np.pi))/len(y)
        if include_diagnostics:
            return loss,pred,{'mean_standardized_squared_residual':q/len(y)}
        return loss,pred

    def _counts(self,f,context,parameters=None):
        c,data=self._load(context);indices=np.asarray(context.args.observational_indices)
        coordinate=c.get('density_coordinate')
        if coordinate not in c['features']:raise ValueError('Binned density_coordinate must be a declared feature')
        lo=np.asarray(data[c['bin_lower']],float)[indices];hi=np.asarray(data[c['bin_upper']],float)[indices]
        exposure=np.asarray(data[c['exposure']],float)[indices]
        if not np.isfinite([lo,hi,exposure]).all() or np.any(hi<=lo) or np.any(exposure<=0):raise ValueError('Invalid bin edges/exposures')
        expected=[]
        for order in (24,48):
            nodes,weights=_quadrature(order)
            x=lo[:,None]+(nodes+1)*(hi-lo)[:,None]/2
            values={name:np.repeat(value,order) for name,value in context.data.items()}
            values[coordinate]=x.ravel()
            pred=self._values(f,values,parameters).reshape(x.shape)
            if not np.isfinite(pred).all() or np.any(pred<0):raise ValueError('Count density must be finite and nonnegative')
            expected.append(exposure*(hi-lo)/2*(pred@weights))
        mu=expected[-1]
        if not np.allclose(expected[0],mu,rtol=1e-5,atol=1e-10):raise ValueError('Bin integration did not converge')
        y=np.asarray(context.data[c['target']],float)
        if np.any(y<0) or np.any(y!=np.floor(y)):raise ValueError('Poisson objective requires nonnegative integer counts')
        if np.any((y>0)&(mu<=0)):raise ValueError('Positive counts require positive expected counts')
        terms=mu-y;positive=y>0
        terms[positive]+=y[positive]*np.log(y[positive]/mu[positive])
        return float(2*np.mean(terms)),mu

    def _loss(self,f,context,parameters=None):
        c,_=self._load(context)
        if c['task_type']=='unbinned_distribution':return float(np.mean(self._density(f,context,parameters)[0]))
        if c['task_type']=='binned_distribution':return self._counts(f,context,parameters)[0]
        return self._regression_loss(f,context,parameters)[0]

    def fit(self,f,y,context):
        self.last_fit_diagnostics = None
        self.validate_expression(f, y, context)
        self._validate_partition(context, fitting=True)
        missing=engine.unbound_parameters(f)
        if missing:
            raise ValueError(f"Parameters need explicit finite initial values: {missing}; use param('a', value=0.0) (quoted name and value keyword)")
        initial=engine.parameter_values(f)
        if any(v is None for v in initial.values()):raise ValueError('Parameters need finite initial values')
        if not initial:return f
        names=list(initial);x0=np.asarray([initial[n] for n in names],float)
        if not np.isfinite(x0).all() or len(x0)>24:raise ValueError('Use at most 24 finite scalar parameters')
        from .parameter_fitting import fit_expression_least_squares, is_affine_in_parameters
        c, data = self._load(context)
        self.last_fit_diagnostics = None
        symmetric = not c.get('uncertainty_lower') and not c.get('uncertainty_upper')
        if self.stable_affine_fit and c['task_type']=='regression' and symmetric and is_affine_in_parameters(f):
            indices = np.asarray(context.args.observational_indices)
            sigma = whitener = None
            if c.get('objective','mse') != 'mse':
                extra = float(c.get('extra_scatter', 0))
                if not np.isfinite(extra) or extra < 0:
                    raise ValueError('extra_scatter must be fixed, finite and nonnegative')
                if c.get('covariance'):
                    cov = np.asarray(data[c['covariance']],float)[np.ix_(indices,indices)]
                    if not np.allclose(cov, cov.T):
                        raise ValueError('Covariance must be symmetric')
                    cov = cov + extra**2 * np.eye(len(indices))
                    whitener = np.linalg.solve(np.linalg.cholesky(cov), np.eye(len(indices)))
                elif c.get('uncertainty'):
                    sigma = np.sqrt(np.asarray(data[c['uncertainty']],float)[indices]**2 + extra**2)
                else:
                    raise ValueError('Weighted objective requires uncertainty or covariance arrays')
            result = fit_expression_least_squares(f, context.data, context.data[c['target']],
                sigma=sigma, whitener=whitener, max_model_evals=self.max_fit_evaluations, allow_nonlinear=False)
            self.last_fit_diagnostics = result.diagnostics
            return result.expression
        # Retain the previous local nonlinear algorithm, with an explicit cap.
        # For regression each loss call performs exactly one model prediction.
        class BudgetExhausted(RuntimeError): pass
        best=x0.copy();score=float('inf');count=0
        def objective(x):
            nonlocal best,score,count
            if count>=self.max_fit_evaluations: raise BudgetExhausted()
            count+=1
            try:
                v=self._loss(f,context,dict(zip(names,x)))
                v=v if np.isfinite(v) else 1e100
            except (ValueError,FloatingPointError,OverflowError,np.linalg.LinAlgError):
                v=1e100
            if v<score: best,score=np.asarray(x).copy(),v
            return v
        exhausted=False;converged=False
        try:
            objective(best)
            for method in ('BFGS','Powell'):
                opt=minimize(objective,best,method=method,options={'maxiter':300})
                objective(opt.x)
                if opt.success and score<1e99:
                    converged=True;break
        except BudgetExhausted:
            exhausted=True
        self.last_fit_diagnostics={'method':'legacy_bfgs_powell','evaluations':count,
            'evaluation_unit':'model prediction' if c['task_type']=='regression' else 'loss evaluation',
            'max_model_evals':self.max_fit_evaluations,'converged':converged,
            'budget_exhausted':exhausted,'objective':float(score)}
        if score>=1e99:raise ValueError('No finite candidate found; inspect density domain and parameter initialization')
        return engine.bind_parameters(f,dict(zip(names,map(float,best))))

    def fit_candidate(self,f,context):return self.fit(f,engine.Symbol(context.target),context)

    def evaluate(self,f,y,context):
        self.validate_expression(f, y, context)
        self._validate_partition(context)
        c,_=self._load(context)
        if c['task_type']=='unbinned_distribution':
            losses,z,err=self._density(f,context)
            lo,hi=self._support(c)
            return {'negative_log_likelihood':float(losses.mean()),'total_negative_log_likelihood':float(losses.sum()),
                    'uniform_nll_gain':float(np.log(hi-lo)-losses.mean()),'n_samples':len(losses),
                    'normalization':z,'quadrature_relative_error':err,'complexity':len(f),
                    'mse':float('nan'),'rmse':float('nan'),'mae':float('nan'),'r2':float('nan')}
        if c['task_type']=='binned_distribution':
            loss,pred=self._counts(f,context)
            metrics=utils.regression_metrics(f,context.data[context.target],pred)
            return {**metrics,'poisson_deviance':loss,'n_samples':len(pred)}
        loss,pred,diagnostics=self._regression_loss(f,context,include_diagnostics=True)
        metrics=utils.regression_metrics(f,context.data[context.target],pred)
        return {**metrics,c.get('objective','mse'):loss,'n_samples':len(pred),**diagnostics}

    def evaluate_candidate(self,f,context):return self.evaluate(f,engine.Symbol(context.target),context)
