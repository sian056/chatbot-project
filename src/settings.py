# source/settings.py
import unicodedata
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator, field_validator
from pathlib import Path

# settings.py 위치 기준으로 프로젝트 루트 계산
# src/settings.py → parent(=src) → parent(=프로젝트 루트)
BASE_DIR = Path(__file__).resolve().parent.parent

# Pydantic BaseSettings 로 통합 관리 : 실무에서 가장 권장되는 방식
# 민감/비민감 정보를 나누되, 한 군데에서 타입 검증까지 하면서 관리하는 방식
class Settings(BaseSettings):
    # 민감 정보의 경우에는 반드시 .env에서 채워져야 함, 기본값 없음

    # ── LLM Provider 선택 ──
    supervisor_provider:  Literal["google", "ollama"]   # fallback과 동일
    rag_rewrite_provider:  Literal["google", "ollama"]
    rag_generate_provider:  Literal["google", "ollama"]
    news_keyword_provider:  Literal["google", "ollama"]
    news_summarize_provider:  Literal["google", "ollama"]

    # google 설정
    google_model: str = "gemini-3.1-flash-lite"
    google_api_key: str | None = None

    # ollama 설정
    ollama_model: str = "gemma4:e2b-mlx"
    ollama_base_url: str = "http://localhost:11434"

    # naver 검색 api 설정
    naver_client_id: str
    naver_client_secret: str

    
    # ── Embedding Provider 선택 ──
    embedding_provider: Literal["hugging", "google"]

    google_embedding: str = "models/gemini-embedding-001"
    hugging_embedding: str = "BAAI/bge-m3"

    # indexing 관련 설정
    #doc_source: Literal["github", "dir", "pdf"]
    doc_source: str = "pdf"
    pdf_name: str = "2026_경제금융용어_800선.pdf" #"2026_경제금융용어_short.pdf" "2026_경제금융용어_short.pdf"
    pdf_path: str = str(BASE_DIR / pdf_name)

    # vector DB
    persist_dir: str = str(BASE_DIR / "chroma_db") #"../chroma_db"
    collection_name: str = "RAG-sian-"
    #collection_name: str = "RAG-sian-"+ doc_source
    eval_dataset_name: str = "sian-til-rag-eval"


    # ── LangSmith ──
    langsmith_tracing: bool
    langsmith_endpoint: str
    langsmith_api_key: str | None = None  # 선택적 (트레이싱 안 쓰면 None)
    langsmith_project: str = "default"

    # judge llm 설정
    judge_model: str = "gemini-3.1-flash-lite"

    # # TIL : directory md 파일 사용시
    # md_path: str = str(BASE_DIR / "sian-til" / "*.md") # "./sian-til/*.md"
    # md_dir_path: str = str(BASE_DIR / "sian-til") #"./sian-til" # BASE_DIR가 pathlib.Path 객체라서 / 연산자로 경로를 이어붙이기 가능

    # # TIL : github md 파일 사용시
    # github_repo: str = "sian35/KTB4-Sian-TIL"
    # github_token: str | None = None

    # ── 설정 로드 방식 지정 ──
    # ".env 파일을 utf-8로 읽고, 대소문자 구분 없이, 모르는 필드는 무시하면서 설정값을 로드해라" 라는 BaseSettings의 동작 방식을 정의하는 메타 설정
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",  #.env 파일에 한글이 있다면 필수
        case_sensitive=False,       # 환경변수의 대소문자를 구분하지 않음
        extra="ignore",             # .env 파일이나 환경변수에 Settings 클래스에 정의되지 않은 필드 무시 (에러 없음)
    )

    # 모델 전체(모든 필드)를 검증
    @model_validator(mode="after")  #mode="after": 모든 필드가 파싱된 후에 실행(self로 접근 가능)
    def check_provider_requrements(self) -> "Settings":
        """선택된 provider에 필요한 API 값이 채워졌는지 검증"""
        all_providers = [
            self.supervisor_provider,
            self.rag_rewrite_provider,
            self.rag_generate_provider,
            self.news_keyword_provider,
            self.news_summarize_provider,
        ]
        if "google" in all_providers and not self.google_api_key:
            raise ValueError(
                "LLM_PROVIDER=google인데 GOOGLE_API_KEY가 설정되지 않았습니다. "
                ".env 파일을 확인하세요."
            )
        # ollama는 로컬 서빙이라 API 키가 필요 없으므로 별도 검증 없음
        return self
    
    # ===============================
    
    # Settings()가 생성될 때 자동으로 실행
    #@field_validator : 특정 필드 하나만 검증, 같은 검증 로직을 여러 필드에 재사용 가능
    @field_validator("pdf_name")#pdf_name 필드값이 설정될 때마다 아래 함수를 자동으로 호출
    @classmethod    # 인스턴스가 아닌 클래스 메서드로 선언 (@filed_validator는 반드시 @classmethod와 함께 사용)
    def normalize_pdf_name(cls, v): # 실제 검증/변환 로직 # cls: Settings 클래스 자체를 가리킴, v: 해당 필드에 들어온 실제 값(pdf_name의 값)
        return unicodedata.normalize("NFC", v)

# 앱 전체에서 재사용할 싱글턴 인스턴스
settings = Settings()

