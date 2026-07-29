from typing import TypedDict, Annotated, Literal
from pydantic import BaseModel, Field


from langchain_core.messages import AnyMessage, SystemMessage, AIMessage
from langgraph.graph.message import add_messages
from langgraph.types import Command
from langgraph.graph import END

from src.model import build_llm


class SupervisorState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    next: str # next agent name

    current_turn_query: str # 이번 턴에 전문 agent 노드에서 사용될 질문

# Structured Output 정의
class SupervisorOutput(BaseModel):
    next: Literal["rag_agent", "news_agent", "FINISH"] = Field(
        description=(
            "다음에 호출할 에이전트 이름. "
            "경제 용어에 대하나 설명/정의가 필요하면 'rag_agent', "
            "최신 경제 뉴스나 시사 정보가 필요하면 'news_agent', "
            "더 이상 추가 검색 없이 지금까지의 정보로 답변을 마무리 할 수 있으면 'FINISH'"
        )
    )

# Supervisor Prompt
SUPERVISOR_SYSTEM_PROMPT = (
    "당신은 여러 전문 에이전트를 관리하는 supervisor입니다.\n"
    "사용 가능한 에이전트:\n"
    "- rag_agent: 경제 용어를 벡터DB에서 검색하여 정확한 설명을 제공합니다.\n"
    "- news_agent: 네이버 뉴스 검색 API로 최신 경제 뉴스를 찾아 요약과 출처 링크를 제공합니다.\n"
    "\n지금 대화에는 이전 턴들의 질문과 답변이 함께 포함되어 있을 수 있습니다.\n"
    "라우팅 판단은 반드시 '가장 최근 사용자 발화'를 기준으로 하고,\n"
    "이전 턴의 내용은 맥락을 이해하기 위한 참고 자료로만 사용하세요.\n"
    "- 용어의 뜻/정의가 궁금한 질문이면 rag_agent를 선택하세요.\n"
    "- 최신 동향, 시사, '요즘', '최근', '뉴스' 같은 표현이 담긴 질문이면 news_agent를 선택하세요.\n"
    "- 두 가지가 모두 필요한 복합 질문이면, 하나를 먼저 호출하고, 그 결과를 확인한 뒤 같은 턴 안에서 이어서 나머지 에이전트를 호출하세요.\n"
    "- 아직 질문에 답할 정보가 부족하면 적절한 에이전트를 선택하세요.\n"
    "- 충분한 정보가 모였다면 'FINISH'를 선택하세요."
)

supervisor_llm = build_llm()
structured_llm = supervisor_llm.with_structured_output(SupervisorOutput)


# Supervisor Node
def supervisor(state:SupervisorState) -> Command[Literal["rag_agent", "news_agent", "__end__"]]:# Literal[]타입은 END가 실제로 담고 있는 값을 적어야한다.
    """
    LangGraph 노드로 등록될 함수.

    Command의 update 인자에 담긴 값은 실행 후 State에 병합된다.
    """

    system_message = SystemMessage(
        content=SUPERVISOR_SYSTEM_PROMPT
    )
    # [{"role": "system", "content": SUPERVISOR_SYSTEM_PROMPT}]과 동일한가
    
    #response = structured_llm.invoke([{"role": "system", "content": SUPERVISOR_SYSTEM_PROMPT}, *state["messages"]])
    # 위의 것과 차이점은? SystemMessage화 시킨것?
    response = structured_llm.invoke([system_message, *state["messages"]])

    if response.next == "FINISH":
        # 사용자에게 보여줄 최종 답변을 마지막 메시지 기준으로 정리하고 싶다면
        # 여기서 최종 요약 LLM 호출을 한 번 더 넣을 수 있다.
        goto = END
    else:
        goto = response.next

    return Command(
        goto=goto,
        update={
            "next": response.next,
            "messages":[
                AIMessage(content=f"[supervisor] 다음 단계: {response.next}", name="supervisor")
            ],
        },
    )



# Command를 사용한 이유 : 노드 함수가 다음 어디로 갈지를 로직과 함께 한 곳에서 처리할 수 있다. = 라우팅 로직이 노드 내부에 있다.
