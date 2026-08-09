import time, datetime

# 시간 출력
def format_elapsed(st_time: float) -> str:
    """
    경과 시간을 "H:MM:SS.ss" 형태(마이크로초 2자리까지)로 반환한다.
    """
    elapsed = str(datetime.timedelta(seconds=time.time()-st_time))
    if "." in elapsed:  # 마이크로초까지 포함이 되어있다면
        elapsed = elapsed[:elapsed.index(".") +3]
    return elapsed

# string으로 변환
def extract_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in content
        )
    return str(content)

# 대화 이력 출력
def print_messages(label:str, messages:list)-> None:
    """
    messages 대화이력 리스트를 한눈에 보기 쉬운 형태로 출력한다.
    """
    print(f"\n[MSG STATE] {label} (총 {len(messages)}개)")
    for i, m in enumerate(messages):
        n_type = type(m).__name__
        name = getattr(m, "name", None)
        content = str(getattr(m, "content", ""))
        preview = content[:50] +("..." if len(content)>50 else "")
        print(f"    [{i}] {n_type} : {name} - {preview!r}")