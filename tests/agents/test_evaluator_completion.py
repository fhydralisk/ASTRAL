from types import SimpleNamespace
import pytest
from sr_harness.agents.evaluator_construction_agent import evaluator_probe_is_finite

def result(extra=None):
    metrics=dict.fromkeys(['mse','rmse','mae','mape','r2','aic','bic','pearson_r','spearman_r','complexity'],1.0)
    metrics.update(extra or {})
    return SimpleNamespace(ok=True,result={'data_split_results':{split:{'metrics':dict(metrics)} for split in ['train','validation']}})

def test_split_only_evaluator_does_not_need_invented_metric():
    assert evaluator_probe_is_finite(result())
    assert evaluator_probe_is_finite(result({'n_samples':20}))

@pytest.mark.parametrize('extra',[{'rmse':float('inf')},{'extra':float('nan')},{'n_samples':True},{'extra':'valid'}])
def test_nonfinite_or_nonnumeric_metrics_block_completion(extra):
    assert not evaluator_probe_is_finite(result(extra))

def test_empty_or_incomplete_probe_cannot_unblock_completion():
    assert not evaluator_probe_is_finite(SimpleNamespace(ok=True,result={'data_split_results':{}}))
    r=result();del r.result['data_split_results']['validation']
    assert not evaluator_probe_is_finite(r)


def test_defined_errors_allow_undefined_constant_correlation():
    assert evaluator_probe_is_finite(result({'spearman_r':float('nan')}))
    assert evaluator_probe_is_finite(result({'mse':0.,'rmse':0.,'aic':-float('inf')}))
