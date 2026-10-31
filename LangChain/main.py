"""KANT NEXT DevDesk. todo(...)를 필요한 표현이나 코드로 바꿉니다."""
import copy # metadata의 중첩 값까지 복사해 원본 자료를 보호
import json # 원본에서 제공된 JSON 모듈
import sys # 현재 main 모듈을 support의 실행 진입점에 전달
import time # 실행 단계별 경과 시간을 측정

# LangChain: 실행 과정과 오류 기록 
from langchain_core.callbacks import BaseCallbackHandler
# 사용자별 대화 기록 저장
from langchain_core.chat_history import InMemoryChatMessageHistory
# 검색할 문서의 본문과 메타데이터 관리
from langchain_core.documents import Document

# AI와 사용자 메시지 생성
from langchain_core.messages import AIMessage, HumanMessage
# AI 응답을 정해진 데이터 형식으로 변환
from langchain_core.output_parsers import PydanticOutputParser
# 프롬프트 구성 및 이전 대화 삽입 
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

# Branch: 조건 분기 / Lambda: 함수 연결 / Parallel: 병렬 처리 / Passthrough: 입력 보존
from langchain_core.runnables import (
    RunnableBranch,            # 조건에 따라 실행 경로 선택    
    RunnableLambda,            # 일반 함수를 체인에 연결
    RunnableParallel,          # 여러 작업을 병렬 실행
    RunnablePassthrough,       # 입력 데이터 유지 및 전달 
)

import support

# 앞 과제의 B2를 가져온다면 정책 지침만 사용합니다. 문서는 context로 전달합니다.
POLICY_INSTRUCTIONS = support.B1_POLICY
POLICY_SOURCE = "B1"


def todo(description):
    """제공: 빈칸을 실행하면 작성할 내용을 알려 줍니다. 이 함수는 수정하지 않습니다."""
    raise NotImplementedError(description)


# 필수 1: 문서 검색

# 원본 데이터를 LangChain Document 객체로 변환
def to_documents(rows, keywords):
    """문서 변환: 본문과 metadata를 나눈 Document를 만듭니다."""
    documents = []
    for row in rows:

        # 본문은 page_content로, 식별자, 제목, 출처 등은 metadata로 분리
        metadata = {key: copy.deepcopy(value) for key, value in row.items() if key != "body"}
        
        # 별도 키워드가 없는 릴리스 문서에는 기본 검색어를 붙임
        defaults = ["uv", "릴리스", "release"] if row["category"] == "release" else []
        metadata["keywords"] = list(keywords.get(row["doc_id"], defaults))
        document = Document(page_content=row["body"],
                            metadata=metadata)
        documents.append(document)
    return documents


# 허용된 문서에서 키워드가 일치하는 상위 문서 검색 
def search_documents(query, documents, allowed_ids, top_k=3):
    """키워드 검색: 후보를 제한하고 일치한 키워드 수로 검색합니다."""
    if type(top_k) is not int or not 1 <= top_k <= 3:
        raise ValueError("top_k는 1~3의 정수입니다.")
    normalized = query.casefold()
    allowed = set(allowed_ids)
    scored = []

    # 허용된 후보를 먼저 걸러 검색 순위에 다른 문서가 섞이지 않게 함 
    for index, document in enumerate(documents):
        if document.metadata["doc_id"] not in allowed:
            continue
        words = {word.casefold() for word in document.metadata.get("keywords", []) if word.strip()}

        # 대소문자와 중복 키워드의 영향을 제거하 뒤 부분 문자열 일치를 센다. 
        score = sum(word in normalized for word in words)
        if score > 0:
            scored.append((score, index, document))

    # 같은 점수는 원본 문서 순서를 유지 
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in scored[:top_k]]


# 검색된 문서를 AI  프롬프트에 사용할 문자열로 변환
def format_context(documents):
    """제공: 검색 문서를 제목, 출처, 본문으로 표시합니다."""
    if not documents:
        return "검색된 문서가 없습니다."
    return "\n\n".join(
        f'<document id="{doc.metadata["doc_id"]}">\n'
        f'제목: {doc.metadata["title"]}\n출처: {doc.metadata["source_url"]}\n'
        f'{doc.page_content}\n</document>' for doc in documents)


