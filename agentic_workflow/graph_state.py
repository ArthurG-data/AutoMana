
import operator
from typing import TypedDict, Annotated, List, Literal, Dict, Any
from langgraph.graph.message import add_messages
"""LLM Setup for Agentic Workflows"""

#agent to ccreate a llisting
class AgentState(TypedDict, total=False):
    messages : Annotated[List[Dict[str, Any]], operator.add]
    task: Literal["create_listing"]


class State(TypedDict):
    """ 'messages will store the conversation history '"""
    """ 'add_message ensures new messages are added at the end'"""
    messages : Annotated[list, add_messages]