import time, datetime

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from src.agents.supervisor import SupervisorState, supervisor
from src.agents.rag_agent import rag_subgraph
from src.agents.news_agent import news_subgraph
from src.utils import print_messages

QUERY_SYSTEM_PROMPT = (
    "당신은 대화 이력을 참고하여 사용자의 가장 최근 메시지를"
    "'그 자체만으로도 의미가 통하는 독립적인 질문'으로 다시 작성하는 역할을 합니다.\n"
    "규칙:\n"
    "- 이미 그 자체로 독립적인 질문이면 그대로 반환하세요."
    "- 대화 이력에 있는 대명사, 생략된 주어/목적어를 명시적으로 채워 넣으세요.\n"
    "(예시: '그거 반댓말은?' -> '인플레이션의 반댓말인 디플레이션이란 무엇인가?')"
    "- 질문의 의도를 바꾸지 말고, 검색에 사용하기 좋은 형태로만 다듬으세요."
)

#rewrite_llm = build_llm(name="Prepare Query", provider="ollama")

def prepare_query(state:SupervisorState) -> dict:
    print(f"==== [DEBUG][SAVE ORIGINAL QUERY] ====")
    print_messages("prepare_query 진입", state["messages"])
    latest_user_message = state["messages"][-1].content

    return {"query": latest_user_message, "rag_agent_calls": 0, "news_agent_calls":0}


def build_multi_agent_graph():
    builder = StateGraph(SupervisorState)

    builder.add_node("prepare_query", prepare_query)
    builder.add_node("supervisor", supervisor)
    builder.add_node("rag_agent", rag_subgraph)    #subgraph
    builder.add_node("news_agent", news_subgraph)   #subgraph

    # 그래프 진입점
    builder.add_edge(START, "prepare_query")
    builder.add_edge("prepare_query", "supervisor")

    builder.add_edge("rag_agent", "supervisor")
    #builder.add_edge("news_agent", END) # 임시로 한번만 테스트 하기 위해
    builder.add_edge("news_agent", "supervisor")

    return builder.compile(checkpointer=MemorySaver())