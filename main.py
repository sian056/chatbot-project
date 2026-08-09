# chatbot-project/main-agent.py
import uuid, json, time

from contextlib import asynccontextmanager
from fastapi import FastAPI
from pydantic import BaseModel

from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from langchain_core.messages import HumanMessage

from src.multi_agent_graph import build_multi_agent_graph
from src.agents.supervisor import AGENT_LABELS
from src.utils import print_messages, extract_text
from src.settings import settings

TOP_LEVEL_STATUS_LABELS = {
  "prepare_query": "질문을 정리하는 중...",
  "supervisor": "다음 단계를 판단하는 중...",
}
SUBGRAPH_STATUS_LABELS = {
  "retrieve": "문서를 검색하는 중...",
  "generate": "답변을 생성하는 중...",
  "search_news": "뉴스를 검색하는 중...",
  "summarize": "뉴스를 요약하는 중...",
}

# 이 조합에 해당하는 노드에서 나온 토큰만 "token" 이벤트로 내보낸다.
TOKEN_SOURCES = {
  ("rag_agent","generate"): "rag_agent",
  ("news_agent","summarize"): "news_agent",
}

SECTION_PROVIDERS = {
  "rag_agent": settings.rag_generate_provider,
  "news_agent": settings.news_summarize_provider,
}

# 서브그래프의 이름만 가져오는 함수
def _subgraph_name_from_namespace(namespace: tuple) -> str|None:
  if not namespace:
    return None
  try:
    return namespace[0].split(":")[0]  #"노드이름:task_id"
  except (IndexError, AttributeError):  #형태가 다른 형식 오면 None
    return None

# === 요청 / 응답 스키마 ===
class QueryRequest(BaseModel):
  question: str
  thread_id: str | None = None

class QueryResponse(BaseModel):
  answer: str
  thread_id: str

# ===== LangGraph ======
# Lifespan : 앱 생명주기 관리
@asynccontextmanager
async def lifespan(app: FastAPI):
  # FastAPI 앱 초기화 시점에 인덱싱 + RAG 그래프 구성
  app.state.graph = build_multi_agent_graph() #yield 이전 코드는 서버가 시작될 때 딱 한 번 실행된다.
  yield

# FastAPI 앱 인스턴스를 생성하면서 lifespan 함수를 등록
app = FastAPI(lifespan=lifespan)

