## Week11
## Weekly Challenge
### 1. 지금까지 구축한 개인 프로젝트를 Docker 컨테이너로 패키징하고 Docker Compose로 실행해보세요.
#### Step 1 : Docker Image 생성
> 맥 os 환경 : 개인 프로젝트 폴더
1. Dockerfile 작성
```
FROM python:3.14-slim

# uv 바이너리 가져오기
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# 의존성 정의 파일만 먼저 복사 (레이어 캐시 최적화)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# 나머지 소스 코드 전체 복사 (src/, main.py, test.py 등)
COPY . .

RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```
2. `.dockerignore` 작성
3. `docker build -t chatbot-project`  
`docker build --platform linux/amd64 -t chatbot-project`  
EC2 인스턴스가 amd64이기 때문에 맞춰줘야 한다.

#### Step 2 : 만든 이미지를 Docker Compose로 실행
> 맥 os 환경 : 개인 프로젝트 폴더
1. docker-compose.yml 작성
```
services:
  chatbot-project:
    build: .
    image: chatbot-project
    ports:
      - "8000:8000"
    env_file:
      - .env
    volumes:
      - ./chroma_db:/app/chroma_db
    environment:
      - OLLAMA_BASE_URL=http://host.docker.internal:11434
    extra_hosts:
      - "host.docker.internal:host-gateway"  # Linux에서 필요
```
2. docker compose up 실행 시 서버 시동까지 자동으로 됨.

### 실행 결과
정상적으로 작동함을 확인. 

### Trouble Shooting
#### 문제 상황 1
올라마 사용시 주소 설정을 바꿔줘야한다.
```
services:
  chatbot-project:
    build: .
    environment:
      - OLLAMA_BASE_URL=http://host.docker.internal:11434
    extra_hosts:
      - "host.docker.internal:host-gateway"  # Linux에서 필요
```

#### 문제 상황 2
도커 이미지 파일이 너무 크다 9.2GB
```
docker run --rm -it chatbot-project sh -c "du -sh /app/.venv/lib/python3.14/site-packages/* 2>/dev/null | sort -rh | head -15"
2.9G	/app/.venv/lib/python3.14/site-packages/nvidia
```
-> linux/amd64 로 빌드하니까 왜 3.2GB 됐지...
-> 9.2GB를 도커 허브에 올렸을때도 3.xGB 였던것같은데.
-> 그래도 크다

---
### 2. 개인 프로젝트의 컨테이너 이미지를 AWS EC2에 배포하고 외부에서 접근 가능하도록 구성해보세요.
### Steps
#### Step 1 : Docker Image를 Docer Hub에 올린다.
> 맥 os 환경
1. 도커 허브 로그인 `docker login -u <username>`
2. 이미지에 태그 달기 `docker tag chatbot-project:latest <username>/chatbot-project:latest`
3. `docker push <username>/chatbot-project:latest`

#### Step 2 : AWS EC2에서 도커 이미지를 받아 실행한다.
> EC2 환경 : Docker 설치 해야함
1. 프로젝트 폴더 생성 `mkdir chatbot-docker`, `cd chatbot-docker`
2. docker-compose.yml 작성
```
services:
  chatbot-project:
    image: <username>/chatbot-project:latest   # build 대신 image만 사용
    ports:
      - "8000:8000"
    env_file:
      - .env
    volumes:
      - ./chroma_db:/app/chroma_db
```
3. .env 작성  
EC2에서 Ollama 사용하려면 다시 설치해야하므로 gemini로 테스트
4. `docker compose up`

#### 문제상황
```
 ⠦ Image <username>/chatbot-project:latest [⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿] 3.142GB / 3.152GB Pulling                162.7s
failed to extract layer (application/vnd.oci.image.layer.v1.tar+gzip sha256:...) to overlayfs as "extract-...": write /var/lib/containerd/io.containerd.snapshotter.v1.overlayfs/snapshots/8/fs/app/.venv/lib/python3.14/site-packages/nvidia/cu13/lib/libcublasLt.so.13: no space left on device
```
디스크 용량 부족

---
### 3. Github Actions를 활용해 코드 푸시 시 자동으로 개인 프로젝트가 빌드, 배포되는 CI/CD 파이프라인을 구축해보세요.

---
### 4. (선택) 빅뱅 배포

### Week 11 Weekly Challenge 회고

---
## Week 11 개인 프로젝트 진행
### Update 기록 
| Date | Update 내용 | 파일 |
|:---:|---|:---:|
|260727|supervisor-agent 구조: 2개 agent구성|agents/|

### 개인 프로젝트 회고
#### 알게 된 점
- 멀티턴 실행 시 사용자가 메시지를 보낼 때마다 invoke()를 새로 호출하기 때문에 그래프가 START부터 다시 돈다.
  - 같은 스레드인 것을 알고 불러오는 과정에 대해 알아야한다.
  - supervisor 노드의 메시지를 누적하지 않으면 supervisor의 여러번의 판단을 추적할 수 없게 된다.
- Orchestration Pattern
  - Supervisor가 판단을 내릴 때 고려해야할 점
    - 무한루프에 빠지지 않도록 상한선을 두기.
    - 판단 결정이 Rule-base인 것이 적합할 수도 있으니 비교해보기.(현재는 StructuredOutput으로 구현되어있음)
- 단순히 모든 상황에 대해 정답인 그래프 구조란 것은 없고 어떤 질문이 들어올 지 예상을 해서 그것에 맞춰 실용적인 구조를 선택해가야 한다.
- 서브그래프에 대한 이해
  - 서브그래프를 상위 그래프의 노드로 등록하여 사용할 때 유의미한 목적이 있어야 사용 이유가 된다.
  - 서브그래프의 재사용성 등을 고려해서 구조를 왜 이렇게 구현하였는가에 대해 스스로 고민해봐야한다.

#### 적용해볼 점
- Plan-and-Execute pattern을 적용해서 Orchestration 과 비교하기

