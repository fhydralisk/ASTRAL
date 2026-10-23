import pytest
from sr_harness.web.session import InteractiveSession
from sr_harness.web.discovery import CASES, prompts

@pytest.mark.parametrize('steps',[1,64,256])
def test_evaluator_step_budget_survives_validation(steps):
    assert InteractiveSession.validate_evaluator_agent_settings({'max_steps':steps}) == {'max_steps':steps}

@pytest.mark.parametrize('steps',[0,257,True,1.5,'64'])
def test_evaluator_step_budget_rejects_invalid_values(steps):
    with pytest.raises(ValueError):
        InteractiveSession.validate_evaluator_agent_settings({'max_steps':steps})



def test_legacy_evaluator_settings_restore_with_new_budget(tmp_path):
    session=InteractiveSession(tmp_path/'logs',workspace_path=tmp_path/'work')
    snapshot=session.export_persistent_state()
    snapshot['evaluator_agent_settings'].pop('max_steps')
    session.restore_persistent_state(snapshot)
    assert session.evaluator_agent_settings['max_steps']==64
