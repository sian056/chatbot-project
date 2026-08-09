# Versions

## 단계별 구현
|ver|목표|달성|
|:---:|---|:---:|
|Ver.1|하나의 그래프인 RAG 시스템|✅|
|Ver.2|RAG 시스템을 하나의 Agent로|✅|
|Ver.3|Multi-Agent : News Agent 추가|✅|
|Ver.3-1|Multi-Agent : 구조 개선|🔜|
|Ver.4|React pattern 적용하여 Tool을 이용해 검색 정확도 높이기|🔜|

---
### Ver.1 하나의 그래프인 RAG 시스템
```mermaid
---
config:
  flowchart:
    curve: linear
---
graph TD;
        __start__([<p>__start__</p>]):::first
        retrieve(retrieve)
        generate(generate)
        __end__([<p>__end__</p>]):::last
        __start__ --> retrieve;
        retrieve --> generate;
        generate --> __end__;
        classDef default fill:#f2f0ff,line-height:1.2
        classDef first fill-opacity:0
        classDef last fill:#bfb6fc
```
---
### Ver.2 Retriever Graph를 하나의 Agent로, Supervisor 추가
`prepare_query` : 전문 agent에서 쿼리를 사용하기 위해 유저의 질문을 저장해두고 넘겨줌.

```mermaid
---
config:
  flowchart:
    curve: linear
---
graph TD;
        __start__([<p>__start__</p>]):::first
        prepare_query(prepare_query)
        supervisor(supervisor)
        __end__([<p>__end__</p>]):::last
        __start__ --> prepare_query;
        prepare_query --> supervisor;
        rag_agent\3agenerate --> supervisor;
        supervisor -.-> __end__;
        supervisor -.-> rag_agent\3arewrite_query;

        subgraph rag_agent["rag_agent(Subgraph)"]
        rag_agent\3arewrite_query(rewrite_query)
        rag_agent\3aretrieve(retrieve)
        rag_agent\3agenerate(generate)
        rag_agent\3aretrieve --> rag_agent\3agenerate;
        rag_agent\3arewrite_query --> rag_agent\3aretrieve;
        end

    
        classDef default fill:#f2f0ff,line-height:1.2
        classDef first fill-opacity:0
        classDef last fill:#bfb6fc

```

---
### Ver.3 Multi-Agent : rag agent, news agent
```mermaid
---
config:
  flowchart:
    curve: linear
---
graph TD;
        __start__([<p>__start__</p>]):::first
        prepare_query(prepare_query)
        supervisor(supervisor)
        __end__([<p>__end__</p>]):::last
        __start__ --> prepare_query;
        news_agent\3asummarize --> supervisor;
        prepare_query --> supervisor;
        rag_agent\3agenerate --> supervisor;
        supervisor -.-> __end__;
        supervisor -.-> news_agent\3arewrite_query;
        supervisor -.-> rag_agent\3arewrite_query;

        subgraph rag_agent["rag_agent(Subgraph)"]
        rag_agent\3arewrite_query(rewrite_query)
        rag_agent\3aretrieve(retrieve)
        rag_agent\3agenerate(generate)
        rag_agent\3aretrieve --> rag_agent\3agenerate;
        rag_agent\3arewrite_query --> rag_agent\3aretrieve;
        end

        subgraph news_agent["news_agent(Subgraph)"]
        news_agent\3arewrite_query(rewrite_query)
        news_agent\3asearch_news(search_news)
        news_agent\3asummarize(summarize)
        news_agent\3arewrite_query --> news_agent\3asearch_news;
        news_agent\3asearch_news --> news_agent\3asummarize;
        end
        classDef default fill:#f2f0ff,line-height:1.2
        classDef first fill-opacity:0
        classDef last fill:#bfb6fc

```
---
### (예정) Ver.3-1 Multi-Agent : rag agent, news agent 구조 개선
```mermaid
---
config:
  flowchart:
    curve: linear
---
graph TD;
        __start__([<p>__start__</p>]):::first
        prepare_query(prepare_query)
        supervisor(supervisor)
        generate_final(generate_final)
        __end__([<p>__end__</p>]):::last
        __start__ --> prepare_query;
        news_agent\3asearch_news --> supervisor;
        prepare_query --> supervisor;
        rag_agent\3aretrieve --> supervisor;
        generate_final -.-> __end__;
        supervisor -.-> generate_final;
        supervisor -.-> news_agent\3akeyword_query;
        supervisor -.-> rag_agent\3aretrieve;
        
        subgraph rag_agent
        rag_agent\3aretrieve(retrieve)
        end
        
        subgraph news_agent
        news_agent\3akeyword_query(keyword_query)
        news_agent\3asearch_news(search_news)
        news_agent\3akeyword_query --> news_agent\3asearch_news;
        end
        
        classDef default fill:#f2f0ff,line-height:1.2
        classDef first fill-opacity:0
        classDef last fill:#bfb6fc

```

#### 고민1
> 검색 정확도 향상을 위해 Retrieve와 리랭킹?

### 어려운 점
수식 로드 &rarr; 금융 계산과 관련 있음

