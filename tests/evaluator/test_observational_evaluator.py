import json
import numpy as np
import pytest
import sr_harness_engine as engine
from sr_harness.core import AgentContext, load_context_data
from sr_harness.runtime.workspace import Workspace
from sr_harness.evaluator import ObservationalEvaluator
from sr_harness.tools.evaluate_observational_formula import EvaluateObservationalFormulaTool


def context(tmp_path, task='unbinned_distribution', **extra):
    w=Workspace(tmp_path);d=tmp_path/'context.data';d.mkdir()
    arrays={'y':np.array([.1,.2,.3,.4,.7,.8]),'x':np.arange(6.),'sigma':np.array([1,2,1,2,1,2.]),
            'group':np.array([0,0,1,1,2,2]),'partition':np.array(['train']*4+['validation']*2)}
    arrays.update(extra.pop('arrays',{}))
    manifest={'axes':{'sample':{'size':6,'description':'row ID'}},'variables':{}}
    for n,a in arrays.items():
        np.save(d/f'{n}.npy',a);manifest['variables'][n]={'file':f'{n}.npy','axes':['sample'],'description':n}
    (d/'manifest.json').write_text(json.dumps(manifest))
    c={'version':1,'task_type':task,'target':'y','features':[] if task=='unbinned_distribution' else ['x'],
       'roles':dict(y='target',x='predictor',sigma='uncertainty',group='group',partition='split'),
       'group':'group','split':'partition','selection':{},'measure':'per unit y','support':{'lower':0,'upper':1},
       'objective':'negative_log_likelihood' if task=='unbinned_distribution' else 'weighted_squared_error','uncertainty':'sigma'}
    c.update(extra);(tmp_path/'discovery_contract.json').write_text(json.dumps(c))
    loaded=load_context_data(d);ctx=AgentContext(workspace=w)
    ctx.commit_context_data(loaded);ctx.update_selection(target='y',features=c['features']);ctx.evaluator=ObservationalEvaluator()
    return ctx


def test_uniform_scale_invariance_and_density_eligibility(tmp_path):
    ctx=context(tmp_path);t=EvaluateObservationalFormulaTool(context=ctx)
    a=t.execute('1');b=t.execute('123')
    assert a['is_candidate'] and b['is_candidate']
    assert a['data_split_results']['validation']['metrics']['negative_log_likelihood']==pytest.approx(0)
    assert b['data_split_results']['validation']['metrics']['negative_log_likelihood']==pytest.approx(0)
    assert np.isnan(a['data_split_results']['validation']['metrics']['mse'])
    with pytest.raises(ValueError,match='positive'):t.execute('-1')


def test_fit_uses_train_not_validation(tmp_path):
    ctx=context(tmp_path,task='regression');t=EvaluateObservationalFormulaTool(context=ctx)
    r=t.execute("param('a', value=0.0)",fit=True)
    expected=np.average([.1,.2,.3,.4],weights=[1,.25,1,.25])
    assert r['fitted_parameters']['a']==pytest.approx(expected,abs=1e-6)
    with pytest.raises(ValueError,match='training'):ctx.evaluator.fit(engine.parse("param('a', value=0.0)"),engine.parse('y'),ctx.validation_split)
    assert len(ctx.train_split.data['y'])==4 and len(ctx.validation_split.data['y'])==2


def test_density_fit_and_no_silent_mse(tmp_path):
    ctx=context(tmp_path);t=EvaluateObservationalFormulaTool(context=ctx)
    r=t.execute("exp(param('a', value=0.0)*y)",fit=True)
    assert r['is_candidate']
    assert r['fitted_parameters']['a']<0
    assert r['data_split_results']['train']['metrics']['negative_log_likelihood']<0
    assert r['data_split_results']['validation']['metrics']['negative_log_likelihood']>0


def test_changed_data_or_group_leakage_rejected(tmp_path):
    ctx=context(tmp_path);ctx.data['y'][0]=99
    with pytest.raises(ValueError,match='differs'):ctx.evaluator.split(ctx)


def test_count_bin_integral_not_center_value(tmp_path):
    arrays={'y':np.ones(6)*2,'lo':np.zeros(6),'hi':np.ones(6)*2,'exposure':np.ones(6)}
    ctx=context(tmp_path,task='binned_distribution',objective='poisson_deviance',arrays=arrays,
                density_coordinate='x',bin_lower='lo',bin_upper='hi',exposure='exposure')
    r=EvaluateObservationalFormulaTool(context=ctx).execute('1')
    assert r['is_candidate']
    assert r['data_split_results']['validation']['metrics']['poisson_deviance']==pytest.approx(0)


