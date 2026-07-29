# chatbot-project/main.py
import uuid

from contextlib import asynccontextmanager
from fastapi import FastAPI
from pydantic import BaseModel

from langchain_core.messages import HumanMessage

from src.rag.graph import build_rag_graph

# === 요청 / 응답 스키마 ===
class QueryRequest(BaseModel):
  question: str
  thread_id: str | None = None

class QueryResponse(BaseModel):
  answer: str
  thread_id: str


# Lifespan : 앱 생명주기 관리

# ===== LangGraph ======
@asynccontextmanager
async def lifespan(app: FastAPI):
  # FastAPI 앱 초기화 시점에 인덱싱 + RAG 그래프 구성
  app.state.graph = build_agent_graph()
  yield

# FastAPI 앱 인스턴스를 생성하면서 lifespan 함수를 등록
app = FastAPI(lifespan=lifespan)

@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest):
  thread_id = req.thread_id or str(uuid.uuid4())  # 랜덤 UUID 생성
  result = app.state.graph.invoke(
    {"query": req.question,
     "messages": [HumanMessage(content=req.question)]},
    config = {"configurable": {"thread_id": thread_id}}
  )
  answer = result["messages"][-1].content # 응답이 메시지 이력의 맨 뒤에 append 되어 있기 때문에 [-1]로 가져옴
  return QueryResponse(answer=answer, thread_id = thread_id)