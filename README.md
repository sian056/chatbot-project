# chatbot-project
## 프로젝트 과정
| week | 과제 | 진행 | 회고 |
|:---:|---|:---:|:---:|
|5| 다음 단어를 생성하는 Transformer Model을 이용해 챗봇을 구현한다.|✅|[회고]()|
|6| 개인 프로젝트의 바닐라 RAG 시스템을 구현한다. |✅|[회고]()|
|7| 개인 프로젝트의 RAG 시스템을 LangChain 기반으로 구현한다.|✅|[회고](./docs/week7-retro.md)|
|8| 개인 프로젝트의 RAG 시스템을 LangGraph 기반으로 구현한다.|✅|[회고](./docs/week8-retro.md)|
|9| 개인 프로젝트에 멀티 Agent를 적용한다.|🔜|[회고](./docs/week9-retro.md)|

## 프로젝트 설명
상황에 따른 필요한 경제 금융 용어를 뽑아내고 해당 용어에 대한 정의와 설명을 검색해준다. 

## 데이터 셋
한국은행에서 배포한 2026 경제금융용어 800선

## 파일 구조
```
chatbot-project/
├── docs/            회고 기록
├── src/
│    ├── dataset/
│    │   ├── data_loader.py     Load Documents
│    │   ├── eval_dataset.py    Evaluation Dataset
│    │   └── vector_store.py    Retriever
│    ├── rag/
│    │   ├── chain.py           Lang Chain
│    │   └── graph.py           Lang Graph
│    ├── eval.py                LangSmith Evaluation
│    ├── model.py               Embedding & LLM model
│    ├── prompts.py             Prompts
│    └── settings.py            settings
├──── main.py                   REST API
└──── test.py                   run test
```
---
## 초기 세팅
1. `.env` ← 설정
```
LANGSMITH_TRACING=
LANGSMITH_ENDPOINT=
LANGSMITH_API_KEY=
LANGSMITH_PROJECT=

# LLM 선택: google 또는 ollama
LLM_PROVIDER=ollama

# google 사용 시 모델명 (선택)
GOOGLE_MODEL=gemini-3.1-flash-lite
GOOGLE_API_KEY=
# ollama 사용 시 설정 (gemma4:e2b-mlx 가 ollama로 서빙되어야 함)
OLLAMA_MODEL=gemma4:e2b-mlx
OLLAMA_BASE_URL=http://localhost:11434

# LLM-as-Judge
JUDGE_MODEL=gemini-3.1-flash-lite

# Embedding 선택: hugging 또는 google (기본)
EMBEDDING_PROVIDER=hugging

# google 사용 시 Embedding 모델명
GOOGLE_EMBEDDING=models/gemini-embedding-001
# hugging face 사용 시 설정
HUGGING_EMBEDDING=BAAI/bge-m3

# RAG 문서 출처 : dir, github, pdf
DOC_SOURCE=pdf
```
2. `uv sync` ← 의존성 설치  
> ollama 사용시
```
ollama pull gemma4:e2b-mlx ← 올라마 모델 다운로드
ollama serve ← 서버 띄우기
```
3. 초기 `Indexing` (한번만 실행)
> 프로젝트 루트 위치(chatbot-project)에서 실행하기 
```
uv run -m src.dataset.vector_store
```
---
## 실행 방법
> 프로젝트 루트 위치에서 실행하기  

1. FastAPI 
```
uv run uvicorn main:app ← 스웨거 문서로 확인 http://localhost:8000/docs
```

2. FastAPI 없이 단일 쿼리 테스트 또는 LangSmith 평가 테스트
```
uv run test.py --mode chain     # LangChain 단일 쿼리 테스트
uv run test.py --mode graph     # LangGraph 단일 쿼리 테스트

검색하고 싶은 개념을 입력하세요: 가계부실위험지수
Sample Question: 가계부실위험지수란 무엇인가요?


uv run test.py --mode smith     # LangSmith 평가 테스트

```
