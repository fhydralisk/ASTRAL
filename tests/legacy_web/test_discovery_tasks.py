import copy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sr_harness.web.app import create_app
from sr_harness.web.session import InteractiveSession
from sr_harness.web import discovery

@pytest.fixture
def setup(tmp_path, monkeypatch):
    root = tmp_path / 'project'
    folder = root / 'data/Gaia/Chen_NatureAstronomy2023'
    folder.mkdir(parents=True)
    source = folder / '41550_2023_2011_MOESM1_ESM.txt'
    source.write_text('source observations')
    (folder/'README.txt').write_text('reference answer: do not mount')
    monkeypatch.setenv('ASTRAL_PROJECT_ROOT', str(root))
    session = InteractiveSession(tmp_path/'workspace', agent_options={'tools':['evaluate_formula','workspace_shell']})
    with TestClient(create_app(session.workspace, session=session)) as client:
        yield client, session, source

def test_catalog(setup):
    client, _, _ = setup
    tasks = client.get('/api/data/discovery-tasks').json()['tasks']
    assert {t['topic'] for t in tasks} == {'Gaia','FRB','ISM'}
    assert next(t for t in tasks if t['name']=='Chen_NatureAstronomy2023')['available']
    assert not next(t for t in tasks if t['name']=='Feng_Science2022')['available']
    assert all(t['relation_zh'] for t in tasks)
    assert all(t['description_zh'] and t['description_en'] for t in tasks)
    assert all('preparation' not in t and 'evaluation' not in t for t in tasks)

def test_readonly_and_prompts(setup):
    client, session, source = setup
    settings = copy.deepcopy(session.settings)
    data_settings = copy.deepcopy(session.data_agent_settings)
    evaluator = session.context.evaluator
    response = client.post('/api/data/discovery-tasks/load', json={'name':'Chen_NatureAstronomy2023'})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['mounts'] == [source.name]
    assert session.workspace_manager.mount_mode(source.name) == 'read-only'
    with pytest.raises(PermissionError):
        session.workspace_manager.open_for_write(source.name, 'w')
    assert source.read_text() == 'source observations'
    assert not (session.workspace/'README.txt').exists()
    assert not (session.workspace/'context.data').exists()
    assert session.settings == settings and session.data_agent_settings == data_settings
    assert session.context.evaluator is evaluator
    assert set(data['prompts']) == {'data_agent','problem_description','evaluator_agent','system_prompt','user_prompt'}
    assert all(data['prompts'].values())
    assert '-173' not in str(data['prompts'])
    assert '0.745' not in str(data['prompts'])
    assert '构建' in data['prompts']['evaluator_agent']
    assert client.post('/api/data/discovery-tasks/load', json={'name':'Chen_NatureAstronomy2023'}).status_code == 200

def test_invalid_unavailable_busy_collision(setup):
    client, session, source = setup
    assert client.post('/api/data/discovery-tasks/load', json={'name':'../../etc'}).status_code == 400
    assert client.post('/api/data/discovery-tasks/load', json={'name':'Feng_Science2022'}).status_code == 404
    session.state = 'running'
    assert client.post('/api/data/discovery-tasks/load', json={'name':'Chen_NatureAstronomy2023'}).status_code == 400
    session.state = 'idle'
    (session.workspace/source.name).write_text('existing work')
    assert client.post('/api/data/discovery-tasks/load', json={'name':'Chen_NatureAstronomy2023'}).status_code == 409
    assert (session.workspace/source.name).read_text() == 'existing work'
    assert not session.workspace_manager.mount_map

def test_feng_extensionless_observations(tmp_path, monkeypatch):
    monkeypatch.setenv('ASTRAL_PROJECT_ROOT', str(tmp_path))
    folder=tmp_path/'.cache/replication_raw/ScienceDB/group'
    folder.mkdir(parents=True)
    for n in range(37):
        (folder/f'burst{n}').write_bytes(b'SIMPLE  = T')
        (folder/f'burst{n}.download.json').write_text('{}')
    case=next(c for c in discovery.CASES if c['name']=='Feng_Science2022')
    assert discovery.sources(case)==[folder]
    (folder/'burst0').unlink()
    assert discovery.sources(case)==[]

