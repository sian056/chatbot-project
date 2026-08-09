import requests, time
from typing import TypedDict, Annotated

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, AnyMessage

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.types import Command

from src.model import build_llm
from src.settings import settings
from src.utils import extract_text, format_elapsed, print_messages

NAVER_NEWS_SEARCH_URL = "https://openapi.naver.com/v1/search/news.json"

_keyword_llm = build_llm(name="News Rewrite", provider=settings.news_keyword_provider)
_summarize_llm = build_llm(name="News Agent", provider=settings.news_summarize_provider)

# news_agent 서브그래프 전용 State
class NewsState(TypedDict):
    # 공유 키
    query: str
    messages: Annotated[list[AnyMessage], add_messages]

    # 비공유 키
    articles: list[dict]    # search_news가 채울 내용(article)
    answer: str
    keyword_query: str       # 뉴스 검색용 키워드
    sources: list[dict]


def keyword_query(state: NewsState) -> dict:
    print(f"\n================================== [DEBUG][NEWS][REWRITE] ==================================n")
    st_time = time.time()

    SYSTEM_PROMPT_QUERY = (
        "당신은 사용자의 요청에서 '최신 뉴스나 시사 정보 검색'과 관련된 부분만 뽑아,"
        "뉴스 검색 API에 적합한 키워드를 추출하는 전문가입니다.\n"
        "사용자의 질문과 대화 이력을 보고, 네이버 뉴스 검색에 최적화된 핵심 키워드만 추출하세요.\n\n"
        "규칙:\n"
        "- 반드시 2~4단어 이내의 키워드만 출력하세요.\n"
        "- 조사(을/를/이/가/의), 동사(알려주세요/설명해줘), 부사는 제거하세요.\n"
        "- 대화 이력에서 대명사(그거/이거/그것)가 있으면 실제 단어로 바꾸세요.\n"
        #"- 만약 사용자의 질문에 대명사, 생략된 주어/목적어가 있다면 대화 이력을 보고 명시적으로 채워 넣은 후 키워드를 추출하세요.\n"
        #"(예시: '그거와 관련된 뉴스를 알려줘' -> '전세와 관련된 뉴스를 알려줘' -> '전세')"
        "- 사용자의 요청이 여러 요구사항을 담은 복합 질문이라면, 그중 '최신 뉴스/동향'에 해당하는 부분만 뽑아내세요.\n"
        "용어 정의나 개념 설명을 요청하는 부분은 완전히 무시하고 포함하지 마세요.\n"
        "- 키워드 외에 다른 텍스트는 절대 출력하지 마세요.\n\n"
        "예시:\n"
        "질문: '전세와 관련된 최신 뉴스를 알려주세요' → '전세 시장'\n"
        "질문: '금리 인상이 경제에 미치는 영향 뉴스 알려줘' → '금리 인상 경제'\n"
        "질문: '그것과 관련된 최신 동향은?' (이전 대화: 환율) → '환율 동향'\n"
        
    )
    
    # print(f"[DEBUG][MESSAGES 전체]")
    # for i,m in enumerate(state["messages"]):
    #     print(f"    [{i}] {type(m).__name__}: {m.content[:50]}")

    # print(f"[DEBUG][MESSAGES 타입] {[type(m) for m in state['messages']]}")
    # print(f"[DEBUG][MESSAGES 개수] {len(state['messages'])}")

    query = state["query"]  # 질문자의 오리지널 쿼리
    print(f"[DEBUG][NEWS][REWRITE][ORIGINAL QUERY] {query}")
    
    # Supervisor의 판단 메시지와 질문자의 오리지널 쿼리 메시지를 제외한 대화 이력
    history = state["messages"][:-1]

    # print(f"[DEBUG][HISTORY] {history}")
    # print(f"[DEBUG][HISTORY 개수] {len(history)}")

    rewritten_query = _keyword_llm.invoke([
        {"role": "system", "content": SYSTEM_PROMPT_QUERY},
        *history,
        {"role": "user", "content": f"다시 써야 할 질문: {query}"}
    ])
    # print(f"[DEBUG][NEWS][REWRITE][REWRITTEN QUERY]{rewritten_content}")
    
    rewritten_content = extract_text(rewritten_query.content)
    # 비어있는 Rewritten query라면
    if not rewritten_content:
        print(f"[DEBUG][NEWS][REWRITE] 빈값 반환 -> 원본 쿼리 사용")
        rewritten_content = query
        print(f"[DEBUG][NEWS][REWRITE][REWRITTEN QUERY]{rewritten_content}")
    else:
        print(f"[DEBUG][NEWS][REWRITE][KEYWORD]{rewritten_content}")

    cost_time = format_elapsed(st_time)
    print(f"\n[TIME][NEWS][REWRITE] {cost_time}\n")

    return {"keyword_query": rewritten_content}

