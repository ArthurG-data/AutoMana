from build_graph import  graph_builder
from langgraph.checkpoint.memory import MemorySaver

#enable memory to save the state of the graph
memory = MemorySaver()

graph = graph_builder.compile(
    checkpointer=memory,
    #human in the loop
    interrupt_before=["tools"]
    #could be after
    )



from IPython.display import Image, display

try:
    display(Image(graph.get_graph().draw_mermaid_png()))
except Exception:
    # This requires some extra dependencies and is optional
    pass





def main():

    config = {"configurable": {"thread_id": "1"}}

    while True:
        user_input = input("User: ")
        if user_input.lower() in ["quit", "exit", "q"]:
            print("Goodbye!")
            break

        # Process user input through the LangGraph
        for event in graph.stream({"messages": [("user", user_input)]}, config):
            for value in event.values():
                if isinstance(value, dict) and "messages" in value:
                    print("Assistant:", value["messages"][-1].content)
                else:
                    print("Event:", value)
        #check if graph is interrupted, waiting for human in the loop
        snapshot = graph.get_state(config)

        if snapshot.next:
            print("\n--- Tool calls pending ---")
            # Show what tools are about to be called
            last_message = snapshot.values["messages"][-1]
            if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
                for tool_call in last_message.tool_calls:
                    print(f"Tool: {tool_call['name']}")
                    print(f"Args: {tool_call['args']}")
            approval = input("\nApprove tool calls? (y/n): ")
            if approval.lower() == "y":
                for event in graph.stream(None, config):
                    for value in event.values():
                        if isinstance(value, dict) and "messages" in value:
                            print("Assistant:", value["messages"][-1].content)
            else:
                print("Tool calls rejected. Continuing...")
                #need a message to continue
                from langchain_core.messages import ToolMessage
                tool_messages = []
                last_message = snapshot.values["messages"][-1]
                if hasattr(last_message, "tool_calls") and last_message.tool_calls:
                    for tool_call in last_message.tool_calls:
                        tool_messages.append(
                            ToolMessage(
                                content="Tool call rejected by user.",
                                tool_call_id=tool_call['id']
                            )
            )
                graph.update_state(config, {"messages": tool_messages})

                # Ask the model to respond without using tools
                for event in graph.stream(None, config):
                    for value in event.values():
                        if isinstance(value, dict) and "messages" in value:
                            print("Assistant:", value["messages"][-1].content)


        

if __name__ == "__main__":
    main()

