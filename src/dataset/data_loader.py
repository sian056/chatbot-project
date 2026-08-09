#src/datset/data_loader.py
import requests, os, urllib
from glob import glob
from pathlib import Path

from langchain_core.documents import Document

from src.settings import settings

#load_dotenv()   # .env 파일을 읽어서 os.environ에 등록

def chunking(docs):
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50,
    )
    split_docs = splitter.split_documents(docs)
    print(f"[INFO] ... Number of chunks: {len(split_docs)}")

    return split_docs

def load_md():
    from langchain_community.document_loaders import TextLoader
    md_paths = sorted(glob(settings.md_path))
    md_docs = []
    for p in md_paths:
        md_docs.extend(TextLoader(p, encoding="utf-8").load())
    docs = md_docs
    print(f"[INFO] [FROM MD LIST] ... Number of Loaded Documents : {len(docs)}")

    return docs

def load_html():
    pass

def preprocess_pdf(docs):

    if "경제금융" in settings.pdf_name:
        docs = docs[18:]    #0~17번 문서까지는 목차라서 제거
        docs = docs[:-5]    #마지막 다섯개 문서 제거
        
        # for idx, doc in enumerate(docs):
        # # 기존 페이지 저장해두기
        #     doc.metadata["source_page"] = doc.metadata["page"]+1 # 0부터 시작되기 때문에 pdf viewer에 표시되는 것과 같게 1부터 시작되게 바꿈
        # # 페이지 번호 다시 매기기
        #     doc.metadata["page"] = idx+1

    print(f"[INFO] [AFTER PDF PREPROCESSING] ... Number of Documents : {len(docs)}")
    return docs
    
def load_pdf():
    from langchain_community.document_loaders import PyPDFLoader
    if not os.path.exists(settings.pdf_path):
        urllib.request.urlretrieve("https://raw.githubusercontent.com/sian35/chatbot-project/main/2026_%EA%B2%BD%EC%A0%9C%EA%B8%88%EC%9C%B5%EC%9A%A9%EC%96%B4_800%EC%84%A0.pdf", filename=settings.pdf_path)
        print(f"[INFO] Successfully downloaded {settings.pdf_path}")

    pdf_loader = PyPDFLoader(settings.pdf_path)
    # === 모든 페이지를 한 번에 ===
    docs = pdf_loader.load()
    print(f"[INFO] [FROM PDF] ... Number of Loaded Documents : {len(docs)}")
    # === 메모리 효율을 위해 페이지를 하나씩 yield하는 제너레이터를 반환
    # for doc in pdf_loader.lazy_load():
    #     print(doc.metadata["page"], doc.page_content[:50])
    if "경제금융" in settings.pdf_name: # NFC,NFD 문제 주의
        docs = preprocess_pdf(docs)

    return docs

def load_dir():
    """디렉토리 안의 모든 *.md 파일을 Document로 로드"""
    from langchain_community.document_loaders import TextLoader, DirectoryLoader
    md_loader = DirectoryLoader(
        path=settings.md_dir_path,
        glob="*.md", # 하위 폴더 포함: "**/*.md"
        loader_cls=TextLoader,
        loader_kwargs={"encoding": "utf-8"}
    )

    md_docs = md_loader.load()
    print(f"[INFO] [FROM DIRECTORY] ... Number of Loaded Documents : {len(md_docs)}")

    return md_docs

# Example
# GitHub repo to index *.md notes from (default: 100-hours-a-week/alex-notes)
# GITHUB_REPO=100-hours-a-week/alex-notes
# GitHub token for accessing the notes repo (needed if it is private)
# GITHUB_TOKEN=your-github-token
# Load Github MD documents

