"""
Alfred V2 - Graph Nodes.

Nodes:
- router: Classify intent, pick agent, set complexity
- think: Domain-specific planning, generate steps
- act: Execute steps via tools
- reply: Synthesize final response
"""

from alfred.graph.nodes.act import act_node, should_continue_act
from alfred.graph.nodes.reply import reply_node
from alfred.graph.nodes.router import router_node
from alfred.graph.nodes.think import think_node

__all__ = [
    "router_node",
    "think_node",
    "act_node",
    "reply_node",
    "should_continue_act",
]
