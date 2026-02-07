"""
Tests for Cook and Brainstorm modes.

Tests the lightweight modes that bypass the LangGraph graph:
- LLM client: call_llm_chat, call_llm_chat_stream
- Cook mode: init, chat turns, exit with handoff
- Brainstorm mode: init, chat turns, exit with handoff
- Handoff: structured summary generation
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    """Run an async coroutine synchronously (no pytest-asyncio needed)."""
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_chat_completion(content: str) -> MagicMock:
    """Build a mock ChatCompletion response."""
    choice = MagicMock()
    choice.message.content = content
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def _make_stream_chunks(tokens: list[str]):
    """Build an async iterator of streaming chunks."""
    chunks = []
    for token in tokens:
        chunk = MagicMock()
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta.content = token
        chunks.append(chunk)

    # Final chunk with no content (stream end)
    final = MagicMock()
    final.choices = [MagicMock()]
    final.choices[0].delta.content = None
    chunks.append(final)

    async def async_iter():
        for c in chunks:
            yield c

    return async_iter()


async def _collect_events(generator) -> list[dict]:
    """Collect all events from an async generator."""
    events = []
    async for event in generator:
        events.append(event)
    return events


# Sample data (matching conftest fixtures but inline for simplicity)
SAMPLE_RECIPE = {
    "id": "recipe-1",
    "name": "Pancakes",
    "description": "Fluffy buttermilk pancakes",
    "cuisine": "american",
    "difficulty": "easy",
    "servings": 4,
    "prep_time_minutes": 10,
    "cook_time_minutes": 15,
    "instructions": [
        "Mix dry ingredients",
        "Whisk wet ingredients",
        "Combine and let rest",
        "Cook on griddle",
    ],
    "tags": ["breakfast", "quick"],
    "recipe_ingredients": [
        {"name": "flour", "category": "baking"},
        {"name": "milk", "category": "dairy"},
        {"name": "eggs", "category": "dairy"},
        {"name": "butter", "category": "dairy"},
    ],
}


# ---------------------------------------------------------------------------
# LLM Client Tests
# ---------------------------------------------------------------------------

class TestCallLlmChat:
    """Tests for call_llm_chat (non-streaming)."""

    def test_returns_text(self):
        mock_client = AsyncMock()
        mock_client.chat.completions.create.return_value = _make_chat_completion(
            "Caramelize onions low and slow."
        )

        with patch("alfred.llm.client.get_raw_async_client", return_value=mock_client), \
             patch("alfred.llm.client.log_prompt"):
            from alfred.llm.client import call_llm_chat

            result = _run(call_llm_chat(
                messages=[
                    {"role": "system", "content": "You are a cook."},
                    {"role": "user", "content": "How do I caramelize onions?"},
                ],
            ))

        assert result == "Caramelize onions low and slow."
        mock_client.chat.completions.create.assert_called_once()

    def test_uses_correct_model(self):
        mock_client = AsyncMock()
        mock_client.chat.completions.create.return_value = _make_chat_completion("ok")

        with patch("alfred.llm.client.get_raw_async_client", return_value=mock_client), \
             patch("alfred.llm.client.log_prompt"):
            from alfred.llm.client import call_llm_chat

            _run(call_llm_chat(
                messages=[{"role": "user", "content": "test"}],
                complexity="low",
                node_name="cook",
            ))

        call_kwargs = mock_client.chat.completions.create.call_args
        assert call_kwargs.kwargs["model"] == "gpt-4.1-mini"

    def test_logs_on_error(self):
        mock_client = AsyncMock()
        mock_client.chat.completions.create.side_effect = Exception("API error")

        with patch("alfred.llm.client.get_raw_async_client", return_value=mock_client), \
             patch("alfred.llm.client.log_prompt") as mock_log:
            from alfred.llm.client import call_llm_chat

            with pytest.raises(Exception, match="API error"):
                _run(call_llm_chat(
                    messages=[{"role": "user", "content": "test"}],
                ))

        mock_log.assert_called_once()
        assert mock_log.call_args.kwargs["error"] == "API error"


class TestCallLlmChatStream:
    """Tests for call_llm_chat_stream (streaming)."""

    def test_yields_tokens(self):
        mock_client = AsyncMock()
        mock_client.chat.completions.create.return_value = _make_stream_chunks(
            ["Hello", " there", "!"]
        )

        async def _test():
            with patch("alfred.llm.client.get_raw_async_client", return_value=mock_client), \
                 patch("alfred.llm.client.log_prompt"):
                from alfred.llm.client import call_llm_chat_stream

                tokens = []
                async for token in call_llm_chat_stream(
                    messages=[{"role": "user", "content": "hi"}],
                ):
                    tokens.append(token)

            return tokens

        tokens = _run(_test())
        assert tokens == ["Hello", " there", "!"]

    def test_logs_full_response_after_stream(self):
        mock_client = AsyncMock()
        mock_client.chat.completions.create.return_value = _make_stream_chunks(
            ["Good", " morning"]
        )

        async def _test():
            with patch("alfred.llm.client.get_raw_async_client", return_value=mock_client), \
                 patch("alfred.llm.client.log_prompt") as mock_log:
                from alfred.llm.client import call_llm_chat_stream

                async for _ in call_llm_chat_stream(
                    messages=[{"role": "user", "content": "hi"}],
                ):
                    pass

            return mock_log

        mock_log = _run(_test())
        mock_log.assert_called_once()
        assert mock_log.call_args.kwargs["response"] == "Good morning"


# ---------------------------------------------------------------------------
# Cook Mode Tests
# ---------------------------------------------------------------------------

class TestCookModeInit:
    """Tests for cook mode initialization (first turn)."""

    def test_init_fetches_recipe_and_sets_state(self):
        mock_stream = _make_stream_chunks(["Let's", " get", " cooking!"])

        async def _test():
            with patch("alfred.modes.cook.db_read", new_callable=AsyncMock) as mock_read, \
                 patch("alfred.llm.client.get_raw_async_client") as mock_client_fn, \
                 patch("alfred.llm.client.log_prompt"):
                mock_read.return_value = [SAMPLE_RECIPE]
                mock_client = AsyncMock()
                mock_client.chat.completions.create.return_value = mock_stream
                mock_client_fn.return_value = mock_client

                from alfred.modes.cook import run_cook_session

                conversation = {}
                events = await _collect_events(run_cook_session(
                    user_message="Let's cook!",
                    user_id="user-1",
                    conversation=conversation,
                    cook_init={"recipe_id": "recipe-1", "notes": "Extra garlic"},
                ))
                return conversation, events

        conversation, events = _run(_test())

        assert conversation["active_mode"] == "cook"
        assert conversation["cook_recipe_name"] == "Pancakes"
        assert "cook_context" in conversation
        assert "Extra garlic" in conversation["cook_context"]
        assert "flour" in conversation["cook_context"]
        assert "Mix dry ingredients" in conversation["cook_context"]

        chunk_events = [e for e in events if e["type"] == "chunk"]
        done_events = [e for e in events if e["type"] == "done"]
        assert len(chunk_events) == 3
        assert len(done_events) == 1
        assert done_events[0]["response"] == "Let's get cooking!"

    def test_init_no_recipe_id_returns_error(self):
        async def _test():
            from alfred.modes.cook import run_cook_session
            conversation = {}
            return await _collect_events(run_cook_session(
                user_message="Let's cook!",
                user_id="user-1",
                conversation=conversation,
                cook_init={"notes": ""},
            ))

        events = _run(_test())
        assert events[0]["type"] == "error"
        assert "No recipe selected" in events[0]["error"]

    def test_init_recipe_not_found_returns_error(self):
        async def _test():
            with patch("alfred.modes.cook.db_read", new_callable=AsyncMock) as mock_read:
                mock_read.return_value = []
                from alfred.modes.cook import run_cook_session
                conversation = {}
                return await _collect_events(run_cook_session(
                    user_message="Let's cook!",
                    user_id="user-1",
                    conversation=conversation,
                    cook_init={"recipe_id": "nonexistent"},
                ))

        events = _run(_test())
        assert events[0]["type"] == "error"
        assert "not found" in events[0]["error"]


class TestCookModeChatTurn:
    """Tests for cook mode chat turns."""

    def test_chat_appends_to_history(self):
        mock_stream = _make_stream_chunks(["Medium", " heat."])

        async def _test():
            with patch("alfred.llm.client.get_raw_async_client") as mock_client_fn, \
                 patch("alfred.llm.client.log_prompt"):
                mock_client = AsyncMock()
                mock_client.chat.completions.create.return_value = mock_stream
                mock_client_fn.return_value = mock_client

                from alfred.modes.cook import run_cook_session

                conversation = {
                    "active_mode": "cook",
                    "cook_context": "Recipe: Pancakes\n1. Mix\n2. Cook",
                    "cook_history": [],
                    "cook_recipe_name": "Pancakes",
                }

                await _collect_events(run_cook_session(
                    user_message="What heat setting?",
                    user_id="user-1",
                    conversation=conversation,
                ))
                return conversation

        conversation = _run(_test())
        assert len(conversation["cook_history"]) == 2
        assert conversation["cook_history"][0]["role"] == "user"
        assert conversation["cook_history"][1]["role"] == "assistant"
        assert conversation["cook_history"][1]["content"] == "Medium heat."

    def test_chat_without_cook_context_returns_error(self):
        async def _test():
            from alfred.modes.cook import run_cook_session
            conversation = {"active_mode": "plan"}
            return await _collect_events(run_cook_session(
                user_message="test",
                user_id="user-1",
                conversation=conversation,
            ))

        events = _run(_test())
        assert events[0]["type"] == "error"
        assert "Not in cook mode" in events[0]["error"]

    def test_llm_failure_returns_error_event(self):
        async def _test():
            with patch("alfred.llm.client.get_raw_async_client") as mock_client_fn, \
                 patch("alfred.llm.client.log_prompt"):
                mock_client = AsyncMock()
                mock_client.chat.completions.create.side_effect = Exception("LLM down")
                mock_client_fn.return_value = mock_client

                from alfred.modes.cook import run_cook_session

                conversation = {
                    "active_mode": "cook",
                    "cook_context": "Recipe context",
                    "cook_history": [],
                    "cook_recipe_name": "Test",
                }

                return await _collect_events(run_cook_session(
                    user_message="test",
                    user_id="user-1",
                    conversation=conversation,
                ))

        events = _run(_test())
        error_events = [e for e in events if e["type"] == "error"]
        assert len(error_events) == 1
        assert "Something went wrong" in error_events[0]["error"]


class TestCookModeExit:
    """Tests for cook mode exit with handoff."""

    def test_exit_with_save_action_injects_summary(self):
        from alfred.domain.kitchen.handoff import HandoffResult

        mock_handoff = HandoffResult(
            summary="Cooked Pancakes. Doubled the garlic.",
            action="save",
            action_detail="Modified recipe worth saving.",
        )

        async def _test():
            with patch("alfred.modes.cook.generate_session_handoff", new_callable=AsyncMock) as mock_fn:
                mock_fn.return_value = mock_handoff

                from alfred.modes.cook import run_cook_session

                conversation = {
                    "active_mode": "cook",
                    "cook_context": "Recipe context",
                    "cook_history": [
                        {"role": "user", "content": "I doubled the garlic"},
                        {"role": "assistant", "content": "Good choice!"},
                    ],
                    "cook_recipe_name": "Pancakes",
                    "recent_turns": [],
                }

                events = await _collect_events(run_cook_session(
                    user_message="__cook_exit__",
                    user_id="user-1",
                    conversation=conversation,
                ))
                return conversation, events

        conversation, events = _run(_test())

        handoff_events = [e for e in events if e["type"] == "handoff"]
        assert len(handoff_events) == 1
        assert handoff_events[0]["action"] == "save"
        assert "Pancakes" in handoff_events[0]["summary"]
        assert len(conversation["recent_turns"]) == 1
        assert "Cook session" in conversation["recent_turns"][0]["user"]
        assert conversation["active_mode"] == "plan"
        assert "cook_context" not in conversation

    def test_exit_with_close_action_no_injection(self):
        from alfred.domain.kitchen.handoff import HandoffResult

        mock_handoff = HandoffResult(
            summary="Normal cook session.",
            action="close",
            action_detail="Nothing to persist.",
        )

        async def _test():
            with patch("alfred.modes.cook.generate_session_handoff", new_callable=AsyncMock) as mock_fn:
                mock_fn.return_value = mock_handoff
                from alfred.modes.cook import run_cook_session
                conversation = {
                    "active_mode": "cook",
                    "cook_context": "Recipe context",
                    "cook_history": [
                        {"role": "user", "content": "Done"},
                        {"role": "assistant", "content": "Great!"},
                    ],
                    "cook_recipe_name": "Pancakes",
                    "recent_turns": [],
                }
                await _collect_events(run_cook_session(
                    user_message="__cook_exit__",
                    user_id="user-1",
                    conversation=conversation,
                ))
                return conversation

        conversation = _run(_test())
        assert len(conversation["recent_turns"]) == 0
        assert conversation["active_mode"] == "plan"

    def test_exit_with_empty_history(self):
        async def _test():
            from alfred.modes.cook import run_cook_session
            conversation = {
                "active_mode": "cook",
                "cook_context": "Recipe context",
                "cook_history": [],
                "cook_recipe_name": "Pancakes",
            }
            events = await _collect_events(run_cook_session(
                user_message="__cook_exit__",
                user_id="user-1",
                conversation=conversation,
            ))
            return conversation, events

        conversation, events = _run(_test())
        handoff_events = [e for e in events if e["type"] == "handoff"]
        assert handoff_events[0]["action"] == "close"
        assert conversation["active_mode"] == "plan"


# ---------------------------------------------------------------------------
# Brainstorm Mode Tests
# ---------------------------------------------------------------------------

class TestBrainstormModeInit:
    """Tests for brainstorm mode initialization."""

    def test_init_loads_profile_and_dashboard(self):
        from alfred.background.profile_builder import UserProfile, KitchenDashboard

        mock_profile = UserProfile()
        mock_dashboard = KitchenDashboard()
        mock_stream = _make_stream_chunks(["Let's", " brainstorm!"])

        async def _test():
            with patch("alfred.modes.brainstorm.get_cached_profile", new_callable=AsyncMock) as mock_prof, \
                 patch("alfred.modes.brainstorm.get_cached_dashboard", new_callable=AsyncMock) as mock_dash, \
                 patch("alfred.llm.client.get_raw_async_client") as mock_client_fn, \
                 patch("alfred.llm.client.log_prompt"):
                mock_prof.return_value = mock_profile
                mock_dash.return_value = mock_dashboard
                mock_client = AsyncMock()
                mock_client.chat.completions.create.return_value = mock_stream
                mock_client_fn.return_value = mock_client

                from alfred.modes.brainstorm import run_brainstorm

                conversation = {}
                events = await _collect_events(run_brainstorm(
                    user_message="What can I make with chicken?",
                    user_id="user-1",
                    conversation=conversation,
                    brainstorm_init=True,
                ))
                return conversation, events

        conversation, events = _run(_test())
        assert conversation["active_mode"] == "brainstorm"
        assert "brainstorm_context" in conversation
        assert len(conversation["brainstorm_history"]) == 2

        chunk_events = [e for e in events if e["type"] == "chunk"]
        assert len(chunk_events) == 2


class TestBrainstormModeExit:
    """Tests for brainstorm exit with handoff."""

    def test_exit_with_save_injects_summary(self):
        from alfred.domain.kitchen.handoff import HandoffResult

        mock_handoff = HandoffResult(
            summary="Developed Miso Eggplant concept.",
            action="save",
            action_detail="Recipe idea ready to formalize.",
        )

        async def _test():
            with patch("alfred.modes.brainstorm.generate_session_handoff", new_callable=AsyncMock) as mock_fn:
                mock_fn.return_value = mock_handoff
                from alfred.modes.brainstorm import run_brainstorm
                conversation = {
                    "active_mode": "brainstorm",
                    "brainstorm_context": "Kitchen context",
                    "brainstorm_history": [
                        {"role": "user", "content": "What about miso eggplant?"},
                        {"role": "assistant", "content": "Great idea!"},
                    ],
                    "recent_turns": [],
                }
                events = await _collect_events(run_brainstorm(
                    user_message="__brainstorm_exit__",
                    user_id="user-1",
                    conversation=conversation,
                ))
                return conversation, events

        conversation, events = _run(_test())
        handoff_events = [e for e in events if e["type"] == "handoff"]
        assert handoff_events[0]["action"] == "save"
        assert len(conversation["recent_turns"]) == 1
        assert conversation["active_mode"] == "plan"
        assert "brainstorm_context" not in conversation


# ---------------------------------------------------------------------------
# Handoff Tests
# ---------------------------------------------------------------------------

class TestHandoff:
    """Tests for generate_session_handoff."""

    def test_cook_handoff_returns_structured_result(self):
        from alfred.domain.kitchen.handoff import HandoffResult

        mock_result = HandoffResult(
            summary="Cooked butter chicken with extra spice.",
            action="update",
            action_detail="User wants to adjust spice levels.",
        )

        async def _test():
            with patch("alfred.modes.handoff.call_llm", new_callable=AsyncMock) as mock_llm:
                mock_llm.return_value = mock_result
                from alfred.modes.handoff import generate_session_handoff
                result = await generate_session_handoff("cook", [
                    {"role": "user", "content": "I added extra chili"},
                    {"role": "assistant", "content": "Nice!"},
                ])
                return result, mock_llm

        result, mock_llm = _run(_test())
        assert result.action == "update"
        assert "butter chicken" in result.summary
        mock_llm.assert_called_once()
        call_kwargs = mock_llm.call_args.kwargs
        assert "cook" in call_kwargs["system_prompt"].lower()

    def test_brainstorm_handoff_uses_brainstorm_prompt(self):
        from alfred.domain.kitchen.handoff import HandoffResult

        mock_result = HandoffResult(
            summary="Explored miso glazes.",
            action="close",
            action_detail="Exploratory session.",
        )

        async def _test():
            with patch("alfred.modes.handoff.call_llm", new_callable=AsyncMock) as mock_llm:
                mock_llm.return_value = mock_result
                from alfred.modes.handoff import generate_session_handoff
                await generate_session_handoff("brainstorm", [
                    {"role": "user", "content": "Tell me about miso"},
                ])
                return mock_llm

        mock_llm = _run(_test())
        call_kwargs = mock_llm.call_args.kwargs
        assert "brainstorm" in call_kwargs["system_prompt"].lower()


# ---------------------------------------------------------------------------
# Mode Enum Tests
# ---------------------------------------------------------------------------

class TestModeConfig:
    """Tests for Mode enum and configuration."""

    def test_bypass_modes_registered_via_domain(self):
        """Bypass modes (cook, brainstorm) are registered via DomainConfig, not Mode enum."""
        from alfred.domain import get_current_domain
        domain = get_current_domain()
        assert "cook" in domain.bypass_modes
        assert "brainstorm" in domain.bypass_modes

    def test_core_modes_no_bypass(self):
        """Core modes (QUICK, PLAN, CREATE) don't have bypass_graph flag."""
        from alfred.core.modes import Mode, MODE_CONFIG
        for mode in Mode:
            config = MODE_CONFIG[mode]
            assert config.get("bypass_graph") is None or config.get("bypass_graph") is False

    def test_plan_mode_unchanged(self):
        from alfred.core.modes import Mode, MODE_CONFIG
        config = MODE_CONFIG[Mode.PLAN]
        assert config.get("bypass_graph") is None or config.get("bypass_graph") is False
        assert config["max_steps"] == 8
        assert config["skip_think"] is False

    def test_bypass_mode_llm_config_via_domain(self):
        """Bypass mode LLM configs come from domain, not NODE_TEMPERATURE."""
        from alfred.domain import get_current_domain
        from alfred.llm.model_router import NODE_TEMPERATURE
        domain = get_current_domain()
        mode_config = domain.get_mode_llm_config()
        # cook/brainstorm are in domain config, not in core NODE_TEMPERATURE
        assert "cook" not in NODE_TEMPERATURE
        assert "brainstorm" not in NODE_TEMPERATURE
        assert mode_config["cook"]["temperature"] == 0.4
        assert mode_config["brainstorm"]["temperature"] == 0.6
        # handoff stays in core
        assert "handoff" in NODE_TEMPERATURE


