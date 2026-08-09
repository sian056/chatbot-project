import os, time, datetime

from typing import TypedDict, Annotated

from langchain_core.documents import Document
from langchain_core.messages import AIMessage, SystemMessage, HumanMessage, AnyMessage

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.types import Command

from src.settings import settings
from src.dataset.vector_store import load_vector_store, initial_indexing, build_retriever
from src.model import build_llm
from src.utils import extract_text, format_elapsed, print_messages

_rewrite_llm = build_llm(name="RAG Rewrite", provider=settings.rag_rewrite_provider)
_generate_llm = build_llm(name="RAG Agent", provider=settings.rag_generate_provider)

if os.path.exists(os.path.join(settings.persist_dir, "chroma.sqlite3")):
    vectorstore = load_vector_store()
else:
    vectorstore = initial_indexing()

retriever = build_retriever(vectorstore)

# Retriever Subgraph 전용 State
class RagState(TypedDict):
    # 공유 키
    query: str
    messages: Annotated[list[AnyMessage], add_messages]

    # 비공유 키
    context: list[Document]
    answer: str
    search_query: str       # RAG 문서 검색용 재작성된 쿼리
    sources: list[dict]

def format_docs(docs):
    return "\n\n".join(doc.page_content for doc in docs)

def rewrite_query(state: RagState) -> dict:
    print(f"\n================================== [DEBUG][RAG][REWRITE] ==================================n")
    st_time = time.time()

    SYSTEM_PROMPT_QUERY = (
        "당신은 사용자의 요청에서 '경제 용어의 정의나 개념 설명'과 관련된 부분만 뽑아,"
        "벡터DB 검색에 적합한 독립적인 검색 쿼리로 재작성하는 역할을 합니다.\n"
        "규칙:\n"
        "- 이미 그 자체로 독립적인 질문(예를 들어, 용어 설명에 대한 단일 질문)이면 그대로 반환하세요.\n"
        "- 대화 이력을 바탕으로 사용자의 요청에 있는 대명사, 생략된 주어/목적어를 명시적으로 채워 넣으세요.\n"
        "(예시: '그거 반댓말은?' -> '인플레이션의 반댓말은?')\n"
        "- 사용자의 요청이 여러 요구사항을 담은 복합 질문이라면,"
        "그중 '용어의 뜻/정의/개념 설명'에 해당하는 부분의 질문만 뽑아내세요.\n"
        "뉴스, 최신 동향, 시사성 요청 부분은 완전히 무시하고 포함하지 마세요.\n"
        "(예시: '금리와 관련된 용어 설명과 뉴스 검색' -> '금리란 무엇인가')\n"
        "- 검색 쿼리는 간결하게 작성하세요."
    )

    query = state["query"]  # 질문자의 오리지널 쿼리
    print(f"[DEBUG][RAG][REWRITE][ORIGINAL QUERY] {query}")
    
    # 마지막 메시지(질문자의 오리지널 쿼리) 제외한 대화 이력
    history = state["messages"][:-1]

    rewritten_query = _rewrite_llm.invoke([
        {"role": "system", "content": SYSTEM_PROMPT_QUERY},
        *history,
        {"role": "user", "content": f"다시 써야 할 질문: {query}"}
    ])

    rewritten_content = extract_text(rewritten_query.content)

    # Rewritten query가 만약 비어있다면
    if not rewritten_content:
        print(f"[DEBUG][RAG][REWRITE] 빈값 반환 -> 원본 쿼리 사용")
        rewritten_content = query
    else:
        print(f"[DEBUG][RAG][REWRITE][REWRITTEN QUERY]{rewritten_content}")
        

    cost_time = format_elapsed(st_time)
    print(f"\n[TIME][RAG][REWRITE] {cost_time}\n")

    return {"search_query": rewritten_content}

# retrieve node
def retrieve(state: RagState) -> dict:
    print(f"\n================================== [DEBUG][RAG][RETRIEVE] ==================================n")
    st_time = time.time()

    query = state["search_query"]
    contexts = retriever.invoke(query)
    print(f"[DEBUG][RAG][RETRIEVE][CONTEXT]")
    for context in contexts:
        print(f"Page Label : {context.metadata.get('page_label','unknown')}")

    cost_time = format_elapsed(st_time)
    print(f"\n[TIME][RAG][RETRIEVE] {cost_time}\n")

    return {"context": contexts}

