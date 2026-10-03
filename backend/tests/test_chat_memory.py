"""Persistent approved-conversation memory must never cross tenant boundaries."""

from apps.core.chat_memory import ApprovedConversationMemory


def _record(record_id: str, question: str) -> dict:
    return {
        "id": record_id,
        "question": question,
        "interpreted_request": question,
        "verification": {"summary": "Verified against returned data."},
        "executed_at": "2026-09-28T00:00:00+00:00",
        # These must not be persisted in ChromaDB.
        "sql": "SELECT private_value FROM students",
        "rows": [{"private_value": "do-not-store"}],
    }


def test_approved_memory_is_scoped_to_tenant_and_workspace(tmp_path):
    memory = ApprovedConversationMemory(tmp_path / "chroma")
    memory.save_approved_conversation(
        tenant_id="tenant-a", workspace_id="workspace-a", actor_user_id="user-a",
        record=_record("approved-a", "Show attendance this month"),
    )
    memory.save_approved_conversation(
        tenant_id="tenant-b", workspace_id="workspace-b", actor_user_id="user-b",
        record=_record("approved-b", "Show confidential grades"),
    )

    own = memory.search_approved_conversations(
        tenant_id="tenant-a", workspace_id="workspace-a", query="attendance"
    )
    assert [match["id"] for match in own] == ["approved-a"]
    assert "private_value" not in own[0]["content"]
    assert "do-not-store" not in own[0]["content"]
    assert memory.search_approved_conversations(
        tenant_id="tenant-a", workspace_id="workspace-b", query="grades"
    ) == []

    memory.delete_workspace_memory(tenant_id="tenant-a", workspace_id="workspace-a")
    assert memory.search_approved_conversations(
        tenant_id="tenant-a", workspace_id="workspace-a", query="attendance"
    ) == []


def test_deleting_one_conversation_keeps_other_scoped_records(tmp_path):
    memory = ApprovedConversationMemory(tmp_path / "chroma")
    memory.save_approved_conversation(
        tenant_id="tenant-a", workspace_id="workspace-a", actor_user_id="user-a",
        record=_record("keep-this", "Show attendance this month"),
    )
    memory.save_approved_conversation(
        tenant_id="tenant-a", workspace_id="workspace-a", actor_user_id="user-a",
        record=_record("remove-this", "Show late arrivals this month"),
    )
    memory.save_approved_conversation(
        tenant_id="tenant-b", workspace_id="workspace-b", actor_user_id="user-b",
        record=_record("other-tenant", "Show confidential grades"),
    )

    memory.delete_approved_conversation(
        tenant_id="tenant-a", workspace_id="workspace-a", record_id="remove-this"
    )

    remaining = memory.search_approved_conversations(
        tenant_id="tenant-a", workspace_id="workspace-a", query="month"
    )
    assert [item["id"] for item in remaining] == ["keep-this"]
    assert memory.search_approved_conversations(
        tenant_id="tenant-b", workspace_id="workspace-b", query="grades"
    )[0]["id"] == "other-tenant"
