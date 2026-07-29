import os

from typing import TypedDict, Literal, Annotated

from langchain_core.documents import Document
from langchain_core.messages import AIMessage, SystemMessage, AnyMessage

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.types import Command
from langgraph.checkpoint.memory import MemorySaver

from src.agents.supervisor import SupervisorState
from src.prompts import SYSTEM_PROMPT, SYSTEM_PROMPT_LOCAL
from src.settings import settings
from src.dataset.vector_store import load_vector_store, initial_indexing, build_retriever
from src.model import build_llm

# Retriever Subgraph 전용 State
class RagState(TypedDict):
    query: str              # 공유 키
    #messages: Annotated[list[AnyMessage], add_messages] # 공유 키
    #rag agent노드에서 messages를 업데이트 하기 때문에 필요없다?

    context: list[Document]
    answer: str

def build_rag_subgraph():
    def extract_text(content) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(
                block.get("text", "") if isinstance(block, dict) else str(block)
                for block in content
            )
        return str(content)

    def format_docs(docs):
        return "\n\n".join(doc.page_content for doc in docs)


    if os.path.exists(os.path.join(settings.persist_dir, "chroma.sqlite3")):
        vectorstore = load_vector_store()
    else:
        vectorstore = initial_indexing()
    retriever = build_retriever(vectorstore)
    llm = build_llm()

    # retrieve node
    def retrieve(state: RagState) -> dict:
        query = state["query"]
        return {"context": retriever.invoke(query)}

    # generate node
    def generate(state: RagState) -> dict:

        if settings.llm_provider == "ollama":
            prompt = SYSTEM_PROMPT_LOCAL
        else:
            prompt = SYSTEM_PROMPT

        docs = state["context"]

        system_message=SystemMessage(
            content=prompt.format(context=format_docs(docs))
        )
        response = llm.invoke([system_message]) #전체 대화이력이 필요한지 확인하기
        response_text = extract_text(response)
        response.content = response_text

        return {"answer": response.content}#, "messages": [response]}

    builder = StateGraph(RagState)

    builder.add_node("retrieve", retrieve)
    builder.add_node("generate", generate)

    builder.add_edge(START, "retrieve")
    builder.add_edge("retrieve", "generate")
    builder.add_edge("generate", END)

    return builder.compile() # subgraph로 변경한 상태에서 체크포인터는 필요없다?

# Rag Agent Node (어댑터 함수 역할)
def rag_agent(state:SupervisorState) -> Command[Literal["supervisor"]]:
    # 유사도 검색 -> 리랭킹 -> 답변 생성 (서브 그래프 or 함수 호출)

    # 입력 변환: SupervisorState -> RagState
    user_query = state["current_turn_query"]
    # rag_input은 필수인가? -> user_query 값을 넘겨줘야 하니 이 경우는 필수
    rag_input = {
        "query": user_query,
        "documents":[],
        "answer": ""
    }

    rag_subgraph = build_rag_subgraph()
    result = rag_subgraph.invoke(rag_input)    # query만 넣어도 되는지 확인 필요

    return Command(
        goto="supervisor",  # supervisor로 복귀
        update={
            "messages": [
                AIMessage(content=result["answer"], name="rag_agent")
            ]
        },
    )


# ===========================================================================================================
def run_rag_pipeline(query: str) -> str:
    if os.path.exists(os.path.join(settings.persist_dir, "chroma.sqlite3")):
        vector_store = load_vector_store()
    else:
        initial_indexing()
        
    retriever = build_retriever(vector_store)
    # 유사도 검색
    candidates = retriever.invoke(query)    # List[Document]

    # 리랭킹
    reranked_docs = reranker.rerank(query=query, documents=candidates, top_n=3)

    # 컨텍스트 구성 및 답변 생성
    context = "\n\n".join(doc.page_content for doc in reranked_docs)
    prompt = (
        "다음 문서만을 근거로 사용자 질문에 답하세요.\n"
        "답변 후 반드시 '[출처] '라는 표시와 함께 참고한 문서의 파일명과 pdf문서의 경우에는 출처 페이지를 나열하세요.\n"
        "여러 문서나 페이지를 참고했다면 모두 나열하세요.\n"
        "근거가 부족하면 '주어진 자료에서는 확인할 수 없습니다.'라고 답하세요.\n\n"
        "{context}"
    )
    answer = answer_llm.invoke(prompt)
    return answer.content


