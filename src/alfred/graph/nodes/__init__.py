"""
Alfred V3 - Graph Nodes.

Nodes:
- router: Classify intent, pick agent, set complexity
- understand: Entity state updates and reference resolution (V3)
- think: Domain-specific planning, generate steps with groups
- act: Execute steps via tools
- act_quick: Quick mode single-call execution (Phase 3)
- reply: Synthesize final response
- summarize: Maintain conversation memory and entity lifecycle
"""

from alfred.graph.nodes.act import act_node, act_quick_node, should_continue_act
from alfred.graph.nodes.reply import reply_node
from alfred.graph.nodes.router import router_node
from alfred.graph.nodes.summarize import summarize_node
from alfred.graph.nodes.think import think_node
from alfred.graph.nodes.understand import understand_node

__all__ = [
    "router_node",
    "understand_node",  # V3
    "think_node",
    "act_node",
    "act_quick_node",  # Phase 3
    "reply_node",
    "summarize_node",
    "should_continue_act",
]
