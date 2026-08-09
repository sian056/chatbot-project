
from langchain_google_genai import ChatGoogleGenerativeAI

from src.settings import settings

#load_dotenv()

def build_embedding():
    # Embedding model
    provider = settings.embedding_provider.lower()
    print(f"[INFO] Build Embedding : {provider}")
    if settings.embedding_provider == "google":
        from langchain_google_genai import GoogleGenerativeAIEmbeddings
        embeddings = GoogleGenerativeAIEmbeddings(
            model=settings.google_embedding,
            google_api_key=settings.google_api_key,
        )
    else:
        from langchain_huggingface import HuggingFaceEmbeddings
        embeddings = HuggingFaceEmbeddings(
        model_name=settings.hugging_embedding,
        encode_kwargs={"normalize_embeddings": True}
    )

    return embeddings


def build_llm(name, provider):
    provider = provider.lower()
    print(f"[INFO] Build LLM for {name}: {provider}")

    if provider == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(
            model=settings.ollama_model,
            base_url=settings.ollama_base_url,
        )

    return ChatGoogleGenerativeAI(
        model=settings.google_model,
        google_api_key=settings.google_api_key,
    )

def build_supervisor_llm():
    """Supervisor는 구조화된 출력이 필요하므로 별도 설정"""
    print(f"[INFO] Build Supervisor LLM: google {settings.google_model}")
    # from langchain_ollama import ChatOllama
    # return ChatOllama(
    #     model=settings.ollama_model,
    #     base_url=settings.ollama_base_url,
    #     format="json",
    # )
    return ChatGoogleGenerativeAI(
        model=settings.google_model,
        google_api_key=settings.google_api_key,
    )


def build_judge_llm():
    print(f"[INFO] Build Judge LLM: {settings.judge_model}")
    return ChatGoogleGenerativeAI(
            model=settings.judge_model,
            google_api_key=settings.google_api_key,
        )