# 원본 입력을 유지하면서 문서 검색과 Context 생성을 연결 
def build_context_chain(documents):
    """검색 입력 연결: 입력 보존과 검색을 병렬로 연결합니다."""
    # 작성 이유: 입력 보존과 검색을 나누는 이유를 한두 줄로 적으세요.
    def retrieve(value):

        # 후속 질문의 대상을 파악하도록 질문과 이전 대화로 검색어를 만듦
        query = support.search_query(value["question"],
                                      value["history"])
        return search_documents(query, documents, value["document_ids"])

    def merge(value):

        # 원래 입력에 검색 문서 객체와 프롬프트용 문자열을 함께 추가 
        return {**value["original"], "documents": value["documents"],
                "context": format_context(value["documents"])}

    preserve = RunnablePassthrough().with_config(run_name="preserve_input")
    retrieve_chain = RunnableLambda(retrieve).with_config(run_name="retrieve")
    parallel = RunnableParallel(original=preserve,
                                documents=retrieve_chain)
    return parallel.with_config(run_name="parallel_prepare") | RunnableLambda(merge).with_config(run_name="merge_context")


# 필수 2: 기본 체인

# AI에게 전달할 프롬프트와 응답 변환기 생성 
def build_prompt_and_parser():
    """프롬프트와 파서: 답변 형식과 이전 대화 자리를 연결합니다."""

    # 시스템 정책, 이번 검색 문서 -> 이전 대화 -> 현재 질문 순서로 전달 
    parser = PydanticOutputParser(pydantic_object=support.Answer)
    prompt = ChatPromptTemplate.from_messages([
        ("system", "{policy}\n\n출력 형식:\n{format_instructions}\n\n이번 검색 문서:\n{context}"),
        MessagesPlaceholder(variable_name="history"),
        ("human", "{question}"),
    ]).partial(policy=POLICY_INSTRUCTIONS, format_instructions=parser.get_format_instructions())
    return prompt.with_config(run_name="prompt"), parser.with_config(run_name="parser")


# AI 답변의 출처가 실제 검색 문서에 포함되는지 검사 
def validate_sources(answer, documents):
    """출처 검사: 이번에 검색한 문서만 출처로 허용합니다."""
    answer = support.Answer.model_validate(answer)
    allowed = {document.metadata["doc_id"] for document in documents}

    # 출저 중복, 검색 밖 출처, 근거 없는 자동 확정 답변을 거부 
    if len(answer.source_ids) != len(set(answer.source_ids)):
        raise support.SourceValidationError("출처가 중복됩니다.")
    if any(source_id not in allowed for source_id in answer.source_ids):
        raise support.SourceValidationError("이번 검색 결과에 없는 출처입니다.")
    if not answer.source_ids and not answer.needs_human:
        raise support.SourceValidationError("근거 없는 답변에는 담당자 확인이 필요합니다.")
    return answer

# 프롬프트 -> 모델 -> 파서 -> 출처 검증 순서로 연결 
def build_primary_chain(model):
    """기본 체인 연결: prompt, model, parser와 출처 검사를 연결합니다."""
    prompt, parser = build_prompt_and_parser()

    # | 연산자는 앞 단계의 출력을 다음 단계의 입력으로 연결 
    generate = prompt | model | parser

    def finish(value):
        answer = validate_sources(value["parsed"], value["documents"])
        return {"reply": answer, "route": "primary"}

# 원래 documents를 보존해야 생성 결과의 실제 검색 출처를 비교할 수 있다. 
    return (RunnablePassthrough.assign(parsed=generate.with_config(run_name="generate_parse"))
            | RunnableLambda(finish).with_config(run_name="validate_sources")).with_config(run_name="primary")

# 검색 문서 유무에 따라 AI 호출 여부 결정 
def build_answer_chain(model, reliable=False):
    """문서 없음 분기: 문서가 없으면 모델을 호출하지 않습니다."""
    primary = build_primary_chain(model)
    if reliable:
        primary = build_resilient_chain(primary)

    # 근거 문서가 없으면 모델을 호출하지 않고 고정된 안내를 반환
    no_documents = RunnableLambda(lambda value: {"reply": support.safe_answer("no_documents"),
                                                "route": "no_documents"})
    def has_no_documents(value):
        return not value["documents"]
    return RunnableBranch((has_no_documents, no_documents), primary).with_config(run_name="route_by_documents")


# 필수 3: 대화 이력