# generate node
def generate(state: RagState) -> dict:
    print(f"\n================================== [DEBUG][RAG][GENERATE] ==================================n")
    print_messages("rag_agent.generate 진입", state["messages"])
    st_time = time.time()

    docs = state["context"]

    prompt = (
        "다음의 검색된 문서만을 근거로 사용자 질문에 간결히 답하세요.\n"
        "근거가 부족하면 '주어진 자료에서는 확인할 수 없습니다.'라고 답하세요.\n\n"
        "[검색된 문서]\n{context}"
    )
    system_message=SystemMessage(
        content=prompt.format(context=format_docs(docs))
    )
    # RAG용 Rewritten query
    human_message = HumanMessage(content=state["search_query"])

    # 디버그용
    # messages_to_send = [system_message, human_message]
    # print(f"[DEBUG][RAG][GENERATE] 전송 메시지 개수: {len(messages_to_send)}")
    # for m in messages_to_send:
    #     print(f"  - {type(m).__name__}: {m.content[:50]!r}")

    # 1. 전체 대화이력을 넘겨주는 경우 ===========
    #response = _generate_llm.invoke([system_message, *state["messages"]]) #전체 대화이력이 필요한지 확인하기
    # ================================


    # 2. 오리지널 쿼리 질문을 제외하고 넘겨주는 경우 ============
    # history = state["messages"][:-1]

    # # print(f"[DEBUG][MESSAGES][최신 쿼리 제외]")
    # # for i,m in enumerate(history):
    # #     print(f"    [{i}] {type(m).__name__}: {m.content[:40]}")
    
    # response = _generate_llm.invoke(
    #     [system_message, 
    #      *history,
    #     ]
    # )
    # ==================================

    # 3. 대화 이력을 넘겨주지 않는 경우 (Rewritten 된 쿼리만 보고 답변 생성한다.)
    #(프롬프트와 Rewritten된 질문 쿼리인 HumanMessage만 보고 답한다)
    response = _generate_llm.invoke([system_message, human_message]) 

    # 답변을 str으로 변환
    response_text = extract_text(response.content)
    print(f"[DEBUG][RAG][GENERATE][RESPONSE]\n{response_text}")
    # ==================================

    # ======== 디버그용 스트리밍 토큰 확인
    # chunks = []
    # for chunk in _generate_llm.stream([system_message, human_message]):
    #     text_piece = extract_text(chunk.content)   # 각 청크의 content만 추출
    #     print(f"[DEBUG][GENERATE-STREAM] {chunk.content!r}")
    #     chunks.append(text_piece)

    # response_text = "".join(chunks)   # 여기서 바로 최종 텍스트 완성
    # ==================================

    # 출처 출력을 위해
    page_sources_stream = sorted(set(
        doc.metadata.get("page_label", "unknown") for doc in docs
    ))
    print(f"[DEBUG] page_sources_stream = {page_sources_stream}")

    page_src_stream = [{"page_label": p} for p in page_sources_stream]

    cost_time = format_elapsed(st_time)
    print(f"\n[TIME][RAG][GENERATE] {cost_time}\n")

    return {
        "answer": response_text,    # 출처 없는 답변
        "sources": page_src_stream, # updates 모드에서 이 값을 읽는다 (출처 표시를 위해 필요)
        "messages": [
            AIMessage(
                content=response_text,  # 출처 없는 답변
                name="rag_agent",
                additional_kwargs={
                    "found_results":bool(docs),     # 검색된 문서 존재 여부
                    "sources": page_src_stream,     # 기록용으로 메시지에 출처를 남긴다.
                },
            )
        ]
    }

def _build_rag_subgraph():
    builder = StateGraph(RagState)

    builder.add_node("rewrite_query", rewrite_query)
    builder.add_node("retrieve", retrieve)
    builder.add_node("generate", generate)

    builder.add_edge(START, "rewrite_query")
    builder.add_edge("rewrite_query", "retrieve")
    builder.add_edge("retrieve", "generate")
    builder.add_edge("generate", END)

    return builder.compile() # subgraph는 체크포인터 필요없다

rag_subgraph = _build_rag_subgraph()