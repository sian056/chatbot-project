## Week9
### Update 기록 
| Date | Update 내용 | 파일 |
|:---:|---|:---:|
|260707|Github에서 `.md` 문서 로더 추가|data_loader.py|
|260708|pdf 파일 로더 추가 |data_loader.py|
|260712|pdf 페이지 전처리, 출처 페이지 표시 추가 |data_loader.py, graph.py|
|260712|초기 인덱싱 분리|vector_store.py|

---
### Trouble Shooting
| Date | Problem | Solution| Doc|
|:---:|---|:---|:---:|
|260705|모델 별 응답 형태가 다르고 프롬프트 이해도가 다르다 |모델별 프롬프트 설정|[상세](https://github.com/sian056/chatbot-project/blob/main/docs/trouble-shooting.md#260705)|
|260707|메모리 초과 오류 `Invalid buffer size: 21.98 GiB` |청킹 추가|[상세](https://github.com/sian056/chatbot-project/blob/main/docs/trouble-shooting.md#260707)|
|260712|Mac 파일 시스템(HFS+) 한글 유니코드 정규화 문제|정규화 추가|[상세](https://github.com/sian056/chatbot-project/blob/main/docs/trouble-shooting.md#260712) |

---
### 파일 구조
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
## 회고
### 배운 점
- 청킹의 필요성에 대한 이해  
기존에 내가 작성한 TIL md파일은 길이가 길지 않기 때문에 청킹 과정 없이 문서별로 임베딩하여도 메모리 문제가 발생하지 않았는데 금융용어 사전 pdf로 변경하면서 각 페이지별로 임베딩을 시도한 순간 메모리 초과 오류가 발생하였다. 따라서 청킹이 이런 부분에 있어서 필요함을 깨달았고 또한 청킹없이 단순히 페이지로 나눈다면 맥락이 끊어질 수 있음을 알게 되었다.  
그리고 RAG를 복습하며 임베딩 모델에 따라 최대 입력 토큰이 다르고 그 점을 고려하여 청킹할 토큰 수를 결정해야함을 깨달았다.

### 어려웠던 점
- Agent로 발전시키기  
현재는 문서에서 검색을 하는 기능만 구현되어 있기 때문에 Retriever 부분을 도구화하여 검색하는 부분을 하나의 도구로 만들고, 추후에 다른 기능을 도구로 구현한다면 multi agent로 작동하게 할 수 있을 것 같다. 다만 retriever를 도구화하는 과정에서 어느 부분을 코드 상에서 도구로 구분하여 분리해야 할지 아직 감이 잘 오지 않아서 예제들을 통해 살펴볼 예정이다.
- pdf 문서 전처리  
PyPDF를 이용해 문서를 로드했을 때 수식에 대한 처리를 제대로 못하고 있다는 것을 알게 되었다. 따라서 수식이나 표도 잘 가져오는 pdf 로더로 수정하고자 한다. 더 나아가 pdf파일을 마크다운 형식으로 바꿔 가져온다면 용어와 그에 해당되는 설명을 계층적으로 구분하기가 쉬워질 것 같다.

### 느낀 점
- 교재에서 배운 개념을 코드에 적용시키는 것은 또 다른 문제이다.  
교재 코드를 나의 코드에 적용시키려 할 때 자주 느낀 점은 간소화된 예시로 되어 있는 예제 코드를 실제 코드에 적용시킬 때 괴리감이 생긴다는 것이었다. 이번에 agent화를 시도하며 다시 한 번 괴리감을 느끼게 되었다.

### 개선 방향
- pdf 문서 전처리 개선  
단순히 전처리만으로 해결될 일이 아니고, 수식을 로드하는 부분에 문제가 있기 때문에 로더 자체를 수정할 필요가 있다.
- 청킹 토큰 고민  
임베딩 모델 선택에 있어 스스로 이유를 잘 성립시키고 그 모델에 맞는 청킹 토큰을 선택해야 한다.
- 초기 인덱싱을 한 번만 수행해야 하는데 중복 인덱싱 되지 않도록 수정
- 기능 확장  
경제 용어 문서 검색과 관련하여 어떤 기능을 추가할 수 있을지 고민해야 한다.  
- 현재까지의 설계
    - 상황을 설명하는 문장에서 관련된 금융 용어를 뽑아내는 도구
    - 해당 금융 용어를 바탕으로 문서에서 검색하여 용어 설명해주는 도구
    - 해결책 제시? 