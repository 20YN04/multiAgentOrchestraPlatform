from __future__ import annotations

from langchain_core.messages import HumanMessage

from multi_agent.graph import build_two_agent_graph
from multi_agent.state import AgentName, ExecutionState


def run_task(task: str) -> ExecutionState:
    graph = build_two_agent_graph()
    initial_state: ExecutionState = {
        "messages": [HumanMessage(content=task)],
        "active_agent": AgentName.RESEARCHER.value,
    }
    return graph.invoke(initial_state)


if __name__ == "__main__":
    result = run_task("Design and implement a robust REST API error-handling strategy.")

    print("Final active agent:", result["active_agent"])
    print("\nConversation transcript:\n")
    for idx, message in enumerate(result["messages"], start=1):
        role = getattr(message, "name", message.__class__.__name__)
        print(f"[{idx}] {role}:\n{message.content}\n")