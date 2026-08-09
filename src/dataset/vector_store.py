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
    print(collection_name)
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

# 문서 업데이트 시 증분 인덱싱
def add_indexing():
    print("[INFO] ---- 추가 인덱스 생성 시작 ---- ")
    # ===== 1. 먼저 해야 할 일: 변경된 문서에서 생성된 기존 청크만 정확하게 찾아 제거하는 것
    #조회된 청크 ID를 이용해 해당 청크만 삭제하면, 다른 문서의 벡터는 그대로 유지한 채 업데이트 대상 문서만 교체할 준비를 마칠 수 있다
    target_source = "sample_preprocessing.pdf"
    #메타데이터의 source 값을 기준으로, 해당 문서에서 생성된 청크만 조회한다.
    #다른 문서의 청크는 건드리지 않는다.
    existing = collection.get(
        where={"source":target_source}
    )

    # 조회된 청크의 ID 목록을 가져온다.
    old_ids = existing["ids"]
    print(f"삭제 대상: {target_source} → {len(old_ids)}개 청크")

    # 해당 청크만 벡터 DB에서 삭제한다
    collection.delete(ids=old_ids)
    print(f"삭제 완료. 현재 ChromaDB 저장 수: {collection.count()}")

    # ===== 2. 업데이트된 문서를 재인덱싱
    # 새 버전 파일을 지정한다.
    updated_doc = {"filepath": "sample_preprocessing_v2.pdf", "format": "pdf"}

    # 새 버전 pdf를 로딩 → 전처리 → 청킹 → 임베딩
    raw_text = load_pdf(updated_doc["filepath"])
    cleaned_text = preprocess_text(raw_text)
    chunks = chunk_text(cleaned_text, chunk_size=500, chunk_overlap=50)
    embeddings = model.encode(chunks).tolist()

    # ChromaDB에 저장
    # source는 원본 파일명으로 유지한다.
    collection.add(
        ids=[f"{target_source}_{i}" for i in range(len(chunks))],
        documents=chunks,
        embeddings=embeddings,
        metadatas=[{
            "source": target_source,
            "format": "pdf",
            "chunk_index": i
        } for i in range(len(chunks))]
    )



def load_vector_store():
    print(f"[INFO] ... Loading Index ...")
    print(f"[INFO] ... Documents from : {settings.doc_source}")
    
    collection_name = settings.collection_name+settings.doc_source
    #print(vectDB_name)
    # ====== Vector DB 존재 확인하고 Indexing 새로 하거나, 기존 Vector DB 로드 ======
    if os.path.exists(os.path.join(settings.persist_dir, "chroma.sqlite3")):
        # ====== Vector DB 존재하면, 기존 인덱스 로드 (from_documents 호출 없이) ======
        vectorstore = Chroma(
            collection_name=collection_name,
            persist_directory=settings.persist_dir,
            embedding_function=embeddings,  # 새 질의를 벡터로 변환할 때 사용할 임베딩 모델
            # 저장된 문서 벡터는 처음 인덱싱할 때 사용한 임베딩 모델 기준으로 만들어졌습니다. 따라서 다시 검색할 때도 같은 임베딩 모델을 사용해야 합니다.
        )
        return vectorstore  #.as_retriever(search_kwargs={"k":3})
    else:
        raise ValueError

def build_retriever(vectorstore):
    return vectorstore.as_retriever(search_kwargs={"k":3}) # k: 가져올 검색 결과 개수, 검색 결과를 항상 List[Document] 형태로 반환한다.
# 내부적으로 저장된 embeddings 객체를 그대로 쿼리 임베딩에도 사용됨


# 프로그램의 시작점일 때만 아래 코드 실행
# 파일이 메인 프로그램으로 사용될 때와 모듈로 사용될 때를 구분하기 위한 용도
if __name__ == '__main__': 
    initial_indexing()

    #vectorstore=load_vector_store()
    #print(vectorstore._collection.count()) # chunk 수가 출력됨. 1248 