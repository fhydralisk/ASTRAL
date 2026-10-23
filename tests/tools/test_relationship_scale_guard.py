import numpy as np
import pytest
from sr_harness.tools.relationship_analysis import RelationshipAnalysisTool

def test_large_spline_diagnostic_fails_before_fit():
    x=np.arange(6000,dtype=float)
    with pytest.raises(ValueError,match="collapse_model='bins'"):
        RelationshipAnalysisTool._fit_predict_1d(x,np.sin(x),x[:10],6,'quantile','spline')

def test_large_binned_diagnostic_remains_available():
    x=np.arange(6000,dtype=float)
    result=RelationshipAnalysisTool._fit_predict_1d(x,np.sin(x),x[:10],6,'quantile','bins')
    assert result.shape==(10,)
    assert np.all(np.isfinite(result))
