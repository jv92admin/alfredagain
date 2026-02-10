"""
Test script for multi-turn conversation.

Run with: python tests/test_multiturn.py
"""

import asyncio
import sys
from pathlib import Path

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from alfred.graph.workflow import run_alfred
from alfred.memory.conversation import initialize_conversation


async def test_multiturn():
    """Test a multi-turn conversation flow."""
    print("=" * 60)
    print("Multi-Turn Conversation Test")
    print("=" * 60)
    
    user_id = "00000000-0000-0000-0000-000000000001"
    
    # Initialize conversation
    conversation = initialize_conversation()
    
    # Test conversation
    turns = [
        "What's in my pantry?",
        "Add 12 eggs to my fridge",
        "What did I just add?",  # Tests reference resolution
    ]
    
    for i, message in enumerate(turns, 1):
        print(f"\n--- Turn {i} ---")
        print(f"You: {message}")
        
        try:
            response, conversation = await run_alfred(
                user_message=message,
                user_id=user_id,
                conversation=conversation,
            )
            print(f"Alfred: {response}")
            
            # Show conversation state
            print(f"\n[Context] Turns: {len(conversation.get('recent_turns', []))}")
            active = conversation.get("active_entities", {})
            if active:
                print(f"[Context] Active entities: {list(active.keys())}")
        
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("Test complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_multiturn())