# 세션 ID를 기준으로 사용자별 대화 기록 조회 및 생성 
def get_history(store, session_id):
    """세션 이력: 세션마다 별도의 이력 객체를 보관합니다."""
    if not isinstance(session_id, str) or not session_id.strip():
        raise ValueError("session_id는 비어 있지 않은 문자열입니다.")
    if session_id not in store:

        # 사용자 세션끼리 대화가 섞이지 않도록 별도 이력 객체를 만듦
        store[session_id] = InMemoryChatMessageHistory()
    return store[session_id]


# 정상 처리된 질문과 AI 답변을 대화 기록에 저장 
def commit_history(store, session_id, question, outcome):
    """이력 저장: 완료된 primary의 질문과 답변만 저장합니다."""
    # 작성 이유: 검색 문서와 대화 이력을 구분하고 primary만 저장하는 이유를 적으세요.
    if outcome["route"] != "primary":
        return
    answer = support.Answer.model_validate(outcome["reply"])
    messages = [HumanMessage(content=question),
                AIMessage(content=answer.answer)]

    # 검색 문서나 JSON 전체 대신 질문과 답변 본문만 순서대로 저장 
    get_history(store, session_id).add_messages(messages)


# 필수 4: 실패 복구

# 복구 가능한 오류 발생 시 재시도하고 실패하면 대체 답변 반환
def build_resilient_chain(primary):
    """실패 복구: 허용 오류에만 처음을 포함해 최대 두 번 시도합니다."""
    retry = primary.with_retry(retry_if_exception_type=support.RECOVERABLE,
                               stop_after_attempt=2, wait_exponential_jitter=False)
    fallback = RunnableLambda(lambda value: {"reply": support.safe_answer("fallback"),
                                            "route": "fallback"}).with_config(run_name="fallback")
    return retry.with_fallbacks([fallback], exceptions_to_handle=support.RECOVERABLE)

# AI 응답을 실시간으로 전달하고 최종 답변을 검증 
def stream_answer(prepared, model, config=None):
    """청크 전달: 아래 순서대로 청크 전달, 검증과 실패 분기를 채웁니다."""
    # 관측 메모: 실행 기록에서 확인한 실패 단계와 처리 결과를 한두 줄로 적으세요.
    if not prepared["documents"]:
        yield {"type": "final", "reply": support.safe_answer("no_documents").model_dump(), "route": "no_documents"}
        return
    prompt, parser = build_prompt_and_parser()
    stream_chain = prompt | model
    sent_delta = False
    for attempt in range(2):
        iterator = stream_chain.stream(prepared, config=config)
        parts = []
        try:
            for chunk in iterator:
                text = support.message_text(chunk)
                if text:

                    # delta는 아직 검증되지 않은 조각이며, 끝까지 모아 최종 검사를 한다.
                    parts.append(text)
                    sent_delta = True
                    yield {"type": "delta", "text": text}

            # 모든 조각을 합친 뒤 스키마와 출처가 유효해야 final primary를 보낸다.
            parsed = parser.invoke("".join(parts), config=config)
            answer = validate_sources(parsed, prepared["documents"])
            yield {"type": "final", "reply": answer.model_dump(), "route": "primary"}
            return
        except support.RECOVERABLE:

            # 조각을 보내기 전 첫 실패만 재시도하고, 이후 실패는 안전 안내로 종료합니다. 
            if not sent_delta and attempt == 0:
                continue
            if sent_delta:

                # 이미 표시한 미검증 내용을 화면에서 지우도록 소비자에게 알립니다. 
                yield {"type": "reset", "reason": "unverified_output"}
            yield {"type": "final", "reply": support.safe_answer("fallback").model_dump(), "route": "fallback"}
            return
        except Exception:
            if sent_delta:
                # 코드 오류 등 복구 대상 밖에 오류는 화면 초기화 후 호출자에게 전달 
                yield {"type": "reset", "reason": "execution_error"}
            raise
        finally:
            # 제공: 정상, 실패, 소비 중단 모두에서 하위 스트림을 닫습니다.
            iterator.close()

