## Week10
### Weekly Challenge

## 1. 유닉스 환경에서 개인 프로젝트 서버를 실행시킨 뒤, 핵심 명령어로 프로세스·스레드·메모리 상태를 조회하고 그 동작을 분석한 보고서를 작성해 보세요.
과제 : 맥, 또는 리눅스에서 개인 프로젝트 서버 프로그램을 실행하고, 핵심 명령어를 써서 프로세스, 스레드, 메모리 등 상태를 관찰하고, 변화 동작을 분석하여 보고서를 작성해서 회고 문서에 넣으세요. 

1. `ps`
```bash
PID TTY TIME CMD

3677 ttys000 0:00.14 -zsh

4035 ttys000 0:07.96 /Users/.../workspace/chatbot-project/.venv/bin/python /Users/.../workspace/chatbot-project/.venv/bin/uvicorn main:app

4039 ttys000 0:00.03 /Users/.../workspace/chatbot-project/.venv/bin/python -c from multiprocessing.resource_tracker import main;main(15)

3327 ttys001 0:00.08 /bin/zsh

4053 ttys002 0:00.12 -zsh
```

2. `ps -f`

```bash
UID PID PPID C STIME TTY TIME CMD

501 3677 3676 0 1:07오후 ttys000 0:00.14 -zsh

501 4035 3677 0 1:08오후 ttys000 0:09.30 /Users/.../workspace/chatbot-project/.venv/bin/python /Users/.../workspace/chatbot-project/.venv/bin/uvicorn main:app

501 4039 4035 0 1:08오후 ttys000 0:00.03 /Users/.../workspace/chatbot-project/.venv/bin/python -c from multiprocessing.resource_tracker import main;main(15)

501 3327 3303 0 1:03오후 ttys001 0:00.08 /bin/zsh

501 4053 4052 0 1:10오후 ttys002 0:00.14 -zsh
```

3. `ps -ef | grep main.py`

```bash
UID PID PPID C STIME TTY TIME CMD

501 4396 4053 0 1:11오후 ttys002 0:00.01 grep main.py
```

4. `top -pid 4035`

```bash
Processes: 577 total, 4 running, 573 sleeping, 3196 threads 13:17:51

Load Avg: 1.49, 1.65, 2.15 CPU usage: 4.57% user, 3.54% sys, 91.87% idle SharedLibs: 473M resident, 79M data, 65M linkedit.

MemRegions: 0 total, 0B resident, 0B private, 1256M shared. PhysMem: 9864M used (1887M wired, 2179M compressor), 5896M unused.

VM: 273T vsize, 6144M framework vsize, 117157(12) swapins, 425172(0) swapouts. Networks: packets: 1359054/862M in, 322988/73M out.

Disks: 813778/29G read, 679747/15G written.

  

PID COMMAND %CPU TIME #TH #WQ #POR MEM PURG CMPRS PGRP PPID STATE BOOSTS %CPU_ME %CPU_OTHRS UID FAULTS COW MSGS MSGR SYSBSD SYSMA CSW

4035 python3.14 0.2 00:08.64 32 2 124 3916M 0B 868M 4035 3677 sleeping *0[1] 0.00000 0.00000 501 143246 140471 3164 1738 200862+ 11617 66247+
```

---

## 2. WireShark로 개인 프로젝트 서버의 HTTP/HTTPS 통신을 캡처해보세요.
### 1) 로컬 호스트 (서버와 클라이언트가 동일 컴퓨터)
`uvicorn main:app`  
`uvicorn main:app --host 127.0.0.1 --port 8000`과 동일하게 동작.  

1. 루프백 인터페이스 선택
2. `tcp.port == 8000` 필터링 후 캡처 시작 
3. 요청 실행 : 스웨거 문서에서 직접 요청 
4. 캡처 중지
5. 디스플레이 필터 : http 검색 : HTTP 요청/응답 패킷만 필터링됨.

![alt text](<./images/week10_01.png>)

6. POST /query 패킷을 우클릭 -> Follow -> HTTP Stream
- 요청 헤더 전체
- 요청 바디
- 응답 헤더
- 응답 바디 
요청은 빨강, 응답은 파랑

![alt text](<./images/week10_02.png>)

### 2) 서버와 클라이언트가 다른 컴퓨터
`uvicorn main:app --host 0.0.0.0 --port 8000`
1. 서버 컴퓨터의 로컬 네트워크 IP 확인  
`ipconfig getifaddr en0`
2. 두 컴퓨터가 같은 네트워크에 있어야 한다.
3. ***서버 컴퓨터***에서 Wireshark 캡처
- 로컬통신과 달리 실제 네트워크를 타므로 루프백 인터페이스가 아닌 **Wi-Fi 인터페이스** 또는 유선이라면 **Ethernet 인터페이스** 선택  
4. `tcp.port == 8000` 필터링 후 캡처 시작
- 특정 상대방 IP까지 지정하고 싶다면  
`tcp port 8000 and host xxx.xxx.x.xx` 클라이언트 IP 입력
5. 클라이언트 컴퓨터에서 요청 보내기
```
curl -X POST http://192.168.0.3:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "경제성장률이 뭐야?", "thread_id": "test-thread-1"}'
  {"answer":"경제성장률은 일정 기간(분기 또는 연간) 동안 한 나라의 경제 규모, 즉 국민소득 규모가 늘어난 정도를 백분율로 표시한 것입니다.\n\n주요 내용은 다음과 같습니다:\n\n* **정의:** 일정 기간 동안 국가의 경제 규모(국민소득 규모)가 얼마나 증가했는지를 백분율로 나타냅니다.\n* **계산 방식:** 경제성장률은 보통 다음 공식으로 계산됩니다: (금년 실질GDP - 전년 실질GDP) / 전년 실질GDP. 경제성장률은 대부분의 경우 실질GDP 증가율을 의미합니다.\n* **해석:**\n    * 양수(+)이면 실제 경제 지표가 예상보다 호조임을 의미합니다.\n    * 음수(-)이면 예상보다 부진함을 의미합니다.\n\n또한, 국민소득(실질GDP)은 각 경제활동 부문에서 창출해낸 실질 부가가치의 합계로 표현됩니다. 따라서 경제성장률은 실질 GDP의 증가율을 나타냅니다.\n\n[출처] 15 페이지,388 페이지","thread_id":"test-thread-1"}%
```
6. 캡처 결과 확인

![alt text](<./images/week10_03.png>)

![alt text](<./images/week10_04.png>)


## Weekly Challenge 회고
### 배운 점
- 항상 호스트랑 포트 주소 없이 uvicorn main:app 으로만 실행해왔어서 기본 주소가 --host 127.0.0.1 --port 8000 인 것을 알게 되었다. 그렇기 때문에 여태껏 localhost:8000 으로 접속 가능하다는 것을 깨달았다. 
- 루프백 : 로컬 통신은 실제 네트워크 카드를 거치지 않고 루프백 인터페이스를 통해서만 오간다.
- 서버와 클라이언트 컴퓨터가 다를 시, 클라이언트 컴퓨터에서 요청을 보낼때는 스웨거 문서 링크로 직접 접속이 되지 않는다.(?)  
=> 확인 필요
- HTTP 평문 노출 위험 : 같은 네트워크의 누구나 스니핑 가능하다는 위험이 있다.