# search_news 노드
def search_news(state: NewsState)-> dict:
    print(f"\n================================== [DEBUG][NEWS][SEARCH] ==================================n")
    print_messages("news_agent.summarize 진입", state["messages"])
    st_time = time.time()

    query = state["keyword_query"]  # 뉴스 검색용 키워드

    # 네이버 검색 API 공통 인증 헤더
    headers = {
        "X-Naver-Client-Id": settings.naver_client_id,
        "X-Naver-Client-Secret": settings.naver_client_secret,
    }

    # 검색 파라미터
    params = {
        "query": query, # 검색어
        "display": 3,   # 가져올 기사 개수
        "start": 1,     # 검색 시작 위치    
        "sort": "sim",  # 정렬 (sim=관련도순)(date=날짜순)
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
    #print(articles)

    cost_time = format_elapsed(st_time)
    print(f"[TIME][NEWS][SEARCH] {cost_time}")

    return {"articles": articles}

# summarize 노드 : 여러개의 뉴스를 요약
def summarize(state: NewsState) ->dict:
    """
    articles를 컨텍스트로 사용해 종합 답변을 생성하고 각 기사의 출처 링크를 붙인다.
    """
    print(f"\n================================== [DEBUG][NEWS][SUMMARIZE] ==================================n")
    st_time = time.time()

    articles = state["articles"]

    if not articles:
        # 검색 결과가 없는 경우
        no_answer = "관련된 최신 뉴스를 찾지 못했습니다."
        return {
            "answer": no_answer,
            "messages": [
                AIMessage(
                    content=no_answer,
                    name="news_agent",
                    additional_kwargs={"found_results": False},
                )
            ]
        }

    # LLM에 넘길 기사 목록 텍스트 구성
    # 제목과 요약본만 있다는 것을 프롬프트에서 명시하기
    articles_text = "\n\n".join(
        f"[기사 {i+1}] {a['title']}\n요약: {a['description']}\n발행일: {a['pub_date']}"
        for i,a in enumerate(articles)
    )

    prompt = (
        "다음은 뉴스 검색 API로 찾은 기사들의 제목과 요약입니다. "
        "이 정보를 종합하여 사용자의 질문에 답하는 자연스러운 설명을 작성하세요. "
        "요약 문장을 그대로 옮기지 말고, 여러 기사의 핵심 내용을 재구성해서 서술하세요.\n"
        "만약 사용자의 질문에 용어 정의나 개념 설명을 요청하는 부분이 있으면 그 부분은 무시하고"
        "뉴스에 대한 설명만 하세요.\n\n"
        "[검색된 기사 목록]\n{articles}"
    )

    system_message=SystemMessage(
        content=prompt.format(articles=articles_text)
    )
    # 뉴스 요약을 위해 오리지널 쿼리 사용.
    human_message = HumanMessage(content=state["query"])
    # 1. 전체 대화이력을 넘겨주는 경우 ===========
    #response = _summarize_llm.invoke([system_message, *state["messages"]])
    # ================================


    # 2. 오리지널 쿼리 질문을 제외하고 넘겨주는 경우 ============
    # history = state["messages"][:-1]

    # # print(f"[DEBUG][MESSAGES][최신 쿼리 제외]")
    # # for i,m in enumerate(history):
    # #     print(f"    [{i}] {type(m).__name__}: {m.content[:40]}")
    
    # response = _summarize_llm.invoke(
    #     [system_message, 
    #      *history,
    #     ]
    # )
    # ==================================

    # 3. 대화 이력을 넘겨주지 않는 경우 (오리지널 쿼리만 보고 답변 생성한다.)
    response = _summarize_llm.invoke([system_message, human_message])

    # 답변을 str으로 변환
    response_text = extract_text(response.content)
    print(f"[DEBUG][NEWS][SUMMARIZE][RESPONSE]\n{response_text}")
    # ==================================

    # 출처 출력을 위해
    link_src_stream = [{"title": a['title'], "url": a['originallink']} for a in articles]
    
    cost_time = format_elapsed(st_time)
    print(f"\n[TIME][NEWS][SUMMARIZE] {cost_time}\n")

    return {
        "answer": response_text,    # 출처 없는 답변 메시지
        "sources": link_src_stream, # updates 모드에서 이 값을 읽는다
        "messages": [
            AIMessage(
                content=response_text,  # 출처 없는 답변 메시지
                name="news_agent",
                additional_kwargs={
                    "found_results": bool(articles),    # 검색된 뉴스 존재 여부
                    "sources": link_src_stream,         # 기록용으로 메시지에 출처를 남긴다.
                },
            )
        ]
    }

def _build_news_subgraph():
    builder = StateGraph(NewsState)

    builder.add_node("keyword_query", keyword_query)
    builder.add_node("search_news", search_news)
    builder.add_node("summarize", summarize)

    builder.add_edge(START, "keyword_query")
    builder.add_edge("keyword_query", "search_news")
    builder.add_edge("search_news","summarize")
    builder.add_edge("summarize", END)

    return builder.compile()

news_subgraph = _build_news_subgraph()