# LangChain 실행 시간, 토큰 청크, 오류 및 사용량 기록 
class TraceHandler(BaseCallbackHandler):
    """실행 기록: 잠금, 상태 보관과 기록 형식은 제공됩니다. 측정할 값만 채웁니다."""
    raise_error = True

    # 게록 환경 및 실행 상태 초기화
    def __init__(self, mode="fixture", path=None, clock=time.perf_counter):
        self.mode = mode
        self.clock = clock
        self.sink = support.TraceSink(path)
        self.records = self.sink.records

        # run_id별 진행 상태를 보관해 병령 실행의 측정값을 구분 
        self.active = {}
        self.model_attempts = 0

    # 체인 또는 모델의 실행 시작 시간과 상태 기록 
    def _start(self, kind, run_id, parent_run_id, name):

        # 병령 콜백이 공유 상테를 동시에 바꾸지 않도록 잠금 안에서 기록한다. 
        with self.sink.lock:
            key = str(run_id)
            state = {"started": self.clock(),
                     "stage": support.safe_stage(name),
                     "parent_run_id": str(parent_run_id) if parent_run_id else None, "chunk_count": 0}
            self.active[key] = state
            if kind == "model":
                self.model_attempts += 1
            self.sink.write({"event": f"{kind}_start", "stage": state["stage"], "run_id": key,
                             "parent_run_id": state["parent_run_id"], "mode": self.mode,
                             "elapsed_ms": 0.0, "chunk_count": 0, "usage": None, "error_type": None})


    # 실행 종료 시간, 오류 및 토큰 사용량 기록 
    def _finish(self, kind, run_id, error=None, usage=None):
        with self.sink.lock:
            key = str(run_id)
            state = self.active.pop(key, None)
            if state is None:
                return
            elapsed_ms = (self.clock() - state["started"]) * 1000

            # 오류 원문 대신 종류만 남겨, 입력, 응답 내용이 기록이 섞이지 않게 한다. 
            error_type = type(error).__name__ if error is not None else None
            self.sink.write({"event": f"{kind}_{'error' if error is not None else 'end'}",
                             "stage": state["stage"], "run_id": key,
                             "parent_run_id": state["parent_run_id"], "mode": self.mode,
                             "elapsed_ms": max(0.0, elapsed_ms), "chunk_count": state["chunk_count"],
                             "usage": usage, "error_type": error_type})

    # AI가 생성한 텍스트 청크의 개수와 처리 시간 기록 
    def on_llm_new_token(self, token, *, run_id, parent_run_id=None, **kwargs):
        text = support.message_text(token)
        if not text:
            return
        with self.sink.lock:
            state = self.active.get(str(run_id))
            if state is None:

                # 사용량 정보만 담긴 빈 청크는 텍스트 청크 수에 포함하지 않습니다. 
                return
            state["chunk_count"] = state["chunk_count"] + 1
            self.sink.write({"event": "model_chunk", "stage": state["stage"], "run_id": str(run_id),
                             "parent_run_id": state["parent_run_id"], "mode": self.mode,
                             "elapsed_ms": max(0.0, (self.clock() - state["started"]) * 1000),
                             "chunk_count": state["chunk_count"], "usage": None, "error_type": None})

    # 제공: LangChain 이벤트를 위 세 메서드에 연결합니다.

    # 체인 실행 시작 이벤트 처리 
    def on_chain_start(self, serialized, inputs, *, run_id, parent_run_id=None, **kwargs):
        self._start("chain", run_id, parent_run_id, kwargs.get("name", "chain"))

    # 체인 실행 완료 이벤트 처리 
    def on_chain_end(self, outputs, *, run_id, **kwargs):
        self._finish("chain", run_id)

    # 체인 실행 중 발생한 오류 기록 
    def on_chain_error(self, error, *, run_id, **kwargs):
        self._finish("chain", run_id, error=error)

    # AI 모델 호출 시작 이벤트 처리 
    def on_chat_model_start(self, serialized, messages, *, run_id, parent_run_id=None, **kwargs):
        self._start("model", run_id, parent_run_id, "model")

    AI 모델 응답 완료 및 토큰 사용량 기록 
    def on_llm_end(self, response, *, run_id, **kwargs):
        self._finish("model", run_id, usage=support.extract_usage(response))

    # AI 모델 호출 중 발생한 오류 기록 
    def on_llm_error(self, error, *, run_id, **kwargs):
        self._finish("model", run_id, error=error)


# 선택 심화 1: 초안 검토
def review_draft(draft, documents, reviewer, rewriter):
    """선택 심화: 필수에서 만든 검증을 재사용해 검토, 한 번 수정, 재검토 흐름을 설계합니다."""
    raise NotImplementedError("선택 심화: review_draft를 구현하세요.")


if __name__ == "__main__":
    raise SystemExit(support.main(sys.modules[__name__]))
