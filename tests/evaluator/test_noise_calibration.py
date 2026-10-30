import json
import numpy as np
import pytest

from sr_harness.core import AgentContext
from sr_harness.evaluator.noise_calibration import estimate_affine_scatter
from sr_harness.runtime.workspace import Workspace
from sr_harness.tools.calibrate_observation_scatter import CalibrateObservationScatterTool


def fixture_data(seed=17):
    rng = np.random.default_rng(seed)
    n = 900
    x = rng.normal(size=n)
    sigma = np.exp(rng.uniform(np.log(.003), np.log(.09), n))
    y = 1.5 - .7*x + rng.normal(size=n)*np.sqrt(sigma**2 + .18**2)
    data = {'x':x, 'y':y, 'sigma':sigma, 'group':np.arange(n),
            'partition':np.array(['train']*700 + ['validation']*200)}
    contract = {'version':1, 'task_type':'regression', 'target':'y', 'features':['x'],
                'roles':{'x':'predictor','y':'target','sigma':'uncertainty','group':'group','partition':'split'},
                'group':'group','split':'partition','uncertainty':'sigma','objective':'gaussian_nll',
                'selection':{}}
    return data, contract


def test_profile_estimates_omitted_scatter_and_weight_effective_size():
    data, contract = fixture_data()
    result = estimate_affine_scatter(data, contract)
    assert result['extra_scatter'] == pytest.approx(.18, abs=.025)
    assert result['training_samples'] == 700
    assert result['baseline_rank'] == 2
    assert result['effective_sample_size_after'] > result['effective_sample_size_before']*2
    assert result['training_nll'] < result['training_nll_zero_scatter']
    assert result['validation_used'] is False
    assert 'misspecification' in result['warning']


def test_validation_responses_and_predictors_do_not_influence_calibration():
    data, contract = fixture_data()
    before = estimate_affine_scatter(data, contract)
    validation = data['partition'] == 'validation'
    data['y'][validation] = np.arange(validation.sum()) * 1e20
    data['x'][validation] = -1e30
    data['sigma'][validation] = 1e-30
    after = estimate_affine_scatter(data, contract)
    assert before == after


def test_zero_scatter_endpoint_is_retained_for_exact_baseline():
    data, contract = fixture_data()
    data['y'] = 1.5 - .7*data['x']
    result = estimate_affine_scatter(data, contract)
    assert result['extra_scatter'] == 0


@pytest.mark.parametrize('change', [
    {'task_type':'unbinned_distribution','objective':'negative_log_likelihood'},
    {'covariance':'matrix'}, {'uncertainty_lower':'sigma'}, {'uncertainty':None},
])
def test_inapplicable_observation_models_are_rejected(change):
    data, contract = fixture_data()
    contract.update(change)
    with pytest.raises(ValueError):
        estimate_affine_scatter(data, contract)


def test_tool_preview_and_apply_updates_only_contract(tmp_path):
    data, contract = fixture_data()
    workspace = Workspace(tmp_path)
    directory = tmp_path/'context.data'
    directory.mkdir()
    manifest = {'axes':{'sample':{'size':900,'description':'observation row'}},'variables':{}}
    for name, array in data.items():
        np.save(directory/f'{name}.npy', array)
        manifest['variables'][name] = {'file':f'{name}.npy','axes':['sample'],'description':name}
    (directory/'manifest.json').write_text(json.dumps(manifest))
    path = tmp_path/'discovery_contract.json'
    path.write_text(json.dumps(contract))
    tool = CalibrateObservationScatterTool(context=AgentContext(workspace=workspace))
    preview = tool.execute()
    assert not preview['applied']
    assert json.loads(path.read_text()) == contract
    applied = tool.execute(apply=True)
    saved = json.loads(path.read_text())
    assert saved['extra_scatter'] == applied['extra_scatter']
    assert saved['extra_scatter_calibration']['training_data_sha256'] == preview['training_data_sha256']
    assert saved['features'] == contract['features']
    assert saved['objective'] == contract['objective']
