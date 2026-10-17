from sr_harness.web.conversations import ConversationRegistry
from tests.web.test_conversations import _tree_signature


def test_read_only_refresh_updates_metadata_and_cached_session(tmp_path):
    writer = ConversationRegistry(tmp_path, persist_sessions=True, persistence_interval=3600)
    writer.default_session.initial_prompt = 'before'
    writer.persist()
    reader = ConversationRegistry(tmp_path, read_only=True)
    reader.read_only_refresh_interval = 0
    try:
        old = reader.default_session
        first_id = old.conversation_id
        writer.default_session.initial_prompt = 'after'
        added = writer.create('owner', 'New conversation')
        writer.persist()
        writer.rename('owner', first_id, 'Renamed')
        before = _tree_signature(tmp_path)
        listed = reader.list('viewer')['conversations']
        assert {r['name'] for r in listed} == {'Renamed', 'New conversation'}
        reader.select('viewer', added['id'])
        updated = reader.default_session
        assert updated.initial_prompt == 'after'
        assert updated is not old
        assert old.initial_prompt == 'before'  # in-flight requests keep their snapshot
        assert reader.default_session is updated  # unchanged file is cached
        assert _tree_signature(tmp_path) == before
        writer.archive('owner', added['id'], first_id)
        assert len(reader.list('viewer')['conversations']) == 1
    finally:
        reader.close()
        writer.close()


def test_refresh_is_throttled_and_preserves_view_on_invalid_manifest(tmp_path):
    writer = ConversationRegistry(tmp_path)
    writer.create('owner', 'First')
    reader = ConversationRegistry(tmp_path, read_only=True)
    try:
        initial = reader.list('viewer')
        writer.create('owner', 'Second')
        assert reader.list('viewer') == initial
        reader._read_only_refresh_at = 0
        assert len(reader.list('viewer')['conversations']) == 2
        good = reader.manifest_path.read_bytes()
        reader.manifest_path.write_text('{')
        reader._read_only_refresh_at = 0
        assert len(reader.list('viewer')['conversations']) == 2
        reader.manifest_path.write_bytes(good)
    finally:
        reader.close()
        writer.close()