def test_contract_file_does_not_activate_evaluator_or_change_session_settings(tmp_path):
    context(tmp_path)
    from sr_harness.evaluator import DefaultEvaluator
    from sr_harness.web.session import InteractiveSession
    session = InteractiveSession(tmp_path/'logs', workspace_path=tmp_path)
    settings = dict(session.settings)
    session.reload_context_data()
    assert type(session.context.evaluator) is DefaultEvaluator
    assert session.settings == settings
    assert session._evaluator_metadata()['selected'] == 'default'


def test_wrong_target_selection_and_support_fail(tmp_path):
    ctx=context(tmp_path)
    ctx.target='sample'
    with pytest.raises(ValueError,match='Selected target'):ctx.evaluator.split(ctx)


def test_missing_parameter_initial_value_has_actionable_error(tmp_path):
    ctx=context(tmp_path)
    with pytest.raises(ValueError, match='explicit finite initial'):
        EvaluateObservationalFormulaTool(context=ctx).execute("exp(param('a')*y)", fit=True)


def test_nonconstant_selection_is_not_assumed_complete(tmp_path):
    ctx=context(tmp_path, selection_probability='efficiency')
    with pytest.raises(ValueError, match='Nonconstant selection'):
        ctx.evaluator.split(ctx)


def test_missing_measurement_scope_cannot_start_symbolic_search(tmp_path):
    ctx=context(tmp_path, replication_status='insufficient_measurements', blocked_reason=['Independent response measurement unavailable'])
    with pytest.raises(ValueError, match='Independent response measurement unavailable'):
        ctx.evaluator.split(ctx)
    from sr_harness.evaluator.observational_contract import require_active_handoff
    with pytest.raises(ValueError, match='Scientific search is not ready'):
        require_active_handoff(ctx)


def test_log_quadrature_preserves_density_measure(tmp_path):
    # On [1,1000], integral(1/y) dy = log(1000), not log(log(1000)).
    values=np.array([1.2,2.,4.,8.,25.,300.])
    ctx=context(tmp_path, arrays={'y':values}, support={'lower':1.,'upper':1000.}, quadrature_scale='log')
    r=EvaluateObservationalFormulaTool(context=ctx).execute('1/y')
    metrics=r['data_split_results']['validation']['metrics']
    assert metrics['normalization']==pytest.approx(np.log(1000),rel=1e-12)
    assert metrics['negative_log_likelihood']==pytest.approx(np.mean(np.log(values[4:]))+np.log(np.log(1000)))
    with pytest.raises(ValueError,match='strictly positive'):
        other=context(tmp_path/'bad', support={'lower':0.,'upper':1.}, quadrature_scale='log')
        EvaluateObservationalFormulaTool(context=other).execute('1')


@pytest.mark.parametrize('operation', ['fit', 'evaluate'])
@pytest.mark.parametrize('formula', ['y', 'sigma', 'unlisted_input'])
def test_direct_evaluator_calls_enforce_declared_variable_roles(tmp_path, operation, formula):
    ctx = context(tmp_path, task='regression')
    with pytest.raises(ValueError, match='scientific predictors'):
        getattr(ctx.evaluator, operation)(engine.parse(formula), engine.parse('y'), ctx.train_split)


@pytest.mark.parametrize('operation', ['fit', 'evaluate'])
def test_direct_evaluator_calls_reject_changed_partition_data(tmp_path, operation):
    ctx = context(tmp_path, task='regression')
    train = ctx.train_split
    train.data['y'] = train.data['y'].copy() + 1
    with pytest.raises(ValueError, match='Partition array differs'):
        getattr(ctx.evaluator, operation)(engine.parse('x'), engine.parse('y'), train)


def test_direct_fitting_cannot_relabel_validation_as_training(tmp_path):
    ctx = context(tmp_path, task='regression')
    forged = ctx.validation_split
    forged.args.observational_partition = 'train'
    with pytest.raises(ValueError, match='Partition indices differ'):
        ctx.evaluator.fit(engine.parse("param('a', value=0)*x"), engine.parse('y'), forged)
