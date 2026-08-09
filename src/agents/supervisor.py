import time

from typing import TypedDict, Annotated, Literal
from pydantic import BaseModel, Field

from langchain_core.messages import AnyMessage, SystemMessage, AIMessage
from langgraph.graph.message import add_messages
from langgraph.types import Command
from langgraph.graph import END

from src.model import build_supervisor_llm
from src.utils import format_elapsed, extract_text, print_messages

# 어떤 에이전트의 답변인지 표시
AGENT_LABELS = {
    "rag_agent": "용어 설명",
    "news_agent": "관련 뉴스",
    "fallback_answer": "기타 답변",
}
# 에이전트 호출 수 한도
MAX_AGENT_CALLS = {
    "rag_agent": 1,
    "news_agent": 1,
}

class SupervisorState(TypedDict):
    # 공유 키
    query: str # 이번 턴에 사용될 오리지널 쿼리
    messages: Annotated[list[AnyMessage], add_messages]

    # 비공유 키
    next: str # next agent name
    rag_agent_calls: int
    news_agent_calls: int
    

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

    # next가 "FINISH"일 때만 최종 답변을 생성한다.
    # FINISH가 아니라면 이 필드는 비워둔다.
    # final_answer: Optional[str] = Field(
    #     default=None,
    #     description=(
    #         "next가 'FINISH'일 때만 작성한다. "
    #         "지금까지 각 에이전트가 만든 답변들을 종합하여 사용자에게 보여줄 자연스러운 최종 답변. "
    #         "[출처] 표시가 있는 답변이 들어있다면 해당 출처를 꼭 표현하도록 할 것. "
    #         "출처는 맨 마지막에 한 줄 띄어쓰고 적도록 할 것. "
    #         "'rag_agent에 따르면' 같은 내부 구현 용어는 절대 쓰지 말 것. "
    #         "next가 'FINISH'가 아니면 null로 둔다."
    #     )
    # )


supervisor_llm = build_supervisor_llm()
structured_llm = supervisor_llm.with_structured_output(SupervisorOutput)

# 잡담 응답 생성
def _fallback_answer(state: SupervisorState) -> str:
    print(f"\n==================================[DEBUG][SUPERVISOR][FALLBACK ANSWER]==================================")
    print_messages("supervisor(fallback answer) 진입", state["messages"])

    SYSTEM_PROMPT = """\
    당신은 경제 용어 검색과 경제 뉴스 검색을 할 수 있는 어시스턴트입니다.
    두 가지 작업만이 가능하다는 것을 명심하세요.
    답변은 자연스럽고 짧게 존댓말로 대답하세요.
    만약 지금까지의 대화에서 검색을 시도했지만 관련 정보를 찾지 못한 상황이라면,
    그 검색을 시도했지만 정보를 찾지 못했다고 솔직하고 간결하게 안내하세요.
    """
    system_message = SystemMessage(
        content=SYSTEM_PROMPT
    )
    response = supervisor_llm.invoke(
        [system_message, *state["messages"]],
        config={"tags": ["fallback_answer"]}
    )  #사용자 발화만 들어가게됨

    # 스트리밍을 위해 반드시 필요
    response_text = extract_text(response.content)
    return response_text

def _agent_results_summary(state: SupervisorState) -> tuple[bool, bool]:
    """
    called_any : 에이전트 호출이 있었는지
    found_any : 결과를 찾은게 있는지
    """
    called_any = False
    found_any = False
    for m in state["messages"]:
        if getattr(m, "name", None) in AGENT_LABELS:
            called_any= True
            if m.additional_kwargs.get("found_results"):
                found_any=True
    return called_any, found_any


