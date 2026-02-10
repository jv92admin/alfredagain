"""
Tests for SessionIdRegistry — domain-agnostic entity lifecycle tracking.

Uses StubDomainConfig (no kitchen dependency).
The registry gets its domain via _get_domain() which calls get_current_domain(),
satisfied by the autouse conftest fixture.
"""

import pytest

from alfred.core.id_registry import SessionIdRegistry


class TestSessionIdRegistryBasics:
    """Test basic ref creation and lookup."""

    def test_translate_read_creates_refs(self):
        registry = SessionIdRegistry()
        records = [
            {"id": "uuid-aaa", "name": "Widget A"},
            {"id": "uuid-bbb", "name": "Widget B"},
        ]
        translated = registry.translate_read_output(records, "items")

        assert translated[0]["id"] == "item_1"
        assert translated[1]["id"] == "item_2"

    def test_get_uuid_from_ref(self):
        registry = SessionIdRegistry()
        registry.translate_read_output(
            [{"id": "uuid-aaa", "name": "Widget"}], "items"
        )
        assert registry.get_uuid("item_1") == "uuid-aaa"

    def test_get_ref_from_uuid(self):
        registry = SessionIdRegistry()
        registry.translate_read_output(
            [{"id": "uuid-aaa", "name": "Widget"}], "items"
        )
        assert registry.get_ref("uuid-aaa") == "item_1"

    def test_has_ref(self):
        registry = SessionIdRegistry()
        registry.translate_read_output(
            [{"id": "uuid-aaa", "name": "Widget"}], "items"
        )
        assert registry.has_ref("item_1") is True
        assert registry.has_ref("item_999") is False

    def test_remove_ref(self):
        registry = SessionIdRegistry()
        registry.translate_read_output(
            [{"id": "uuid-aaa", "name": "Widget"}], "items"
        )
        assert registry.remove_ref("item_1") is True
        assert registry.has_ref("item_1") is False


class TestGeneratedEntities:
    """Test gen_* ref lifecycle."""

    def test_register_generated(self):
        registry = SessionIdRegistry()
        ref = registry.register_generated(
            entity_type="item",
            label="New Widget",
            content={"name": "New Widget", "category": "special"},
        )
        assert ref.startswith("gen_item_")
        assert registry.get_artifact_content(ref) is not None

    def test_promote_generated_to_real(self):
        registry = SessionIdRegistry()
        gen_ref = registry.register_generated(
            entity_type="item",
            label="Pending Widget",
            content={"name": "Pending Widget"},
        )
        # Promoting a gen ref keeps the same ref name (gen_item_1) but updates UUID
        promoted_ref = registry.register_created(
            gen_ref=gen_ref,
            uuid="uuid-new",
            entity_type="item",
            label="Pending Widget",
        )
        assert promoted_ref == gen_ref  # Same ref, now points to real UUID
        assert registry.get_uuid(promoted_ref) == "uuid-new"

    def test_get_all_pending_artifacts(self):
        registry = SessionIdRegistry()
        registry.register_generated("item", "Widget 1", {"name": "W1"})
        registry.register_generated("item", "Widget 2", {"name": "W2"})
        pending = registry.get_all_pending_artifacts()
        assert len(pending) == 2


class TestFilterTranslation:
    """Test ref -> UUID translation in filters."""

    def test_translate_filters(self):
        registry = SessionIdRegistry()
        registry.translate_read_output(
            [{"id": "uuid-aaa", "name": "Widget"}], "items"
        )
        filters = [{"field": "id", "op": "eq", "value": "item_1"}]
        translated = registry.translate_filters(filters)
        assert translated[0]["value"] == "uuid-aaa"


class TestPayloadTranslation:
    """Test ref -> UUID translation in write payloads."""

    def test_translate_payload(self):
        registry = SessionIdRegistry()
        registry.translate_read_output(
            [{"id": "uuid-aaa", "name": "Widget"}], "items"
        )
        payload = {"item_id": "item_1", "title": "My Note"}
        translated = registry.translate_payload(payload, "notes")
        assert translated["item_id"] == "uuid-aaa"
        assert translated["title"] == "My Note"


class TestSerialization:
    """Test to_dict / from_dict round-trip."""

    def test_round_trip(self):
        registry = SessionIdRegistry()
        registry.translate_read_output(
            [{"id": "uuid-aaa", "name": "Widget"}], "items"
        )
        data = registry.to_dict()
        restored = SessionIdRegistry.from_dict(data)
        assert restored.get_uuid("item_1") == "uuid-aaa"
        assert restored.get_ref("uuid-aaa") == "item_1"


class TestFormatForPrompt:
    """Test prompt formatting."""

    def test_format_for_prompt(self):
        registry = SessionIdRegistry()
        registry.translate_read_output(
            [{"id": "uuid-aaa", "name": "Widget"}], "items"
        )
        prompt = registry.format_for_prompt()
        assert "item_1" in prompt
        # Labels may or may not appear in basic prompt format
        assert "item" in prompt.lower()

    def test_empty_registry_format(self):
        registry = SessionIdRegistry()
        prompt = registry.format_for_prompt()
        assert isinstance(prompt, str)
