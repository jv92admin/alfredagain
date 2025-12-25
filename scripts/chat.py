#!/usr/bin/env python
"""
Simple chat script for testing Alfred multi-turn conversation.

Usage:
    python scripts/chat.py
    
Or with logging:
    python scripts/chat.py --verbose
"""

import asyncio
import logging
import sys
from pathlib import Path

# Fix Windows encoding
if sys.platform == "win32":
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, errors='replace')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, errors='replace')

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def setup_logging(verbose: bool = False):
    """Setup logging with visible output."""
    level = logging.DEBUG if verbose else logging.INFO
    
    # Format that shows node progress
    fmt = "%(asctime)s [%(name)s] %(message)s"
    datefmt = "%H:%M:%S"
    
    logging.basicConfig(
        level=level,
        format=fmt,
        datefmt=datefmt,
        handlers=[logging.StreamHandler(sys.stderr)]
    )
    
    # Quiet down noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)


async def chat_loop(verbose: bool = False):
    """Main chat loop."""
    from alfred.graph.workflow import run_alfred
    from alfred.memory.conversation import initialize_conversation
    from alfred.config import settings
    
    logger = logging.getLogger("chat")
    
    print("=" * 60)
    print("Alfred V2 - Multi-Turn Chat")
    print("=" * 60)
    print("Commands: 'exit' to quit, 'context' to see state")
    print("-" * 60)
    
    user_id = settings.dev_user_id
    conversation = initialize_conversation()
    turn_count = 0
    
    while True:
        try:
            # Get input
            print()
            user_input = input("You: ").strip()
            
            if not user_input:
                continue
                
            if user_input.lower() in ("exit", "quit", "q"):
                print("\nGoodbye!")
                break
            
            if user_input.lower() == "context":
                show_context(conversation, turn_count)
                continue
            
            # Process message
            logger.info(f"Processing: {user_input[:50]}...")
            
            response, conversation = await run_alfred(
                user_message=user_input,
                user_id=user_id,
                conversation=conversation,
            )
            
            turn_count += 1
            
            # Show response
            print(f"\nAlfred: {response}")
            
            # Quick context summary
            active = conversation.get("active_entities", {})
            if active:
                entities = ", ".join(active.keys())
                logger.debug(f"Active entities: {entities}")
            
        except KeyboardInterrupt:
            print("\n\nInterrupted. Goodbye!")
            break
        except Exception as e:
            logger.exception(f"Error: {e}")
            print(f"\n[Error] {e}")


def show_context(conversation: dict, turn_count: int):
    """Show conversation context."""
    print("\n--- Conversation Context ---")
    print(f"Turns: {turn_count}")
    
    # Engagement
    engagement = conversation.get("engagement_summary", "")
    if engagement:
        print(f"Session: {engagement}")
    
    # Active entities
    active = conversation.get("active_entities", {})
    if active:
        print("Active entities:")
        for etype, edata in active.items():
            print(f"  - {etype}: {edata.get('label', '?')}")
    
    # Recent turns
    recent = conversation.get("recent_turns", [])
    if recent:
        print(f"Recent turns: {len(recent)}")
        for t in recent[-2:]:
            user = t.get("user", "")[:40]
            print(f"  You: {user}...")
    
    # History
    history = conversation.get("history_summary", "")
    if history:
        print(f"History: {history[:100]}...")
    
    print("----------------------------\n")


def main():
    """Entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Alfred chat")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show debug logging")
    args = parser.parse_args()
    
    setup_logging(args.verbose)
    asyncio.run(chat_loop(args.verbose))


if __name__ == "__main__":
    main()

