"""
Background workflow execution for Alfred.

Decouples the LLM workflow from the SSE request lifecycle so that
workflows complete even if the client disconnects (phone locks, network blip).

The SSE endpoint creates an asyncio.Queue, launches the workflow as a
background task, and reads events from the queue. If the client disconnects,
the background task keeps running and stores the result in the jobs table.

See: docs/ideas/job-durability-spec.md (Phase 3)
"""

import asyncio
import logging
from typing import Any

from alfred.db.request_context import clear_request_context, set_request_context
from alfred.graph.workflow import run_alfred_streaming
from alfred.web.jobs import complete_job, fail_job
from alfred.web.session import commit_conversation

logger = logging.getLogger(__name__)

# In-memory event queues keyed by job_id (for cleanup tracking only).
# The queue is passed directly to the background worker; this dict
# allows deferred cleanup after the background task finishes.
job_event_queues: dict[str, asyncio.Queue] = {}


async def run_workflow_background(
    job_id: str | None,
    event_queue: asyncio.Queue,
    user_id: str,
    access_token: str,
    message: str,
    mode: str,
    conversation: dict[str, Any],
    ui_changes: list[dict] | None,
    conversations_cache: dict[str, dict[str, Any]],
    log_prompts: bool = False,
) -> None:
    """Run Alfred workflow independent of request lifecycle.

    Yields events into the provided queue (if any SSE listener is connected).
    Stores final result in jobs table regardless of client connection state.
    """
    from alfred.llm.prompt_logger import enable_prompt_logging, set_user_id

    queue = event_queue

    try:
        # Set up context for this task
        set_request_context(access_token=access_token, user_id=user_id)
        enable_prompt_logging(log_prompts)
        set_user_id(user_id)

        async for update in run_alfred_streaming(
            user_message=message,
            user_id=user_id,
            conversation=conversation,
            mode=mode,
            ui_changes=ui_changes,
        ):
            # Relay event to SSE listener (if still connected)
            if queue:
                try:
                    queue.put_nowait(update)
                except asyncio.QueueFull:
                    pass  # Drop event if queue is full (client too slow)

            # Handle terminal events
            if update["type"] == "done":
                if job_id:
                    try:
                        complete_job(access_token, job_id, {
                            "response": update["response"],
                            "active_context": update.get("active_context"),
                        })
                    except Exception as e:
                        logger.error(f"Failed to complete job {job_id}: {e}")

                commit_conversation(
                    user_id, access_token,
                    update["conversation"], conversations_cache,
                )

            elif update["type"] == "context_updated":
                # Post-summarization conversation update
                commit_conversation(
                    user_id, access_token,
                    update["conversation"], conversations_cache,
                )

    except Exception as e:
        logger.exception(f"Background workflow failed for job {job_id}")
        if job_id:
            fail_job(access_token, job_id, str(e))
        if queue:
            try:
                queue.put_nowait({"type": "error", "error": str(e)})
            except asyncio.QueueFull:
                pass

    finally:
        # Signal end-of-stream to SSE listener
        if queue:
            try:
                queue.put_nowait({"type": "stream_end"})
            except asyncio.QueueFull:
                pass

        clear_request_context()

        # Clean up queue after a delay (give SSE time to drain)
        if job_id:
            async def cleanup():
                await asyncio.sleep(30)
                job_event_queues.pop(job_id, None)

            asyncio.create_task(cleanup())