# Supervisor Node
def supervisor(state:SupervisorState) -> Command[Literal["rag_agent", "news_agent", "__end__"]]:# Literal[]타입은 END가 실제로 담고 있는 값을 적어야한다.
    """
    다음으로 부를 Agent를 결정하고 Agent로부터 얻은 답변을 바탕으로 최종 답변을 생성하는 Supervisor.
    Command의 update 인자에 담긴 값은 실행 후 State에 병합된다.
    """
    print(f"\n================================== [DEBUG][SUPERVISOR] ==================================n")
    st_time = time.time()

    # agent 호출 한도 도달했는지 판단
    rag_maxed = state["rag_agent_calls"] >= MAX_AGENT_CALLS["rag_agent"]
    news_maxed = state["news_agent_calls"] >= MAX_AGENT_CALLS["news_agent"]

    # Supervisor Prompt
    SUPERVISOR_SYSTEM_PROMPT = """\
    당신은 사용자의 요청을 보고 다음으로 불러올 에이전트를 결정하는 supervisor입니다.
    사용 가능한 에이전트:
    - rag_agent: 경제 용어를 벡터DB에서 검색하여 정의 또는 설명을 제공합니다.
    - news_agent: 네이버 뉴스 검색 API로 최신 경제 뉴스 또는 시사 동향을 찾아 요약합니다.

    지금 대화에는 이전 턴들의 질문과 답변이 함께 포함되어 있을 수 있습니다.
    라우팅 판단은 반드시 '가장 최근 사용자 발화'를 기준으로 하고,
    이전 턴의 내용은 맥락을 이해하기 위한 참고 자료로만 사용하세요.

    - 용어의 뜻/정의가 궁금한 질문이면 rag_agent를 선택하세요.
    - '최신 동향', '시사', '요즘', '최근', '뉴스' 같은 표현이 담긴 질문이면 news_agent를 선택하세요.
    - 두 가지가 모두 필요한 복합 질문이면, 하나를 먼저 호출하고, 그 결과를 확인한 뒤 같은 턴 안에서 이어서 나머지 에이전트를 호출하세요.
    - 아직 질문에 답할 정보가 부족하면 적절한 에이전트를 선택하세요.
    - 충분한 정보가 모였다면 next를 'FINISH'로 선택하세요.
    """
    # 하고, 동시에 final_answer에 지금까지의 에이전트 답변들을 종합한 최종 답변을 작성하세요.
    # - rag_agent로부터 정보를 얻었다면 [출처]를 남기도록하고, news_agent로부터 뉴스 정보를 얻어왔다면 출처 링크를 제공하세요.
    # - 만약 agent로부터 주어진 자료에서부터 확인할 수 없다는 답변을 받으면 최종답변에도 똑같이 주어진 자료에서 확인할 수 었다고 답변하세요.
    # - 다만 rag_agent/news_agent를 한 번도 호출하지 않고 곧바로 'FINISH'하는 경우라면 final_answer에 정보가 없어 답변할 수 없음을 안내하세요.
    
    # 동적인 Supervisor 프롬프트 설정 (agent 호출 최대로 도달하면 중요 제약 전달)
    constraint_notes = []
    if rag_maxed:
        constraint_notes.append(
            f"- rag_agent는 이미 이번 턴에 {MAX_AGENT_CALLS["rag_agent"]}회 호출되어 더 이상 선택할 수 없습니다."
        )
    if news_maxed:
        constraint_notes.append(
            f"- news_agent는 이미 이번 턴에 {MAX_AGENT_CALLS["news_agent"]}회 호출되어 더 이상 선택할 수 없습니다."
        )
    if constraint_notes:
        SUPERVISOR_SYSTEM_PROMPT +="\n\n[중요 제약]\n"+"\n".join(constraint_notes)


    system_message = SystemMessage(
        content=SUPERVISOR_SYSTEM_PROMPT
    )

    decision = structured_llm.invoke([system_message, *state["messages"]])
    print(f"\n[SUPERVISOR][NEXT] {decision.next}\n")

    # 재검증 (방어코드) ===================
    if decision.next == "rag_agent" and rag_maxed:
        print("[SUPERVISOR] rag_agent 한도 초과, LLM이 지침을 무시함 -> FINISH로 강제 전환\n")
        decision.next = "FINISH"
    elif decision.next == "news_agent" and news_maxed:
        print("[SUPERVISOR] news_agent 한도 초과, LLM이 지침을 무시함 -> FINISH로 강제 전환\n")
        decision.next = "FINISH"
    # ===========================

    # ==== 시간 측정 ====
    cost_time = format_elapsed(st_time)
    print(f"\n[TIME] Supervisor : {cost_time}\n")
    # ===========================
    if decision.next == "FINISH":
        # 사용자에게 보여줄 최종 답변을 마지막 메시지 기준으로 정리하고 싶다면
        # 여기서 최종 요약 LLM 호출을 한 번 더 넣을 수 있다.
        # 에이전트가 한번도 호출되지 않아서 빈 문자열이라면 잡담 응답 처리. e.g.,요청하신 질문에 답할 수 없습니다. 등
        print(f" ================================== [DEBUG][SUPERVISOR][FINISH] ================================== ")
        print(f"[DEBUG][SUPERVISOR][FINISH] rag_agent called {state["rag_agent_calls"]} times")
        print(f"[DEBUG][SUPERVISOR][FINISH] news_agent called {state["news_agent_calls"]} times\n")
          
        called_any, found_any = _agent_results_summary(state)

        # 스트리밍을 위해 not called_any와 not found_any 모두 fallback_answer로 넘김
        if not called_any or not found_any:
            print("[SUPERVISOR]잡담 또는 정보 없음 -> _fallback_answer 사용")
            fallback_answer = _fallback_answer(state)

            update={
                "next": decision.next,
                "messages": [AIMessage(content=fallback_answer, name= "Supervisor")]
            }

        else: # 제대로된 FINISH (에이전트 호출하였고 응답 얻음)
            update ={
                "next": decision.next,
            }
        
        return Command(
            goto=END,
            update=update
        )

    elif decision.next == "rag_agent":
        update = {
            "next": decision.next,
            "rag_agent_calls": state["rag_agent_calls"] + 1,
        }
        print(f"[DEBUG][SUPERVISOR] rag_agent called {update["rag_agent_calls"]} times")
            
    elif decision.next == "news_agent":
        update = {
            "next": decision.next,
            "news_agent_calls": state["news_agent_calls"] + 1,
        }
        print(f"[DEBUG][SUPERVISOR] news_agent called {update["news_agent_calls"]} times")

    return Command(
        goto=decision.next,
        update=update
    )



# Command를 사용한 이유 : 노드 함수가 다음 어디로 갈지를 로직과 함께 한 곳에서 처리할 수 있다. = 라우팅 로직이 노드 내부에 있다.