def test_task_mounts_and_prompts_survive_session_restore(setup):
    client, session, source = setup
    client.post('/api/data/discovery-tasks/load', json={'name':'Chen_NatureAstronomy2023'})
    snapshot = session.export_persistent_state()
    restored = InteractiveSession(session.workspace, workspace_path=session.workspace)
    restored.restore_persistent_state(snapshot)
    assert restored.workspace_manager.mount_mode(source.name) == 'read-only'
    assert restored.snapshot()['discovery_task']['prompts']['data_agent']
    with pytest.raises(PermissionError):
        restored.workspace_manager.open_for_write(source.name, 'w')
    legacy = dict(snapshot)
    legacy.pop('discovery_task')
    InteractiveSession(session.workspace, workspace_path=session.workspace).restore_persistent_state(legacy)

def test_browser_transient_promotion_preserves_readonly_input(tmp_path, monkeypatch):
    from sr_harness.web.conversations import ConversationRegistry
    root=tmp_path/'project'
    folder=root/'data/Gaia/Chen_NatureAstronomy2023'
    folder.mkdir(parents=True)
    source=folder/'41550_2023_2011_MOESM1_ESM.txt'
    source.write_text('unaltered original')
    monkeypatch.setenv('ASTRAL_PROJECT_ROOT',str(root))
    registry=ConversationRegistry(tmp_path/'store',persist_sessions=True)
    app=create_app(tmp_path,session=registry.session_proxy,conversation_registry=registry)
    with TestClient(app) as client:
        initial=client.get('/api/conversations').json()
        client.headers['X-SR-Harness-Conversation']=initial['selected']
        client.get('/api/session')
        response=client.post('/api/data/discovery-tasks/load',json={'name':'Chen_NatureAstronomy2023'})
        assert response.status_code==200,response.text
        state=client.get('/api/session').json()
        from pathlib import Path
        logical=Path(state['workspace'])/source.name
        assert logical.is_symlink()
        assert logical.resolve()==source.resolve()
        listing=client.get('/api/workspace').json()['entries']
        assert listing[0]['mounted'] and listing[0]['read_only']
        assert client.put('/api/workspace/upload?path='+source.name,content=b'tamper').status_code>=400
        assert source.read_text()=='unaltered original'


def test_case_specific_selection_without_reference_answers():
    for case in discovery.CASES:
        drafted=discovery.prompts(case,[Path('sample-observations.dat')], 'Generic system instructions')
        assert 'sample-observations.dat' in drafted['data_agent']
        assert '系统接受的数据格式' in drafted['data_agent']
        assert '记录' in drafted['data_agent'] or '包含' in drafted['data_agent']
        assert '{inputs}' not in drafted['data_agent']
        assert drafted['problem_description'] == drafted['user_prompt'] == case['task']
        assert drafted['evaluator_agent'] == case['evaluation']
        assert drafted['system_prompt'] == 'Generic system instructions'
        assert case['relation_zh'] not in str(drafted)
        assert len(drafted['data_agent']) < 300
        assert len(drafted['problem_description']) < 80
        for term in ['公式', '符号回归', '交接', '评测', '训练', '验证', '候选', 'objective',
                     '只读输入', '不要修改原文件', 'context.data']:
            assert term not in drafted['data_agent'], (case['name'], term)
        for term in ['训练', '验证', '评分', 'SDSS', 'LAMOST']:
            assert term not in drafted['problem_description'], (case['name'], term)
    chen=next(c for c in discovery.CASES if c['name']=='Chen_NatureAstronomy2023')
    assert all(term in chen['evaluation'] for term in ['SDSS', 'LAMOST', '独立检验', '重复', '金属丰度误差'])
    xiang=next(c for c in discovery.CASES if c['name']=='Xiang_Nature2022')
    assert '筛选条件' in xiang['preparation']
    assert '族群选择边界' in xiang['evaluation']
