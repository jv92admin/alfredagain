"""
Core test fixtures — StubDomainConfig, no kitchen dependency.

These fixtures enable testing Alfred's orchestration engine in isolation,
proving that src/alfred/ has zero dependency on src/alfred_kitchen/.
"""

import os
import pytest
from unittest.mock import MagicMock

# Set test environment before importing alfred modules
os.environ["ALFRED_ENV"] = "development"
os.environ["ALFRED_USE_ADVANCED_MODELS"] = "false"
os.environ.setdefault("OPENAI_API_KEY", "test-key-not-real")

from alfred.domain.base import (
    CRUDMiddleware,
    DomainConfig,
    EntityDefinition,
    SubdomainDefinition,
)
from alfred.domain import register_domain


# ---------------------------------------------------------------------------
# StubDomainConfig — minimal implementation for core-only tests
# ---------------------------------------------------------------------------


class StubDomainConfig(DomainConfig):
    """
    Minimal DomainConfig for testing core without kitchen.

    2 entities, 2 subdomains, no real DB, no bypass modes.
    Proves that core functions work with any domain, not just kitchen.
    """

    @property
    def name(self) -> str:
        return "stub"

    @property
    def entities(self) -> dict[str, EntityDefinition]:
        return {
            "items": EntityDefinition(
                type_name="item",
                table="items",
                primary_field="name",
                fk_fields=[],
                complexity="medium",
                label_fields=["name"],
            ),
            "notes": EntityDefinition(
                type_name="note",
                table="notes",
                primary_field="title",
                fk_fields=["item_id"],
                complexity=None,
                label_fields=["title"],
            ),
        }

    @property
    def subdomains(self) -> dict[str, SubdomainDefinition]:
        return {
            "items": SubdomainDefinition(
                name="items",
                primary_table="items",
                related_tables=["notes"],
                description="Item management",
            ),
            "notes": SubdomainDefinition(
                name="notes",
                primary_table="notes",
                related_tables=[],
                description="Note management",
            ),
        }

    def get_persona(self, subdomain: str, step_type: str) -> str:
        return f"You are a helpful {subdomain} assistant."

    def get_examples(
        self,
        subdomain: str,
        step_type: str,
        step_description: str = "",
        prev_subdomain: str | None = None,
    ) -> str:
        return ""

    def get_table_format(self, table: str) -> dict:
        return {}

    def get_empty_response(self, subdomain: str) -> str:
        return f"No {subdomain} found."

    def get_fk_enrich_map(self) -> dict[str, tuple[str, str]]:
        return {"item_id": ("items", "name")}

    def get_field_enums(self) -> dict[str, dict[str, list[str]]]:
        return {"items": {"category": ["general", "special"]}}

    def get_semantic_notes(self) -> dict[str, str]:
        return {}

    def get_fallback_schemas(self) -> dict[str, str]:
        return {
            "items": "CREATE TABLE items (id uuid, name text, category text);",
            "notes": "CREATE TABLE notes (id uuid, title text, item_id uuid);",
        }

    def get_scope_config(self) -> dict[str, dict]:
        return {}

    def get_user_owned_tables(self) -> set[str]:
        return {"items", "notes"}

    def get_uuid_fields(self) -> set[str]:
        return {"item_id"}

    def get_subdomain_registry(self) -> dict[str, dict]:
        return {
            "items": {"tables": ["items", "notes"]},
            "notes": {"tables": ["notes"]},
        }

    def get_subdomain_examples(self) -> dict[str, list[str]]:
        return {
            "items": ["Add a new item", "Show my items"],
            "notes": ["Add a note", "Show notes"],
        }

    def infer_entity_type_from_artifact(self, artifact: dict) -> str:
        if "title" in artifact:
            return "note"
        return "item"

    def compute_entity_label(self, record: dict, entity_type: str, ref: str) -> str:
        return record.get("name") or record.get("title") or ref

    def get_subdomain_aliases(self) -> dict[str, str]:
        return {"stuff": "items"}

    def get_subdomain_formatters(self) -> dict:
        return {}

    @property
    def bypass_modes(self) -> dict[str, type]:
        return {}

    @property
    def default_agent(self) -> str:
        return "main"

    def get_handoff_result_model(self) -> type:
        from pydantic import BaseModel

        class StubHandoffResult(BaseModel):
            summary: str = ""
            action: str = "close"
            action_detail: str = ""

        return StubHandoffResult

    def get_db_adapter(self):
        """Return a mock DB adapter for tests."""
        mock = MagicMock()
        mock_table = MagicMock()
        mock_table.select.return_value = mock_table
        mock_table.insert.return_value = mock_table
        mock_table.update.return_value = mock_table
        mock_table.delete.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[])
        mock.table.return_value = mock_table
        mock.rpc.return_value = MagicMock(data=[], execute=MagicMock(return_value=MagicMock(data=[])))
        return mock


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def register_stub_domain():
    """Register StubDomainConfig before each core test."""
    domain = StubDomainConfig()
    register_domain(domain)
    yield domain
    # Reset to None after test (clean slate)
    import alfred.domain as _mod
    _mod._current_domain = None


@pytest.fixture
def stub_domain(register_stub_domain):
    """Explicitly access the StubDomainConfig instance."""
    return register_stub_domain


@pytest.fixture
def mock_openai():
    """Mock OpenAI client for unit tests."""
    mock_client = MagicMock()
    mock_completion = MagicMock()
    mock_completion.choices = [MagicMock(message=MagicMock(content='{"action": "step_complete"}'))]
    mock_client.chat.completions.create.return_value = mock_completion
    return mock_client
