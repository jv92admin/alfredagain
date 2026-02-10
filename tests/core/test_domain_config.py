"""
Tests for DomainConfig protocol and StubDomainConfig.

Verifies that a minimal domain implementation satisfies the protocol,
and that computed properties (table_to_type, type_to_table) work.
"""

import pytest

from alfred.domain import get_current_domain
from alfred.domain.base import DomainConfig


class TestStubDomainConfig:
    """Test that StubDomainConfig satisfies DomainConfig protocol."""

    def test_is_domain_config(self, stub_domain):
        assert isinstance(stub_domain, DomainConfig)

    def test_name(self, stub_domain):
        assert stub_domain.name == "stub"

    def test_entities(self, stub_domain):
        assert "items" in stub_domain.entities
        assert "notes" in stub_domain.entities
        assert stub_domain.entities["items"].type_name == "item"
        assert stub_domain.entities["notes"].type_name == "note"

    def test_subdomains(self, stub_domain):
        assert "items" in stub_domain.subdomains
        assert "notes" in stub_domain.subdomains

    def test_table_to_type(self, stub_domain):
        mapping = stub_domain.table_to_type
        assert mapping["items"] == "item"
        assert mapping["notes"] == "note"

    def test_type_to_table(self, stub_domain):
        mapping = stub_domain.type_to_table
        assert mapping["item"] == "items"
        assert mapping["note"] == "notes"

    def test_get_current_domain_returns_stub(self, stub_domain):
        domain = get_current_domain()
        assert domain.name == "stub"

    def test_bypass_modes_empty(self, stub_domain):
        assert stub_domain.bypass_modes == {}

    def test_default_agent(self, stub_domain):
        assert stub_domain.default_agent == "main"

    def test_subdomain_aliases(self, stub_domain):
        aliases = stub_domain.get_subdomain_aliases()
        assert aliases["stuff"] == "items"

    def test_user_owned_tables(self, stub_domain):
        tables = stub_domain.get_user_owned_tables()
        assert "items" in tables
        assert "notes" in tables

    def test_uuid_fields(self, stub_domain):
        fields = stub_domain.get_uuid_fields()
        assert "item_id" in fields

    def test_infer_entity_type(self, stub_domain):
        assert stub_domain.infer_entity_type_from_artifact({"name": "X"}) == "item"
        assert stub_domain.infer_entity_type_from_artifact({"title": "X"}) == "note"

    def test_compute_entity_label(self, stub_domain):
        label = stub_domain.compute_entity_label(
            {"name": "Widget"}, "item", "item_1"
        )
        assert label == "Widget"


class TestDomainConfigDefaults:
    """Test default method implementations on DomainConfig."""

    def test_get_crud_middleware_default(self, stub_domain):
        assert stub_domain.get_crud_middleware() is None

    def test_get_entity_data_legend_default(self, stub_domain):
        assert stub_domain.get_entity_data_legend("item") is None

    def test_detect_detail_level_default(self, stub_domain):
        assert stub_domain.detect_detail_level("item", {}) is None

    def test_get_archive_key_default(self, stub_domain):
        assert stub_domain.get_archive_key_for_description("test") is None

    def test_get_archive_keys_for_subdomain_default(self, stub_domain):
        assert stub_domain.get_archive_keys_for_subdomain("items") == []

    def test_format_entity_for_context_default(self, stub_domain):
        lines = stub_domain.format_entity_for_context(
            "item", "item_1", "Widget", {"name": "Widget", "category": "general"}
        )
        assert any("item_1" in line for line in lines)
        assert any("Widget" in line for line in lines)

    def test_format_record_for_context_default(self, stub_domain):
        result = stub_domain.format_record_for_context({"name": "Widget", "id": "item_1"})
        assert "Widget" in result
        assert "item_1" in result

    def test_format_records_for_context_empty(self, stub_domain):
        result = stub_domain.format_records_for_context([])
        assert len(result) == 1
        assert "no records" in result[0]

    def test_get_system_prompt_default(self, stub_domain):
        prompt = stub_domain.get_system_prompt()
        assert "stub" in prompt

    def test_get_mode_llm_config_default(self, stub_domain):
        assert stub_domain.get_mode_llm_config() == {}

    def test_get_think_domain_context_default(self, stub_domain):
        assert stub_domain.get_think_domain_context() == ""
