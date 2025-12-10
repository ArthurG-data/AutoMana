from langgraph.graph import StateGraph, MessagesState, START, END
from graph_state import State
from graph_nodes import chatbot, tool_node
from langgraph.prebuilt import tools_condition

graph_builder = StateGraph(State)

graph_builder.add_node("chatbot", chatbot)
graph_builder.add_node("tools", tool_node)
graph_builder.add_conditional_edges(
    "chatbot",
    tools_condition
)
graph_builder.add_edge("tools", "chatbot")
graph_builder.set_entry_point("chatbot")