# ---------------------------------------------------------------------------
# Plan State Preservation Tests
# ---------------------------------------------------------------------------

class TestPlanStatePreservation:
    """Verify Plan mode state is preserved during Cook/Brainstorm."""

    def test_cook_preserves_plan_state(self):
        mock_stream = _make_stream_chunks(["ok"])

        async def _test():
            with patch("alfred.modes.cook.db_read", new_callable=AsyncMock) as mock_read, \
                 patch("alfred.llm.client.get_raw_async_client") as mock_client_fn, \
                 patch("alfred.llm.client.log_prompt"):
                mock_read.return_value = [SAMPLE_RECIPE]
                mock_client = AsyncMock()
                mock_client.chat.completions.create.return_value = mock_stream
                mock_client_fn.return_value = mock_client

                from alfred.modes.cook import run_cook_session

                conversation = {
                    "id_registry": {"recipe_1": "uuid-123"},
                    "recent_turns": [{"user": "show recipes", "assistant": "Here are..."}],
                    "turn_summaries": ["User asked about recipes"],
                }

                await _collect_events(run_cook_session(
                    user_message="Let's cook!",
                    user_id="user-1",
                    conversation=conversation,
                    cook_init={"recipe_id": "recipe-1"},
                ))
                return conversation

        conversation = _run(_test())
        assert conversation["id_registry"] == {"recipe_1": "uuid-123"}
        assert len(conversation["recent_turns"]) == 1
        assert conversation["turn_summaries"] == ["User asked about recipes"]
        assert conversation["active_mode"] == "cook"
        assert "cook_context" in conversation