# CORS 미들웨어
# 다른 origin에서 fetch 요청을 보낼 수 있게 허용
# 프론트/백엔드가 같은 origin에서 서빙된다면, 이 미들웨어 자체를 제거해도 됨
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 개발 단계에서는 전체 허용, 배포 시에는 실제 프론트 origin으로 제한
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/query/stream") # Streaming은 리턴값이 StreamingResponse
def query(req: QueryRequest):
  st_time = time.time()

  thread_id = req.thread_id or str(uuid.uuid4())
  config = {
    "configurable": {"thread_id": thread_id},
    "recursion_limit": 10,
  }
  inputs = {"messages": [HumanMessage(content=req.question)]}

  # ---- for streaming ----
  def _sse(event:str, data:dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

  def event_generator():
    first_token_time = None # TTFT 측정
    section_accumulated = {}  # section별로 지금까지 전송한 텍스트 누적

    try:
      for namespace, mode, chunk in app.state.graph.stream(
        inputs,
        config=config,
        stream_mode=["updates", "messages"],
        subgraphs=True
      ):
        if mode == "updates":
          for node_name, node_output in chunk.items():  
            # namespace가 비어있으면 상위 그래프, 비어있지 않으면 하위 그래프
            labels = TOP_LEVEL_STATUS_LABELS if not namespace else SUBGRAPH_STATUS_LABELS
            label = labels.get(node_name)
            if label:
              yield _sse("status", {"label": label})  # status: 어떤 노드 실행 중인지 보여주기 위해

            # Stream에서 출처 표시
            subgraph_name = _subgraph_name_from_namespace(namespace)
            if subgraph_name in AGENT_LABELS.keys() and node_name in ("generate","summarize"):
               sources = node_output.get("sources", [])
               if sources:
                  yield _sse("sources",{
                     "section": subgraph_name,
                     "items": sources,
                  })
            # -----------------------

        elif mode == "messages":
          msg_chunk, metadata = chunk
          node_name = metadata.get("langgraph_node")
          tags = metadata.get("tags", [])

          # Extract text 반드시 필요. (화면 표시용) fallback_answer 함수에서 답변을 extract_text한것과는 별개의 작업
          text = extract_text(msg_chunk.content)

          # ---- [DEBUG] 이 노드에서 나오는 모든 청크를 순서대로, 길이와 함께 확인 ----
          # if node_name == "generate":
          #     print(f"[DEBUG][CHUNK] len={len(text)} | text={text!r}")

          if node_name == "supervisor" and "fallback_answer" in tags: # 잡담 응답 또는 검색 실패 응답일 경우
            # section_label: 누구의 응답인지 (rag인지, news인지, 단순 답변인지)
            section, section_label = "fallback_answer", AGENT_LABELS["fallback_answer"]
            #print(f"[DEBUG] -> fallback_answer 분기로 매칭됨, section={section}")
          else:
            subgraph_name = _subgraph_name_from_namespace(namespace)

            if subgraph_name == "rag_agent" and node_name == "generate":
                section, section_label = "rag_agent", AGENT_LABELS["rag_agent"]
            elif subgraph_name == "news_agent" and node_name == "summarize":
                section, section_label = "news_agent", AGENT_LABELS["news_agent"]
            else:
                #print(f"[DEBUG] -> 매칭 실패, continue로 버려짐 (tags={tags})")
                continue

          if text:
            # 첫 토큰 오는 시간(TTFT) 측정
            if first_token_time is None:
              first_token_time = time.time()
              print(f"[TIME] TTFT: {first_token_time - st_time:.2f}초")

            # ----------------------- 누적 텍스트와 비교하여 중복 텍스트가 오면 넘긴다.-------------
            prev = section_accumulated.get(section, "")
            # 새 텍스트가 지금까지 누적된 것 전체를 그대로 포함하는 "재전송"이라면 건너뛴다.
            # 비교 먼저 -> 그 다음 누적
            if prev and text.strip() == prev.strip():
               print(f"[DEBUG][SSE] 완성본 재전송으로 판단되어 건너뜀 (len={len(text)})")
               continue
            section_accumulated[section] = section_accumulated.get(section,"")+text


            yield _sse("token", {             # "token" : 실시간으로 타이핑할 텍스트 조각
              "section":section,              # 속하는 agent
              "section_label": section_label, # 누구의 응답인지에 따른 표시 (용어 설명 or 관련 뉴스 or 답변)
              "text": text,                   # 텍스트 조각 (토큰)
            }
            )

    except Exception as e:
      yield _sse("error", {"error": str(e)})

    # 그래프 실행이 모두 끝난 뒤, thread_id에 실제로 무엇이 최종 저장됐는지 확인
    final_state = app.state.graph.get_state(config)
    print_messages("[DEBUG] 턴 종료 후 최종 저장 상태", final_state.values["messages"])

    # 전체 처리 시간 측정
    end_time = time.time()
    print(f"[TIME] 전체 처리 시간: {end_time - st_time:.2f}초\n")

    yield _sse("done", {"thread_id":thread_id}) # "done" 다음 턴에 쓸 thread_id

  return StreamingResponse(event_generator(), media_type="text/event-stream")


# invoke
# @app.post("/query", response_model=QueryResponse)
# def query(req: QueryRequest):
#   thread_id = req.thread_id or str(uuid.uuid4())  # thread_id 없으면 랜덤 UUID 생성
#   config = {
#         "configurable": {"thread_id": thread_id}, 
#         "recursion_limit": 20,
#       }
#   inputs = {"messages": [HumanMessage(content=req.question)]}

#   # invoke
#   result = app.state.graph.invoke(#그래프 실행
#     inputs,
#     config=config
#   )

#   # supervisor의 final answer
#   answer = result["messages"][-1].content # 응답이 메시지 이력의 맨 뒤에 append 되어 있기 때문에 [-1]로 가져옴
#   return QueryResponse(answer=answer, thread_id = thread_id)  # 직접 정의한 스키마

# 반드시 모든 API 라우트 뒤, 파일의 가장 마지막에 위치해야 함
app.mount("/", StaticFiles(directory="static", html=True), name="static")
# name: FastAPI 내부에서 이 마운트를 가리킬 식별자(url_for() 등에 씀). 지금 프로젝트 규모에서는 크게 신경 쓰지 않아도 됨