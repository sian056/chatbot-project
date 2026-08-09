import os

from langchain_chroma import Chroma

from src.settings import settings
from src.dataset.data_loader import chunking, load_dir, load_github, load_pdf
from src.model import build_embedding

# Embedding model
embeddings = build_embedding()

#load_dotenv()

def initial_indexing():
    print("[INFO] Initialize Indexing")
    embeddings = build_embedding()

    if settings.doc_source == "dir":
        docs = load_dir()
        
    elif settings.doc_source == "github":
        docs = load_github()
    
    elif settings.doc_source == "pdf":
        docs = load_pdf()

    # Chunking 필수
    split_docs = chunking(docs)

    # ====== Vector DB 디렉토리 없으면 생성 ======
    if not os.path.exists(settings.persist_dir):
        os.makedirs(settings.persist_dir)

    # ====== 영구 저장 모드 ======
    collection_name = settings.collection_name + settings.doc_source
    #print(collection_name)
    # from_documents: 생성과 동시에 추가 
    vectorstore = Chroma.from_documents(
        split_docs,
        embeddings,
        collection_name=collection_name, # 한 persist_directory 안에 여러 컬렉션을 분리 저장할 수 있다
        persist_directory=settings.persist_dir, # Chroma가 해당 폴더에 SQLite 파일로 인덱스를 저장. 프로세스를 다시 시작해도 이 폴더에서 인덱스를 다시 열 수 있다.
    )

    print("[INFO] ... Vector DB 저장 완료. ./chroma_db 폴더에 SQLite 인덱스가 생성되었습니다.")
    print("[INFO] Finish Indexing")

    return vectorstore

def load_vector_store():
    print(f"[INFO] ... Loading Index ...")
    print(f"[INFO] ... Documents from : {settings.doc_source}")
    
    collection_name = settings.collection_name+settings.doc_source

    # ====== 기존 Vector DB 로드 (from_documents 호출 없이) ======
    vectorstore = Chroma(
        collection_name=collection_name,
        persist_directory=settings.persist_dir,
        embedding_function=embeddings,  # 새 질의를 벡터로 변환할 때 사용할 임베딩 모델
        # 저장된 문서 벡터는 처음 인덱싱할 때 사용한 임베딩 모델 기준으로 만들어졌습니다. 따라서 다시 검색할 때도 같은 임베딩 모델을 사용해야 합니다.
    )
    return vectorstore  #.as_retriever(search_kwargs={"k":3})

def build_retriever(vectorstore):
    return vectorstore.as_retriever(search_kwargs={"k":3}) # k: 가져올 검색 결과 개수, 검색 결과를 항상 List[Document] 형태로 반환한다.
# 내부적으로 저장된 embeddings 객체를 그대로 쿼리 임베딩에도 사용


# 프로그램의 시작점일 때만 아래 코드 실행
# 파일이 메인 프로그램으로 사용될 때와 모듈로 사용될 때를 구분하기 위한 용도
if __name__ == '__main__': 
    initial_indexing()
