# src/rag/graph.py
import os

from typing import TypedDict, Annotated
from pathlib import Path

from langchain_core.documents import Document
from langchain_core.messages import SystemMessage, AnyMessage
from langchain_core.tools import tool

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver

from src.prompts import SYSTEM_PROMPT, SYSTEM_PROMPT_LOCAL
from src.dataset.vector_store import build_retriever, load_vector_store, initial_indexing
from src.model import build_llm
from src.settings import settings


# MessagesState 을 이용하지 않은 것은 context가 필요해서?
class State(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages] # add_messages: reducer- 자동으로 리스트에 새로운 메시지를 append
    context: list[Document] #reducer가 없으므로 노드가 반환하는 값으로 덮어쓰기된다. 매 질문마다 새로 검색한 문서로 교체


def build_rag_graph():
    if os.path.exists(os.path.join(settings.persist_dir, "chroma.sqlite3")):
        vector_store = load_vector_store()
    else:
        initial_indexing()
        
    retriever = build_retriever(vector_store)
    
    llm = build_llm()

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
        if settings.llm_provider == "ollama":
            prompt = SYSTEM_PROMPT_LOCAL
        else:
            prompt = SYSTEM_PROMPT
            
        docs = state["context"]
        #검색된 문서들을 하나의 문자열로 합쳐서(format_docs), 시스템 프롬프트의 {context}로 끼워넣는다.
        system_message = SystemMessage( # SystemMessage : 모델의 행동 방식, 페르소나, 규칙을 지정한다. 대화 전체에 일관되게 적용할 지시를 넣는다.
            content=prompt.format(context=format_docs(docs)) # .format 은 순수 문자열 반환
        )
        # 시스템 메시지 + 전체 대화 이력을 LLM에 넣어 응답 생성. (멀티턴 대화 맥락 유지)
        # 전체 대화 이력: 리스트 그대로가 아닌 리스트 안의 요소들을 하나씩 풀어서 넣는다 (unpacking) # [system_message, HumanMessage("질문1"), AIMessage("답변1"), HumanMessage("질문2")]
        response = llm.invoke([system_message, *state["messages"]])
        # 전체 대화 이력이 필요한가?

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
    # END와 연결하지 않은 이유가 있나? => END 작성 이유: 가독성, 유지보수성
    builder.add_edge("generate", END)

    return builder.compile(checkpointer=MemorySaver())  # 그래프 컴파일 시 체크포인터 연결


# ========= Multi-Agent ===============
# === 공유 State
class TeamState(TypedDict):
    query: str
    messages: Annotated[list, add_messages] # add_messages: reducer- 자동으로 리스트에 새로운 메시지를 append
    context: list[Document] # Retriever Agent의 결과 : reducer가 없으므로 노드가 반환하는 값으로 덮어쓰기된다. 매 질문마다 새로 검색한 문서로 교체
    cal_result: str # Calculate Agent의 결과
    next_agent: str     # Supervisor가 결정한 다음 Agent



def build_multi_agent():
    vector_store = load_vector_store()
    retriever = build_retriever(vector_store)
    
    llm = build_llm()
    
    if settings.llm_provider == "ollama":
        prompt = SYSTEM_PROMPT_LOCAL
    else:
        prompt = SYSTEM_PROMPT

    retriever_prompt = ChatPromptTemplate.from_messages([
        ("system",
         "다음 문서만을 근거로 사용자 질문에 답하세요.\n"
        "답변 후 반드시 '[출처] '라는 표시와 함께 참고한 문서의 파일명과 pdf문서의 경우에는 출처 페이지를 나열하세요.\n"
        "여러 문서나 페이지를 참고했다면 모두 나열하세요.\n"
        "근거가 부족하면 '주어진 자료에서는 확인할 수 없습니다.'라고 답하세요.\n\n"),
        ("user")
    ])
    def retriever_agent(state:TeamState):
        result = llm.invoke(retriever_prompt.format_messages(
            query=state["query"]
        ))
        return {"context": extract_text(result.content)}

    calc_prompt = ChatPromptTemplate.from_messages([
        ("system", "주어진 문장에서 필요한 수식을 계산해 과정을 설명하고 결과를 반환해주세요."),
        ("user", "문장: {query}")
    ])
    def calc_agent(state: TeamState):
        result = llm.invoke(calc_prompt.format_messages(
            query=state["query"],
        ))
        return {"cal_result": extract_text(result.content)}
    
    # === 1) Supervisor
    def supervisor(state: TeamState):
        pass

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

    @tool
    def retrieve_economics_word(query:str)->str:
        """경제용어를 검색하여 해당 용어에 대한 정보를 가져온다."""
        docs = retriever.invoke(query)
        return "\n\n".join([doc.page_content for doc in docs])


    def generate(state: State):
        docs = state["context"]
        #검색된 문서들을 하나의 문자열로 합쳐서(format_docs), 시스템 프롬프트의 {context}로 끼워넣는다.
        system_message = SystemMessage(
            content=prompt.format(context=format_docs(docs)) 
        )
        # 시스템 메시지 + 전체 대화 이력을 LLM에 넣어 응답 생성. (멀티턴 대화 맥락 유지)
        # 전체 대화 이력: 리스트 그대로가 아닌 리스트 안의 요소들을 하나씩 풀어서 넣는다 (unpacking) # [system_message, HumanMessage("질문1"), AIMessage("답변1"), HumanMessage("질문2")]
        response = llm.invoke([system_message, *state["messages"]])

        # 어떤 응답이든 str로 변환하기
        response_text = extract_text(response.content)

        if settings.llm_provider == "ollama":
            # 출처 직접 추가
            
            if settings.doc_source == "pdf":
                sources = sorted(set(
                doc.metadata.get('page','unknown') for doc in docs
                ))
                source_text = "\n\n[출처] " + ",".join(f"{p}페이지" for p in sources) #[출처] 모든 출처 페이지들 연결
            else:
                sources = sorted(set(
                Path(doc.metadata.get('source','unknown')).name for doc in docs
                ))
                source_text = "\n\n[출처] " + ",".join(sources) # [출처] 모든 출처 파일명들 연결
            
            response_text += source_text    # response_text의 맨 마지막에 source_text 추가


        response.content = response_text
        return {"messages": [response]} # 새로 생성된 응답 메시지 하나만 반환하면, reducer가 자동으로 기존 이력 뒤에 append
    
    builder = StateGraph(State)
    builder.add_node("retrieve", retrieve)
    builder.add_node("generate", generate)

    builder.add_edge(START, "retrieve")
    builder.add_edge("retrieve", "generate")
    # END와 연결하지 않은 이유가 있나? => END 작성 이유: 가독성, 유지보수성
    builder.add_edge("generate", END)

    return builder.compile(checkpointer=MemorySaver())