# ===== 기존 함수 
def build_rag_graph():
    if os.path.exists(os.path.join(settings.persist_dir, "chroma.sqlite3")):
        vector_store = load_vector_store()
    else:
        initial_indexing()
        
    retriever = build_retriever(vector_store)
    
    llm = build_llm()
    
    if settings.llm_provider == "ollama":
        prompt = SYSTEM_PROMPT_LOCAL
    else:
        prompt = SYSTEM_PROMPT

    def format_docs(docs):# 여러 개의 Document 객체를 하나의 긴 문자열로 합친다.
        return "\n\n".join(doc.page_content for doc in docs)    # 서로 다른 문서에서 온 내용임을 표시하기 위해 \n\n 사용
    
    def format_docs_src(docs):  # 출처가 포함된 context로 만들어준다.
        return "\n\n".join( # 출처를 받아오는데 경로 전체가 오기 때문에, Path객체로 변환 후 파일명만 추출한다.
            f"[source: {Path(doc.metadata.get('source', 'unknown')).name}]\n{doc.page_content}" for doc in docs
        )
    
    def extract_text(content) -> str:
        # gemini 모델이 응답을 content block으로 반환하기 때문에 llm provider에 구애받지 않고 content를 일관된 문자열로 통일
        if isinstance(content, str):    #이미 str이라면 그대로 반환
            return content
        if isinstance(content, list):
            return "".join(
                block.get("text", "") if isinstance(block, dict) else str(block)
                for block in content
            )
        return str(content) #예상 밖의 형태라면 str로 강제로 변환 : 방어선 코드
    
    # 이것을 도구화?
    def retrieve(state: State):
        question = state["messages"][-1].content        #대화 이력 중 가장 최신 메시지를 질문으로 설정해서 검색기에 넣는다.
        return {"context": retriever.invoke(question)}  #검색 결과(Document 리스트)를 context에 담아서 반환한다.

    def generate(state: State):
        docs = state["context"]
        #검색된 문서들을 하나의 문자열로 합쳐서(format_docs), 시스템 프롬프트의 {context}로 끼워넣는다.
        system_message = SystemMessage( # SystemMessage : 모델의 행동 방식, 페르소나, 규칙을 지정한다. 대화 전체에 일관되게 적용할 지시를 넣는다.
            content=prompt.format(context=format_docs(docs)) # .format 은 순수 문자열 반환
        )
        # 시스템 메시지 + 전체 대화 이력을 LLM에 넣어 응답 생성. (멀티턴 대화 맥락 유지)
        # 전체 대화 이력: 리스트 그대로가 아닌 리스트 안의 요소들을 하나씩 풀어서 넣는다 (unpacking) # [system_message, HumanMessage("질문1"), AIMessage("답변1"), HumanMessage("질문2")]
        response = llm.invoke([system_message, *state["messages"]])

        # 어떤 응답이든 str로 변환하기, llm provider에 구애받지 않고 content를 일관된 문자열로 통일
        response_text = extract_text(response.content)

        if settings.llm_provider == "ollama":
            # 출처 직접 추가
            
            if settings.doc_source == "pdf":
                sources = sorted(set(
                doc.metadata.get('page','unknown') for doc in docs
                ))
                source_text = "\n\n[출처] " + ",".join(f"{p} 페이지" for p in sources) #[출처] 모든 출처 페이지들 연결
                #print(source_text)
            else:
                sources = sorted(set(
                Path(doc.metadata.get('source','unknown')).name for doc in docs
                ))
                source_text = "\n\n[출처] " + ",".join(sources) # [출처] 모든 출처 파일명들 연결
            
            response_text += source_text    # response_text의 맨 마지막에 source_text 추가
            #print(response_text)


        response.content = response_text
        return {"messages": [response]} # 새로 생성된 응답 메시지 하나만 반환하면, reducer가 자동으로 기존 이력 "뒤"에 append
    
    builder = StateGraph(State)
    builder.add_node("retrieve", retrieve)
    builder.add_node("generate", generate)

    builder.add_edge(START, "retrieve")
    builder.add_edge("retrieve", "generate")
    builder.add_edge("generate", END)

    return builder.compile(checkpointer=MemorySaver())  # 그래프 컴파일 시 체크포인터 연결


