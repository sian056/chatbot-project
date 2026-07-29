#chatbot-project/test.py
import argparse

from langchain_core.messages import HumanMessage

BUFFER_SIZE = 5
buffer=[]

def main():
    parser = argparse.ArgumentParser(description="LangChain")
    parser.add_argument('--mode', choices=['smith', 'chain', 'graph', 'multi'], help='Choose mode: LangChain, LangGraph, LangSmith, Multi-Agent')
    args = parser.parse_args()

    print("Hello from rag-project!")
    print(f"{args.mode} mode selected!")

    if args.mode == "smith":
        from src.rag.chain import build_rag_chain
        from src.eval import eval_rag

        rag = build_rag_chain()
        eval_result = eval_rag(rag)
        print("LangSmith Evaluation")
        print(f"{eval_result}")
    
    else:
        # keyword = input("검색하고 싶은 개념을 입력하세요: ")
        # q = f"{keyword}(이)란 무엇인가요?"
        q = input("무엇이 궁금한가요?: ")
        print(f"Sample Question: {q}\n")

        if args.mode == "chain":
            from src.rag.chain import build_rag_chain
            rag = build_rag_chain()
            result = rag.invoke(q)

            print(f"Answer:\n{result}")
            print()
            
        elif args.mode == "graph":
            from src.rag.graph import build_rag_graph
            config = {
                "configurable": {"thread_id":"memory-user-001"},
                "recursion_limit": 25,
            }
            graph = build_rag_graph()

            # 답변 한 번에 invoke
            result = graph.invoke(
                {"messages": [HumanMessage(content=q)]},
                config  # checkpointer 사용중이라 필수
            )
            answer = result["messages"][-1].content
            print(f"Answer:\n{answer}")
            print()

            # 답변에 Streaming 적용
            # print(f"Answer:\n")
            # for chunk, metadata in graph.stream(
            #     {"messages": [HumanMessage(content=q)]},
            #     config,  # checkpointer 사용중이라 필수
            #     stream_mode="messages"
            # ):
            #     if metadata["langgraph_node"]=="generate" and chunk.content:
            #         #print(chunk.content, end='', flush=True) # 한 토큰씩 프린트
            #         buffer.append(chunk.content)    # BUFFER_SIZE 토큰씩 프린트
            #     if len(buffer) >= BUFFER_SIZE:
            #         print("".join(buffer), end="", flush=True)
            #         buffer.clear()
            # print()
            # 문제: 출처 표시가 안됨

            

            #graph visualize
            # graph_view = graph.get_graph()
            # mermaid_text = graph_view.draw_mermaid()
            # print(mermaid_text)

            #graph_view.print_ascii()
        elif args.mode == "multi":
            from src.rag.multi_agent_graph import build_multi_agent_graph
            from src.agents.rag_agent import build_rag_subgraph
            from src.agents.news_agent import build_news_subgraph

            graph = build_multi_agent_graph()
            #graph visualize
            graph_view = graph.get_graph()
            mermaid_text = graph_view.draw_mermaid()
            print(mermaid_text)

            rag_subgraph = build_rag_subgraph()
            rag_subgraph_view = rag_subgraph.get_graph()
            mermaid_text2 = rag_subgraph_view.draw_mermaid()
            print(mermaid_text2)

            news_subgraph = build_news_subgraph()
            news_subgraph_view = news_subgraph.get_graph()
            mermaid_text3 = news_subgraph_view.draw_mermaid()
            print(mermaid_text3)
    
if __name__ == "__main__":
    main()
