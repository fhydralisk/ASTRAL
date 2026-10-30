"""Synthetic integration checks for frozen observational fitting wiring."""
import json
import numpy as np
import pytest
from scipy.linalg import solve_triangular
import sr_harness_engine as engine

from sr_harness.core import AgentContext, load_context_data
from sr_harness.evaluator.observational_evaluator import ObservationalEvaluator
from sr_harness.runtime.workspace import Workspace


def make_context(path, *, validation_shift=0., covariance=False, stable=True, budget=1000,
                 sigma=None, asymmetric=False):
    workspace = Workspace(path)
    directory = path/'context.data'
    directory.mkdir()
    x = np.linspace(-1, 1, 12)
    y = 2.4*x - .7 + np.array([.1,-.2,.05,.03,-.08,.13,-.01,.09,1,2,3,4])
    y[8:] += validation_shift
    data = {'x':x, 'y':y, 'sigma':np.linspace(.04,.3,12) if sigma is None else sigma,
            'partition':np.array(['train']*8+['validation']*4), 'group':np.arange(12)}
    contract = {'version':1, 'task_type':'regression', 'target':'y', 'features':['x'],
                'roles':{'x':'predictor','y':'target','sigma':'uncertainty','group':'group','partition':'split'},
                'group':'group','split':'partition','uncertainty':'sigma','selection':{},
                'objective':'gaussian_nll','extra_scatter':.12}
    if covariance:
        data['covariance'] = np.diag(data['sigma']**2)+np.full((12,12),.0009)
        contract['covariance'] = 'covariance'
        contract['roles']['covariance'] = 'uncertainty'
    if asymmetric:
        data.update(lower=data['sigma'], upper=data['sigma']*2)
        contract.update(uncertainty_lower='lower', uncertainty_upper='upper', objective='weighted_squared_error')
        contract['roles'].update(lower='uncertainty', upper='uncertainty')
    manifest = {'axes':{'sample':{'size':12,'description':'observation index'}},'variables':{}}
    for name, array in data.items():
        np.save(directory/f'{name}.npy',array)
        manifest['variables'][name] = {'file':f'{name}.npy','axes':['sample']*array.ndim,'description':name}
    (directory/'manifest.json').write_text(json.dumps(manifest))
    (path/'discovery_contract.json').write_text(json.dumps(contract))
    context = AgentContext(workspace=workspace)
    context.commit_context_data(load_context_data(directory,workspace=workspace))
    context.update_selection(target='y',features=['x'])
    context.evaluator = ObservationalEvaluator(stable_affine_fit=stable,max_fit_evaluations=budget)
    return context, data


def expression():
    return engine.parse("param('a', value=0)*x + param('b', value=0)")


def test_affine_wiring_uses_fixed_scatter_and_never_validation_response(tmp_path):
    results = []
    for label, shift in [('ordinary',0.),('changed',1e20)]:
        context, data = make_context(tmp_path/label,validation_shift=shift)
        fitted = context.evaluator.fit_candidate(expression(),context.train_split)
        results.append(engine.parameter_values(fitted))
        A = np.column_stack([data['x'][:8],np.ones(8)])
        sigma = np.sqrt(data['sigma'][:8]**2+.12**2)
        expected = np.linalg.lstsq(A/sigma[:,None],data['y'][:8]/sigma,rcond=None)[0]
        np.testing.assert_allclose([results[-1]['a'],results[-1]['b']],expected)
        assert context.evaluator.last_fit_diagnostics['method']=='scaled_svd'
        assert context.evaluator.last_fit_diagnostics['evaluations']==5
    assert results[0] == results[1]


def test_covariance_wiring_matches_training_generalized_least_squares(tmp_path):
    context, data = make_context(tmp_path,covariance=True)
    fitted = context.evaluator.fit_candidate(expression(),context.train_split)
    factor = np.linalg.cholesky(data['covariance'][:8,:8]+.12**2*np.eye(8))
    A = np.column_stack([data['x'][:8],np.ones(8)])
    expected = np.linalg.lstsq(solve_triangular(factor,A,lower=True),
                              solve_triangular(factor,data['y'][:8],lower=True),rcond=None)[0]
    actual = engine.parameter_values(fitted)
    np.testing.assert_allclose([actual['a'],actual['b']],expected)


def test_legacy_budget_counts_every_loss_and_returns_best_seen(tmp_path,monkeypatch):
    context,_ = make_context(tmp_path,stable=False,budget=4)
    evaluator = context.evaluator
    train = context.train_split
    original = evaluator._loss
    observed = []
    def record(f,ctx,parameters=None):
        loss = original(f,ctx,parameters)
        observed.append((loss,dict(parameters)))
        return loss
    monkeypatch.setattr(evaluator,'_loss',record)
    fitted = evaluator.fit_candidate(expression(),train)
    assert len(observed)==4
    assert engine.parameter_values(fitted)==min(observed,key=lambda item:item[0])[1]
    assert evaluator.last_fit_diagnostics['evaluations']==4
    assert evaluator.last_fit_diagnostics['budget_exhausted']
    assert not evaluator.last_fit_diagnostics['converged']


def test_affine_budget_and_validation_fit_guard(tmp_path):
    context,_ = make_context(tmp_path,budget=2)
    fitted = context.evaluator.fit_candidate(expression(),context.train_split)
    assert engine.parameter_values(fitted)=={'a':0.,'b':0.}
    assert context.evaluator.last_fit_diagnostics['evaluations']==2
    assert context.evaluator.last_fit_diagnostics['budget_exhausted']
    with pytest.raises(ValueError,match='training partition'):
        context.evaluator.fit_candidate(expression(),context.validation_split)


def test_negative_formal_sigma_is_rejected_before_it_can_be_squared(tmp_path):
    sigma=np.ones(12);sigma[0]=-.1
    context,_=make_context(tmp_path,sigma=sigma)
    with pytest.raises(ValueError,match='strictly positive'):
        context.evaluator.fit_candidate(expression(),context.train_split)


def test_asymmetric_errors_use_legacy_not_fixed_quadratic_svd(tmp_path):
    context,_=make_context(tmp_path,asymmetric=True,budget=20)
    context.evaluator.fit_candidate(expression(),context.train_split)
    assert context.evaluator.last_fit_diagnostics['method']=='legacy_bfgs_powell'
    assert context.evaluator.last_fit_diagnostics['evaluations']<=20


def test_parameterless_fit_does_not_reuse_previous_diagnostics(tmp_path):
    context, _ = make_context(tmp_path)
    evaluator = context.evaluator
    evaluator.fit(expression(), engine.parse('y'), context.train_split)
    assert evaluator.last_fit_diagnostics is not None
    evaluator.fit(engine.parse('1'), engine.parse('y'), context.train_split)
    assert evaluator.last_fit_diagnostics is None
