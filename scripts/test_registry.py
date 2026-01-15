#!/usr/bin/env python
"""Test registry persistence. Run with: alfred test-registry"""

import asyncio
import sys
from pathlib import Path

# Add src to path BEFORE any imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

async def main():
    # Import inside function to avoid module-level issues
    from alfred.graph.workflow import run_alfred
    from alfred.memory.conversation import initialize_conversation
    from alfred.config import settings
    
    user_id = settings.dev_user_id
    conv = initialize_conversation()
    
    print("\n=== TURN 1: Reading inventory ===")
    resp, conv = await run_alfred("whats in my inventory", user_id, conversation=conv)
    print(f"Response: {resp[:80]}...")
    
    # Check registry after Turn 1
    reg = conv.get("id_registry")
    if reg:
        count = len(reg.get("ref_to_uuid", {}))
        print(f"\n✅ After Turn 1: Registry has {count} entities")
        if count > 0:
            refs = list(reg.get("ref_to_uuid", {}).keys())[:5]
            print(f"   Sample refs: {refs}")
    else:
        print("\n❌ After Turn 1: NO REGISTRY!")
    
    print("\n=== TURN 2: Asking about recipes ===")
    resp2, conv2 = await run_alfred("any recipes?", user_id, conversation=conv)
    print(f"Response: {resp2[:80]}...")
    
    reg2 = conv2.get("id_registry")
    if reg2:
        count2 = len(reg2.get("ref_to_uuid", {}))
        print(f"\n✅ After Turn 2: Registry has {count2} entities")
    else:
        print("\n❌ After Turn 2: NO REGISTRY!")

if __name__ == "__main__":
    asyncio.run(main())
