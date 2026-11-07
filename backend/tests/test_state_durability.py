"""F11/F12: real SQL/Chroma, independent threaded writes, synthetic data only."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
import os
from uuid import uuid4
from threading import Barrier
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select

from apps.api.session import SessionManager
from apps.core import chat_memory, local_state
from apps.core.chat_memory import ApprovedConversationMemory, GuardedConversationMemory, ChatMemoryError
from apps.core.rag import retrieve_context
from backend import database
from backend.main import create_app
from backend.memory_deletions import retry_deletions, deletion_worker
from backend.models import User, MemoryDeletion, MemoryGeneration, WorkspaceHistoryRecord
from backend.routers.auth import current_user
from backend.security import utcnow
from backend.workspace_repository import WorkspaceRepository


@pytest.fixture(params=['sqlite','postgresql'])
def state(request, tmp_path, monkeypatch):
    original_url = database.engine.url.render_as_string(hide_password=False)
    schema = None
    base = None
    if request.param == 'postgresql':
        from sqlalchemy.engine import make_url
        from sqlalchemy.schema import CreateSchema
        url = os.getenv('TEST_PERSISTENCE_POSTGRES_URL')
        if not url:
            pytest.skip('TEST_PERSISTENCE_POSTGRES_URL not configured (dedicated disposable DB)')
        base = database.make_engine(url)
        assert base.dialect.name == 'postgresql'
        schema = 'state_test_'+uuid4().hex
        with base.begin() as connection:
            connection.execute(CreateSchema(schema))
        url = make_url(url).update_query_dict({'options':'-csearch_path='+schema}).render_as_string(hide_password=False)
    else:
        url = 'sqlite:///' + str(tmp_path / 'auth.db')
    database.configure_database(url)
    database.init_db()
    monkeypatch.setattr(local_state, 'STATE_DIRECTORY', tmp_path / 'state')
    monkeypatch.setattr(local_state, 'STATE_PATH', tmp_path / 'state' / 'state.json')
    monkeypatch.setattr('apps.core.workspaces.LOCAL_WORKSPACE_DIRECTORY', tmp_path / 'uploads')
    with database.SessionLocal() as db:
        for owner in ['owner-a', 'owner-b']:
            db.add(User(id=owner, full_name='Synthetic', email=owner+'@example.com', password_hash='synthetic', workspace_type='personal', workspace_role='owner'))
        db.commit()
        repo = WorkspaceRepository(db)
        for owner in ['owner-a', 'owner-b']:
            repo.ensure_tenant(owner, owner, name='Synthetic', workspace_type='personal')
        for workspace, owner in [('a', 'owner-a'), ('a2', 'owner-a'), ('b', 'owner-b')]:
            repo.save_workspace({'id': workspace, 'name': workspace, 'owner_user_id': owner}, owner)
        db.commit()
    manager = SessionManager()
    manager.hydrate_from_database()
    monkeypatch.setattr('apps.api.session.session_manager', manager)
    for route in ['history', 'workspaces', 'query', 'settings']:
        monkeypatch.setattr('apps.api.routers.'+route+'.session_manager', manager)
    storage = ApprovedConversationMemory(tmp_path / 'chroma')
    memory = GuardedConversationMemory(storage)
    monkeypatch.setattr(chat_memory, '_memory', memory)
    def append(record_id, workspace='a', owner='owner-a'):
        record = manager.append_history(workspace, {'id': record_id, 'question': 'Synthetic attendance '+record_id})
        assert memory.save_approved_conversation(tenant_id=owner, workspace_id=workspace, actor_user_id=owner, record=record)
        return record
    def search(workspace='a', owner='owner-a'):
        return memory.search_approved_conversations(tenant_id=owner, workspace_id=workspace, query='attendance', limit=10)
    def due():
        with database.SessionLocal() as db:
            for intent in db.scalars(select(MemoryDeletion)).all():
                intent.next_attempt_at = utcnow()-timedelta(seconds=1)
            db.commit()
    def client():
        app = create_app(include_product=True)
        app.dependency_overrides[current_user] = lambda: User(id='owner-a', full_name='Synthetic', email='owner-a@example.com', workspace_type='personal', workspace_role='owner')
        return TestClient(app)
    try:
        yield SimpleNamespace(manager=manager, memory=memory, storage=storage, append=append, search=search, due=due, client=client, tmp=tmp_path)
    finally:
        database.engine.dispose()
        if schema:
            from sqlalchemy.schema import DropSchema
            with base.begin() as connection:
                connection.execute(DropSchema(schema,cascade=True))
            base.dispose()
        database.configure_database(original_url)


def test_concurrent_mutations_publish_complete_snapshots_without_lost_records(state):
    barrier = Barrier(12, timeout=10)
    def write(i):
        barrier.wait()
        state.manager.add_workspace({'id': 'upload-'+str(i), 'name': 'Synthetic upload', 'owner_user_id': 'owner-a'})
        record = state.manager.append_history('a', {'id': 'q'+str(i), 'question': 'Synthetic attendance'})
        state.manager.set_guardrails('a2', {'max_rows': i+1})
        state.manager.save(active_workspace_id='a')
        state.manager.delete_history('owner-a', 'a', record['id'])
        state.manager.append_history('a', {'id': 'keep'+str(i), 'question': 'Synthetic attendance'})
        return json.loads(local_state.STATE_PATH.read_text())
    with ThreadPoolExecutor(max_workers=12) as pool:
        snapshots = list(pool.map(write, range(12)))
    assert all(isinstance(snapshot['workspaces'], dict) for snapshot in snapshots)
    assert {row['id'] for row in state.manager.get_history('a')} == {'keep'+str(i) for i in range(12)}
    with database.SessionLocal() as db:
        assert {row['id'] for row in WorkspaceRepository(db).get_history('a')} == {'keep'+str(i) for i in range(12)}
    assert len(state.manager.list_workspaces()) == 15
    assert not list(local_state.STATE_DIRECTORY.glob('*.tmp'))


@pytest.mark.parametrize('operation', ['append', 'clear', 'single', 'remove', 'guardrails'])
def test_actual_sql_commit_failure_rolls_back_cache_history_and_intent(state, operation):
    state.append('q1')
    before = local_state.STATE_PATH.read_text()
    def fail(db):
        db.flush()  # Real SQL writes occurred before the injected commit failure.
        raise RuntimeError('synthetic commit failure')
    event.listen(database.SessionLocal, 'before_commit', fail)
    try:
        with pytest.raises(RuntimeError):
            if operation == 'append': state.manager.append_history('a', {'id':'q2'})
            elif operation == 'clear': state.manager.delete_history('owner-a','a')
            elif operation == 'single': state.manager.delete_history('owner-a','a','q1')
            elif operation == 'remove': state.manager.remove_workspace('a')
            else: state.manager.set_guardrails('a', {'max_rows':1})
    finally:
        event.remove(database.SessionLocal, 'before_commit', fail)
    assert [row['id'] for row in state.manager.get_history('a')] == ['q1']
    assert state.manager.get_workspace('a') is not None
    assert local_state.STATE_PATH.read_text() == before
    with database.SessionLocal() as db:
        assert [row['id'] for row in WorkspaceRepository(db).get_history('a')] == ['q1']
        assert db.scalars(select(MemoryDeletion)).all() == []
        assert db.scalars(select(MemoryGeneration)).all() == []


def test_stale_json_does_not_restore_deleted_history_or_workspace(state, monkeypatch):
    state.append('q1')
    stale = local_state.STATE_PATH.read_text()
    state.manager.delete_history('owner-a','a')
    local_state.STATE_PATH.write_text(stale)
    restarted = SessionManager()
    restarted.hydrate_from_database()
    assert restarted.get_history('a') == []
    state.manager.remove_workspace('a')
    local_state.STATE_PATH.write_text(stale)
    restarted = SessionManager()
    restarted.hydrate_from_database()
    assert restarted.get_workspace('a') is None


def test_json_failure_after_commit_does_not_undo_sql_or_resurrect_on_restart(state, monkeypatch):
    state.append('q1')
    def fail(**kwargs): raise OSError('synthetic disk failure')
    monkeypatch.setattr('apps.api.session.save_local_state', fail)
    state.manager.delete_history('owner-a','a')
    assert json.loads(local_state.STATE_PATH.read_text())['query_history']['a'][0]['id'] == 'q1'
    restarted = SessionManager()
    restarted.hydrate_from_database()
    assert restarted.get_history('a') == []


@pytest.mark.parametrize('single', [False, True])
def test_chroma_failure_restart_retry_and_delayed_index_never_resurrect(state, monkeypatch, single):
    old = state.append('q1')
    state.append('q2')
    with monkeypatch.context() as patch:
        def fail(*args, **kwargs): raise OSError('synthetic Chroma unavailable')
        patch.setattr(state.storage._collection, 'delete', fail)
        intent = state.manager.delete_history('owner-a','a','q1' if single else None)
        assert retry_deletions(intent_id=intent) == 1
        assert 'q1' not in [row['id'] for row in state.search()]
        assert all(row['id'] != 'q1' for row in retrieve_context(state.memory, tenant_id='owner-a', workspace_id='a', question='attendance q1'))
        restarted = SessionManager()
        restarted.hydrate_from_database()
        assert 'q1' not in [row['id'] for row in restarted.get_history('a')]
        # Independently reopened storage and policy do not rely on a process-only tombstone.
        reopened = GuardedConversationMemory(ApprovedConversationMemory(state.tmp/'chroma'))
        assert 'q1' not in [row['id'] for row in reopened.search_approved_conversations(tenant_id='owner-a',workspace_id='a',query='attendance')]
        assert reopened.save_approved_conversation(tenant_id='owner-a',workspace_id='a',actor_user_id='owner-a',record=old) is False
        state.append('new')
    state.due()
    assert retry_deletions(intent_id=intent) == 0
    assert 'new' in [row['id'] for row in state.search()]
    assert retry_deletions(intent_id=intent) == 0
    assert 'q1' not in [row['id'] for row in state.search()]


def test_cleanup_preserves_new_generation_even_if_vector_id_reused(state):
    state.append('reused')
    intent = state.manager.delete_history('owner-a','a')
    state.append('reused')  # New generation, same physical vector id.
    assert retry_deletions(intent_id=intent) == 0
    assert [row['id'] for row in state.search()] == ['reused']


def test_scope_and_fail_closed_policy_on_both_retrieval_paths(state, monkeypatch):
    state.append('q1')
    state.append('q2','a2')
    state.append('q3','b','owner-b')
    state.manager.delete_history('owner-a','a')
    assert state.search() == []
    assert [row['id'] for row in state.search('a2')] == ['q2']
    assert [row['id'] for row in state.search('b','owner-b')] == ['q3']
    with pytest.raises(ValueError): state.manager.delete_history('owner-b','a2')
    def unavailable(): raise OSError('synthetic policy DB failure')
    monkeypatch.setattr(database, 'SessionLocal', unavailable)
    with pytest.raises(ChatMemoryError): state.search('a2')
    assert retrieve_context(state.memory,tenant_id='owner-a',workspace_id='a2',question='attendance') == []


def test_api_explicit_pending_status_idempotency_and_isolation(state, monkeypatch):
    state.append('q1')
    def fail(*args, **kwargs): raise OSError('synthetic Chroma failure')
    monkeypatch.setattr(state.storage._collection, 'delete', fail)
    with state.client() as client:
        csrf=client.get('/api/v1/auth/csrf')
        headers={'X-CSRF-Token':client.cookies.get('csrf_token')}
        response=client.delete('/api/history/a/records/q1',headers=headers)
        assert response.status_code == 202 and response.json()['cleanup_pending'] is True
        assert client.get('/api/history/a').json() == []
        assert client.get('/api/history/a/memory/search?q=attendance').json() == {'matches':[]}
        assert client.delete('/api/history/a/records/q1',headers=headers).status_code == 202
        assert client.delete('/api/history/b',headers=headers).status_code == 404


def test_retry_is_bounded_and_respects_backoff(state, monkeypatch):
    state.append('q1')
    intent=state.manager.delete_history('owner-a','a')
    calls=[]
    def fail(*args, **kwargs):
        calls.append(True)
        raise OSError('synthetic Chroma failure')
    monkeypatch.setattr(state.memory, 'cleanup', fail)
    assert retry_deletions(intent_id=intent) == 1
    assert retry_deletions(intent_id=intent) == 1
    assert len(calls) == 1
    with database.SessionLocal() as db: assert db.get(MemoryDeletion,intent).attempts == 1


def test_real_csv_uploads_can_overlap_history_saves_and_deletes(state):
    with state.client() as client:
        client.get('/api/v1/auth/csrf')
        headers={'X-CSRF-Token':client.cookies.get('csrf_token')}
        barrier=Barrier(6,timeout=10)
        def request(i):
            barrier.wait()
            if i < 3:
                return client.post('/api/workspaces/upload',files={'file':('synthetic.csv',b'name,value\na,1\n','text/csv')},headers=headers)
            state.manager.append_history('a',{'id':'keep'+str(i)})
            state.manager.delete_history('owner-a','a','absent'+str(i))
            return client.get('/api/history/a')
        with ThreadPoolExecutor(max_workers=6) as pool: responses=list(pool.map(request,range(6)))
        assert all(response.status_code in (200,201) for response in responses)
        assert {row['id'] for row in state.manager.get_history('a')} == {'keep3','keep4','keep5'}
        assert len(state.manager.list_workspaces()) == 6


def test_worker_stops_and_retries_in_own_process_without_hotloop(monkeypatch):
    calls=[]
    async def run():
        stop=asyncio.Event()
        def retry(**kwargs):
            calls.append(kwargs)
        monkeypatch.setattr('backend.memory_deletions.retry_deletions',retry)
        task=asyncio.create_task(deletion_worker(stop))
        for _ in range(50):
            if calls: break
            await asyncio.sleep(0.001)
        stop.set()
        await task
    asyncio.run(run())
    assert calls == [{'limit':10}]


def test_unique_snapshot_files_have_restrictive_permissions_and_cleanup(state, monkeypatch):
    import os
    from pathlib import Path
    from stat import S_IMODE
    paths=[]
    original=Path.replace
    def replace(path,target):
        paths.append(path)
        assert path.name.startswith('.state-')
        if os.name == 'posix': assert S_IMODE(path.stat().st_mode) == 0o600
        return original(path,target)
    monkeypatch.setattr(Path,'replace',replace)
    state.manager.save()
    state.manager.save()
    assert len(set(paths)) == 2
    def fail(path,target): raise OSError('synthetic rename failure')
    monkeypatch.setattr(Path,'replace',fail)
    state.manager.save()
    assert not list(local_state.STATE_DIRECTORY.glob('*.tmp'))


def test_cleanup_paginated_batches_keep_new_generation_and_finish(state):
    # Real local Chroma with >200 old entries, including legacy vectors without generation.
    raw=state.storage._collection
    ids=['legacy'+str(i) for i in range(205)]
    raw.upsert(ids=ids,documents=['Synthetic attendance']*205,
        embeddings=[[1.0]+[0.0]*63]*205,
        metadatas=[{'tenant_id':'owner-a','workspace_id':'a'} for _ in ids])
    intent=state.manager.delete_history('owner-a','a')
    state.append('new')
    assert retry_deletions(intent_id=intent) == 1
    assert 'new' in [row['id'] for row in state.search()]
    state.due()
    assert retry_deletions(intent_id=intent) == 0
    assert raw.get(where=state.storage._scope('owner-a','a'))['ids'] == ['new']


def test_migration_round_trip_preserves_history_and_establishes_authority(state):
    from alembic import command
    from sqlalchemy import inspect
    from backend.models import PersistenceMarker
    state.append('q1')
    config=database._alembic_config()
    command.downgrade(config,'20261016_0016')
    assert 'memory_deletions' not in inspect(database.engine).get_table_names()
    command.upgrade(config,'head')
    with database.SessionLocal() as db:
        assert db.get(PersistenceMarker,'relational-authority-v1') is not None
        assert [row['id'] for row in WorkspaceRepository(db).get_history('a')] == ['q1']


@pytest.mark.parametrize('workspace,owner',[('a2','owner-a'),('b','owner-b')])
def test_old_cleanup_cannot_delete_same_vector_id_in_other_scope(state,workspace,owner):
    state.append('reused')
    intent=state.manager.delete_history('owner-a','a')
    state.append('reused',workspace,owner)
    assert retry_deletions(intent_id=intent) == 0
    assert [row['id'] for row in state.search(workspace,owner)] == ['reused']


def test_current_vectors_do_not_starve_legacy_cleanup(state):
    intent=state.manager.delete_history('owner-a','a')
    raw=state.storage._collection
    def insert(prefix, count, metadata):
        raw.upsert(ids=[prefix+str(i) for i in range(count)],documents=['Synthetic']*count,
                   embeddings=[[1.0]+[0.0]*63]*count,metadatas=[metadata]*count)
    scope={'tenant_id':'owner-a','workspace_id':'a'}
    insert('current',205,{**scope,'memory_generation':1})
    insert('old',205,scope)
    assert retry_deletions(intent_id=intent) == 1
    state.due()
    assert retry_deletions(intent_id=intent) == 0
    remaining=raw.get(where=state.storage._scope('owner-a','a'))['ids']
    assert set(remaining) == {'current'+str(i) for i in range(205)}


def test_upgrade_of_empty_authoritative_db_never_imports_deleted_workspaces(state):
    from alembic import command
    state.append('q1')
    stale=local_state.STATE_PATH.read_text()
    for workspace in ['a','a2','b']:
        state.manager.remove_workspace(workspace)
    local_state.STATE_PATH.write_text(stale)
    config=database._alembic_config()
    command.downgrade(config,'20261016_0016')
    command.upgrade(config,'head')
    restarted=SessionManager()
    restarted.hydrate_from_database()
    assert restarted.list_workspaces() == []


def test_legacy_import_only_once_before_relational_authority_exists(state):
    from sqlalchemy import delete
    from backend.models import Tenant, PersistenceMarker
    state.append('q1')
    # Construct the pre-authority condition: legacy users exist but no tenant
    # or workspace state has ever been accepted by this simulated installation.
    with database.SessionLocal() as db:
        db.execute(delete(Tenant))
        db.execute(delete(PersistenceMarker))
        db.commit()
    first=SessionManager()
    first.hydrate_from_database()
    assert first.get_workspace('a') is not None
    stale=json.loads(local_state.STATE_PATH.read_text())
    stale['workspaces']['late']={'id':'late','owner_user_id':'owner-a','name':'Must not reimport'}
    local_state.STATE_PATH.write_text(json.dumps(stale))
    second=SessionManager()
    second.hydrate_from_database()
    assert second.get_workspace('late') is None
