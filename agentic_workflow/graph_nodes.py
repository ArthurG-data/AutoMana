from typing import Dict, Any
from langchain_core.messages import HumanMessage, AIMessage
from graph_state import AgentState, State
from langgraph.prebuilt import ToolNode
from llm_setup import llm_with_tools, TOOLS
"""
def decide_task_node(state : AgentState) -> AgentState:
   
"""

def chatbot(state : State):
    response = llm_with_tools.invoke(state["messages"])

    """return the updates message"""

    return {"messages" : [response]}

tool_node = ToolNode(TOOLS)