def fetch_from_github():
    """GitHub 저장소의 모든 *.md 파일을 Document로 로드"""
    # ==== 1. 인증 헤더 준비 ====
    headers = {
        "Accept": "application/vnd.github+json", # GitHub REST API의 응답형식을 JSON으로 지정하는 표준 헤더
        "X-GitHub-Api-Version": "2022-11-28",   # GitHub API의 버전을 고정
    }
    token = settings.github_token
    if token:   # token이 있을 때만 Authorization 헤더를 추가
        headers["Authorization"] = f"Bearer {token}"

    # ==== 2. 저장소 기본 정보 조회 (기본 브랜치 확인) ====
    api_base = f"https://api.github.com/repos/{settings.github_repo}"
    repo_res = requests.get(api_base, headers=headers, timeout=30)  # GitHub의 저장소 정보 조회 엔드포인트 호출. 저장소의 메타 데이터 반환
    repo_res.raise_for_status() # HTTP 상태 코드가 4xx/5xx(에러)면 즉시 예외 발생
    branch = repo_res.json()["default_branch"]  # 응답 JSON에서 기본 브랜치명(main or master)을 꺼낸다.

    # ==== 3. 저장소 전체 파일 트리 조회 ====
    # GitTrees API 호출 : 이 브랜치의 특정 커밋 시점에 있는 전체 파일/폴더 구조를 반환하는 API
    tree_res = requests.get(
        f"{api_base}/git/trees/{branch}?recursive=1", headers=headers, timeout=30
    )   # ?recursive=1 : 모든 하위 폴더까지 재귀적으로 펼쳐진 전체 파일 목록을 한 번에 받는다.
    tree_res.raise_for_status()

    # ==== 4. .md 파일만 필터링하며 순회
    docs = []
    for entry in tree_res.json()["tree"]:
        # blob(폴더)이거나 .md가 아니라면(README.md도 건너뜀) 건너뛴다.
        if entry["type"] != "blob" or not entry["path"].endswith(".md") or entry["path"].endswith("README.md") or ("subnotes" in entry["path"]) or ("template" in entry["path"]):
            #print(f"{entry["path"]} passed")
            continue
        
        #src_name = f"{Path(entry['path']).parent.name}/{Path(entry['path']).name}"
        #print(src_name)
        # === API 호출 횟수가 많아서 수정 ===
        # 각 파일의 실제 텍스트 내용을 가져오려면 Contents API를 파일마다 개별 호출한다.
        '''
        file_res = requests.get(
            f"{api_base}/contents/{entry['path']}?ref={branch}",
            headers={**headers, "Accept": "application/vnd.github.raw+json"},   # 딕셔너리 언패킹 문법: 기존 headers(인증 정보 등)를 그대로 복사하면서, "Accept" 키만 새 값으로 덮어쓴다.
            timeout=30,                                                         # raw: Contents API는 기본적으로 Base64로 인코딩된 JSON으로 반환하는데 이렇게 지정하면 인코딩 없이 원본 텍스트(raw)를 그대로 응답.
        )
        '''

        # === API 호출 대신 Raw URL로 접근 (Rate Limit 소비 없음) (용량이 커짐..?)
        # URL 구조 https://raw.githubusercontent.com/{유저명}/{저장소명}/{브랜치명}/{파일경로}
        raw_url = f"https://raw.githubusercontent.com/{settings.github_repo}/{branch}/{entry['path']}"
        file_res = requests.get(raw_url, timeout=30)    # headers 불필요

        
        file_res.raise_for_status()

        # ==== 5. Document 객체로 감싸기
        docs.append(
            Document(
                page_content=file_res.text, # raw 형식으로 받았기 때문에, 응답 본문이 마크다운 원문 텍스트이다.
                metadata={"source": entry["path"]}, # 춡처 정보: 상위폴더/파일명 (파일명 중복 대비) :: settings.github_repo}/{entry['path'] 저장소명/파일경로
            )
        )

    return docs


def load_github(use_cache = True) -> list[Document]:
    # 캐시가 있으면 GitHub 호출 없이 바로 반환

    docs = fetch_from_github()

    print(f"[INFO] [FROM GITHUB] ... Number of Loaded Documents : {len(docs)}")
    return docs





