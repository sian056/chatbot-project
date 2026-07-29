from typing import TypedDict, Literal

import requests

from langchain_core.messages import AIMessage

from langgraph.graph import StateGraph, START, END
from langgraph.types import Command

from src.model import build_llm
from src.settings import settings
from src.agents.supervisor import SupervisorState

NAVER_NEWS_SEARCH_URL = "https://openapi.naver.com/v1/search/news.json"

summarize_llm = build_llm()

# news_agent 서브그래프 전용 State
class NewsState(TypedDict):
    query: str
    articles: list[dict]    # search_news가 채울 내용(article)
    answer: str         

# search_news 노드
def search_news(state: NewsState)-> dict:
    query = state["query"]

    # 네이버 검색 API 공통 인증 헤더
    headers = {
        "X-Naver-Client-Id": settings.naver_client_id,
        "X-Naver-Client-Secret": settings.naver_client_secret,
    }

    params = {
        "query": query,
        "display": 5, #가져올 기사 개수
        "start": 1,
        "sort": "date", #최신 경제 뉴스를 가져올 것이기에
    }

    response = requests.get(
        NAVER_NEWS_SEARCH_URL,
        headers=headers,
        params=params,
        timeout=5
    )
    response.raise_for_status() # 401(인증 실패), 429(요청 한도 초과) 등을 예외로 처리

    raw_items = response.json().get("items", [])

    # 네이버 API 응답은 title/description에 <b> 태그가 섞여서 온다 (검색어 강조용)
    # 사용자에게 보여주거나 LLM에게 넘기기 전에 제거
    def strip_html(text: str)-> str:
        return text.replace("<b>", "").replace("</b>","").replace("&quot;",'"')

    articles = [
        {
            "title": strip_html(item["title"]),
            "description": strip_html(item["description"]),
            # original link가 비어있을 경우 네이버 링크로 대체
            "originallink": item.get("originallink") or item["link"],
            "pub_date": item["pubDate"],
        }
        for item in raw_items
    ]

    return {"articles": articles}

# summarize 노드 : 여러개의 뉴스를 요약
def summarize(state: NewsState) ->dict:
    """
    articles를 컨텍스트로 사용해 종합 답변을 생성하고 각 기사의 출처 링크를 붙인다.
    """
    articles = state["articles"]

    if not articles:
        # 검색 결과가 없는 경우
        return {"answer": "관련된 최신 뉴스를 찾지 못했습니다."}

    # LLM에 넘길 기사 목록 텍스트 구성
    # 제목과 요약본만 있다는 것을 프롬프트에서 명시하기
    articles_text = "\n\n".join(
        f"[기사 {i+1}] {a['title']}\n요약: {a['description']}\n발행일: {a['pub_date']}"
        for i,a in enumerate(articles)
    )

    prompt = (
        "다음은 뉴스 검색 API로 찾은 기사들의 제목과 요약입니다. "
        "이 정보를 종합하여 질문에 답하는 자연스러운 설명을 작성하세요. "
        "요약 문장을 그대로 옮기지 말고, 여러 기사의 핵심 내용을 재구성해서 서술하세요.\n\n"
        f"[질문]\n{state['query']}\n\n"
        f"[검색된 기사 목록]\n{articles_text}"
    )

    response = summarize_llm(prompt)

    # 기사의 출처를 코드에서 직접 조립한다.
    source_list = "\n".join(f"- {a['title']}: {a['originallink']}" for a in articles)

    final_answer = f"{response.content}\n\n[출처]\n{source_list}"

    return {"answer": final_answer}

# news subgraph 
def build_news_subgraph():
    builder = StateGraph(NewsState)

    builder.add_node("search_news", search_news)
    builder.add_node("summarize", summarize)

    builder.add_edge(START, "search_news")
    builder.add_edge("search_news","summarize")
    builder.add_edge("summarize", END)

    return builder.compile()

# news agent 노드
def news_agent(state: SupervisorState)-> Command[Literal["supervisor"]]:

    # 입력 변환
    user_query = state["current_turn_query"]
    news_input = {
        "query": user_query,
        "articles": [],
        "answer": ""
    }

    # subgraph
    news_subgraph = build_news_subgraph()
    result = news_subgraph.invoke(news_input)

    # 출력 변환: NewsState -> SupervisorState
    return Command(
        goto="supervisor",
        update={
            "messages": [
                AIMessage(content=result["answer"], name="news_agent")
            ]
        }
    )