from types import SimpleNamespace
import numpy as np
import pytest
from sr_harness.evaluator.observational_contract import audit_contract, audit_evaluator_splits, candidate_role_errors


def example():
    data = dict(y=np.arange(6.), x=np.arange(6.)+10, row=np.arange(6),
                group=np.array([1,1,2,2,3,3]), sigma=np.ones(6),
                partition=np.array(['train']*4+['validation']*2))
    contract = dict(version=1, task_type='regression', target='y', features=['x'],
                    roles=dict(y='target', x='predictor', row='identifier', group='group',
                               sigma='uncertainty', partition='split'),
                    group='group', split='partition', uncertainty='sigma', selection={})
    return contract, data


def test_group_leakage_and_uncertainty_are_rejected():
    c,d=example()
    assert audit_contract(c,d)['valid']
    d['group'][-1]=1
    assert not audit_contract(c,d)['valid']
    d['sigma'][0]=0
    assert 'uncertainty must be strictly positive' in audit_contract(c,d)['errors']


def test_bookkeeping_and_definition_not_discoveries_but_physical_axis_is():
    c,d=example()
    assert candidate_role_errors(c, {'row'}, 'y')
    c['roles']['x']='definition_component'
    assert candidate_role_errors(c, {'x'}, 'y')
    c['roles']['x']='coordinate'
    assert not candidate_role_errors(c, {'x'}, 'y')
    assert candidate_role_errors(c, {'x'}, 'different_target')


def test_distribution_cannot_claim_row_mse_is_valid():
    c,d=example()
    c.update(task_type='binned_distribution', objective='mse')
    assert not audit_contract(c,d)['valid']
    c.update(measure='counts per x interval', support=[0,10], objective='poisson_deviance')
    assert audit_contract(c,d)['valid']


def test_actual_random_split_fails_despite_finite_metrics():
    c,d=example()
    splits={label:SimpleNamespace(data={n:v[d['partition']==label] for n,v in d.items()})
            for label in ('train','validation')}
    assert audit_evaluator_splits(c,d,splits)['valid']
    splits['validation'].data['y']=d['y'][[0,1]]
    assert not audit_evaluator_splits(c,d,splits)['valid']


@pytest.mark.parametrize('change', [dict(target={'name':'y'}),dict(features=['missing']),dict(roles=[]),dict(split='missing')])
def test_malformed_or_logical_names_fail_with_diagnostics(change):
    c,d=example();c.update(change)
    assert not audit_contract(c,d)['valid']


def test_generic_evaluation_keeps_original_behavior_with_contract_file(tmp_path):
    from sr_harness.core import AgentContext
    from sr_harness.runtime.workspace import Workspace
    from sr_harness.tools.evaluate_formula import EvaluateTool
    _, data = example()
    workspace = Workspace(tmp_path)
    # Even an invalid observational file is irrelevant until the extension is selected.
    (tmp_path/'discovery_contract.json').write_text('{invalid json')
    context = AgentContext(data={k:data[k] for k in ('x','y','row')}, target='y', workspace=workspace)
    assert EvaluateTool(context=context).execute('row')['is_candidate']
    assert EvaluateTool(context=context).execute('x-10')['is_candidate']


def test_numerical_helpers_have_correct_semantics():
    import importlib.util
    from pathlib import Path
    p=Path(__file__).resolve().parents[2]/'src/sr_harness/skills/prepare-discovery-handoff/scripts/observational_losses.py'
    spec=importlib.util.spec_from_file_location('loss_helpers',p)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    assert m.poisson_deviance([0,2],[0,2])==0
    assert np.isinf(m.poisson_deviance([1],[0]))
    assert m.poisson_deviance([0],[2])==4
    assert m.weighted_squared_error([1],[0],[2])==.25
    assert m.selected_density_nll([1,1], [1,1], [0,2], [1,1], [1,1])==pytest.approx(np.log(2))
    # Overall density amplitude cancels on the observed support.
    assert m.selected_density_nll([3,3], [3,3], [0,2], [1,1], [1,1])==pytest.approx(np.log(2))


def test_distribution_search_requires_matching_ranking():
    from sr_harness.evaluator.observational_contract import require_search_objective
    c={'task_type':'binned_distribution', 'objective':'poisson_deviance'}
    with pytest.raises(ValueError, match='Return to evaluator'):
        require_search_objective(c,'mse')
    require_search_objective(c,'poisson_deviance')
    require_search_objective(None,'mse')


def test_handoff_split_audit_is_explicit_not_part_of_generic_validation(tmp_path):
    import json
    from sr_harness.core import AgentContext
    from sr_harness.evaluator import DefaultEvaluator
    from sr_harness.runtime.workspace import Workspace
    from sr_harness.tools.validate_evaluator import ValidateEvaluatorTool
    c,d=example()
    w=Workspace(tmp_path)
    (tmp_path/'discovery_contract.json').write_text(json.dumps(c))
    directory=tmp_path/'context.data';directory.mkdir()
    manifest={'axes':{'sample':{'size':6,'description':'bookkeeping'}},'variables':{}}
    for name,value in d.items():
        np.save(directory/f'{name}.npy',value)
        manifest['variables'][name]={'file':f'{name}.npy','axes':['sample'],'description':name}
    (directory/'manifest.json').write_text(json.dumps(manifest))
    class WrongSplit(DefaultEvaluator):
        @classmethod
        def split(cls,context):
            return {label:context.with_data({n:v[idx] for n,v in context.data.items()})
                    for label,idx in [('train',[2,3,4,5]),('validation',[0,1])]}
    class FrozenSplit(DefaultEvaluator):
        @classmethod
        def split(cls,context):
            return {label:context.with_data({n:v[d['partition']==label] for n,v in context.data.items()})
                    for label in ('train','validation')}
    context=AgentContext(data={k:d[k] for k in ('x','y')},target='y',workspace=w,evaluator=WrongSplit())
    assert 'handoff_audit' not in ValidateEvaluatorTool(context=context).execute('x-10')
    from sr_harness.evaluator.observational_contract import require_active_handoff
    with pytest.raises(ValueError,match='before search'):
        require_active_handoff(context)
    context.evaluator=FrozenSplit()
    context.invalidate_splits()
    require_active_handoff(context)
    assert 'handoff_audit' not in ValidateEvaluatorTool(context=context).execute('x-10')


def test_density_coordinate_is_not_regression_label_leakage():
    c,_=example()
    assert candidate_role_errors(c,{'y'},'y')
    c.update(task_type='unbinned_distribution',features=[])
    assert not candidate_role_errors(c,{'y'},'y')
    assert candidate_role_errors(c,{'row'},'y')


def test_generic_prompt_override_is_not_augmented_from_contract(tmp_path):
    import json
    from sr_harness.agents.sr_agent import SRAgent
    from sr_harness.runtime.workspace import Workspace
    class Customized(SRAgent):
        def customize_initial_prompts(self,messages,**kwargs):
            return [{'role':'user','content':'custom user instruction'}]
    agent=object.__new__(Customized)
    agent.max_refinement_depth=20
    agent.context=SimpleNamespace(workspace=Workspace(tmp_path))
    c,_=example()
    (tmp_path/'discovery_contract.json').write_text(json.dumps(c))
    messages=agent.create_initial_prompt_messages('question',{'x':np.arange(6)}, {'y':np.arange(6)},[])
    assert messages == [{'role':'user','content':'custom user instruction'}]
