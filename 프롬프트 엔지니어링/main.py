"""KANT NEXT DevDesk. 정책 프롬프트부터 _todo(...) 한 곳씩 바꾸세요.

시작: uv run --frozen python main.py demo
확인: uv run --frozen python main.py check policy
실제 호출: uv run --frozen python main.py run policy --live

반복문, 파일 처리, 로그 형식은 준비되어 있습니다.
_todo(...)를 값, 조건식 또는 함수 호출로 바꾸면 해당 부분이 실행됩니다.
설명 주석에는 선택 이유를 1~2문장 남기세요. 별도 문서는 만들지 않습니다.
"""
import copy          # 중첩된 dict.list까지 복사하여 원본 요청과 티켓을 보호
import hashlib       # 지시문에서 일정한 해시값을 계산  
import json          # JSON 문자열과 파이썬 dict·list를 서로 변환
import re            # 정규식으로 티켓 번호의 문자열 형식을 검사
import time          # 전송 대기와 처리 시간 측정에 사용 

# JSON Schema는 JSON 데이터의 필수 필드, 자료형, 허용값을 정의하는 규칙
from jsonschema import Draft202012Validator, ValidationError

# 프로젝트에서 제공하는 공통 기능: API 전송 보조, 로그, 이미지 변환, 명령행 실행 등
import support

# 미구현된 기능을 오류로 알린다.
def _todo(label):
    raise NotImplementedError(label)


# 필수 1 / 정책 프롬프트. 문자열 두 개를 작성합니다.
# 사내 문서와 정책으로 AI 지시문 생성

def build_instructions(documents, variant):
  """문서 목록과 실험 유형을 받아 모델에 전달할 지시문 문자열을 만든다.

  documents: 각 항목에 doc_id가 있는 사내 문서 목록
  variant: baseline은 기본 정책, reasoning은 근거, 제약 점검 지시를 추가
  반환값: 공통 정책과 참고 문서 JSON을 합친 문자열
  """

  # 지원하지 않는 이름을 조용히 처리하지 않고 즉시 오류로 알려 오타를 발견한다. 
  # 이 함수의 정책 차이는 reasoning의 추가 점검 지시
  # support.base_request는 reasoning.effort도 baseline=none, reasoning=low로 바꾼다.
  # 따라서 두 조건의 결과 차이를 프롬프트 문구 하나의 효과만으로 해석하면 안된다.
  # support.sample_answer에는 policy-python이 나오지만 실제 허용 출처는 documents의 doc_id이다. 
    if variant not in {"baseline", "reasoning"}:
        raise ValueError("variant는 baseline 또는 reasoning입니다.")
    
    # 이유: Few-shot은 사내 문서와 티켓을 활용한 예시로 문의를 구분하고 근거를 표시하는 방법을 알려줄 때 사용하며, 
    # Self-Consistency는 같은 문의에 대한 풀이를 여러 번 생성한 뒤 가장 많이 나온 최종 답을 선택하는 방식이다.
    
    # 왜 Reasoning을 쓰나?: 확인된 사실과 아직 확인되지 않은 사실을 구분하기 위해서 사용합니다.  
    # 한계: 정보부족, 근거 자체의 오류, 판단 과정의 실수입니다, 
    # Reasoning은 주어진 근거를 활용하는 데 도움을 주지만, 
    # 부족한 사실을 대신 만들어 주거나 정답을 보장하지는 않는다. 

    #policy = _todo("정책 프롬프트: 역할, 업무 범위, 근거, 비밀정보, 담당자 확인, 답변 형식을 담은 문자열")
    policy = """
    역할: 기업 개발팀의 개발환경 및 장애문의에 답하는 지원 담당자 
    업무 범위: 개발환경 및 장애 문의에 답하며, Python 버전 문의는 policy_python을 근거로 안내하고, 범위를 벗어난 질문에는 DevDesk의 지원 범위 밖임을 알리고 해당 업무 담당 부서에 문의하도록 안내한다. 
    근거: 사내 문서와 티켓을 근거로 답하고 자료에 포함되지 않으면 추측하지 않고 답변에 필요한 정보가 부족함을 알린다. 
    비밀정보: 외부나 권한이 없는 사람에게 인증정보, 개인정보, 보안 관련 기밀, 사업 관련 기밀 등을 공개하지 않는다. 
    담당자 확인: 자료만으로 판단하기 어렵거나 변경에 권한 및 승인이 필요한 경우, 담당자 확인이 필요함을 안내한다. 실제로 담당자에게 연락해 확인하지 않았다면 “담당자에게 확인했습니다”라고 말하지 않는다.
    답변 형식:설명을 한 문단으로 작성하고 해결 절차를 번호로 나누고, 답변 내용과 참고한 근거를 구분하고 JSON의 정해진 항목으로 출력하세요. 
    """

    # reasoning 조건에만 근거 점검 지시 추가  
    if variant == "reasoning":
        policy += """
    답변을 작성하기 전에 확인된 사실과 아직 확인되지 않은 사실을 구분하며, 질문의 상황을 파악하고 관련 근거를 확인한다.
    근거의 적용 조건과 제약을 확인하고 답할 수 있는 범위를 결정한다.        
    """
    # 같은 문서는ㄴ 항상 같은 순서로 구성 
    corpus = json.dumps(sorted(documents, key=lambda item: item["doc_id"]),
                        ensure_ascii=False, sort_keys=True)
    return policy + "\n<reference_documents>\n" + corpus + "\n</reference_documents>"


# 필수 2 / 답변 검증과 수정. 스키마를 만든 뒤 값과 출처를 검사합니다.
# AI 답변에 필요한 JSON 형식 정의  
def answer_format():

    # 이유: 네 필드의 자료형과 허용된 문의 분류를 고정하기 위해 사용한다. 
    properties = {
        "answer": {
            "type": "string"
        },
        "source_ids": {
            "type": "array",
            "items": {
                "type": "string"
            }
        },
        "needs_human": {
            "type": "boolean"
        },
        "category": {
            "type": "string",
            "enum": [
                "installaction",
                "access",
                "incident",
                "general"
            ]
        }
    }
    schema = {"type": "object", "properties": properties,
              "required": ["answer", "source_ids", "needs_human", "category"],
              "additionalProperties": False}
    return {"format": {"type": "json_schema", "name": "devdesk_answer",
                       "strict": True, "schema": schema}}

# 답변의 JSON 형식과 출처 유효성 검사 
def validate_answer(raw, known_ids):
    answer = json.loads(raw)
    Draft202012Validator(answer_format()["format"]["schema"]).validate(answer)
    # 이유: 스키마는 답변의 자료형과 구조만 확인하므로, 내용의 정확성까지 보장하지 않는다.
    # 따라서 출처가 실제로 존재하는지, 답변 본문이 해당 문서와 업무 정책에 맞는지 별도로 확인해야 한다. 

  # 빈 답변, 없는·중복 출저, 담당자 확인 누락 검사  
    rules = [
        (   
            not answer["answer"].strip(), "blank answer"),
        (
            any(source_id not in known_ids for source_id in answer["source_ids"]), "unknown source_id"),
        (
            len(answer["source_ids"]) != len(set(answer["source_ids"])), "duplicate source_id"),
        (
            not answer["source_ids"] and answer["needs_human"] is False, "unsupported answer requires human"),
    ]
    for invalid, message in rules:
        if invalid:
            raise ValueError(message)
    return answer

# 답변 오류를 검사하고 수정 요청 또는 대체 답변 처리 
def finish_answer(send, request, response, known_ids, events):
    request = copy.deepcopy(request)
    fallback = {"answer": "확인 가능한 답변을 만들지 못했습니다. 담당자 확인이 필요합니다.",
                "source_ids": [], "needs_human": True, "category": "general"}
    repair_used = False
    # 한 번 검사하고, 필요하면 한 번 수정한 뒤 같은 검사를 다시 합니다.
    for turn in range(2):
        if response is None:
            reason = "api_failure"
        elif response.get("status") == "round_limit":
            reason = "round_limit"
        elif response.get("status") != "completed":
            reason = "incomplete"
        elif support.has_refusal(response):
            reason = "refusal"
        else:
            try:
                answer = validate_answer(response["output_text"], known_ids)
                return {"answer": answer, "fallback_reason": None, "repair_used": repair_used}
            except (ValueError, ValidationError) as error:
                error_kind, field = support.validation_detail(error)
                events.append({"event": "validation_error", "repair_already_used": repair_used,
                               "error_kind": error_kind, "error_field": field})
                if turn == 1:
                    reason = "validation_failed"
                else:
                    # 종류: invalid_json, schema_error, blank_answer, unknown_source,
                    # duplicate_source, unsupported_answer. 종류에 맞게 안내를 만드세요.
                    hint = {
                        "invalid_json": "JSON 문법",
                        "schema_error": "스키마 에러",
                        "blank_answer": "빈 답변",
                        "unknown_source": "없는 출처",
                        "duplicate_source": "중복 출처",
                        "unsupported_answer": "출처 없이 담당자 확인 불필요"
                    }
                    
                    repair_used = True
                    support.append_repair_input(request, response, hint)
                    response = send(request)
                    continue
        return {"answer": fallback, "fallback_reason": reason, "repair_used": repair_used}


# 필수 3 / 티켓 조회. 티켓 조회 조건과 모델에 돌려줄 값을 정합니다.

# 티켓 조회 도구의 이름과 입력 형식 정의
def tool_schema():
    parameters = {
        "type": "object",
        "properties": {
            "ticket_id":{
                "type": "string",
                "pattern":"^IT-[0-9]{4}$"
            }
        },
        "required": ["ticket_id"],
        "additionalProperties": False
    }
    return {"type": "function", "name": "lookup_ticket", "strict": True,
            "description": "기존 티켓의 상태를 읽습니다. 티켓을 변경하지 않습니다.",
            "parameters": parameters}

# 티켓 번호를 검사하고 해당 티켓 정보 조회
def execute_tool(name, arguments, tickets):
    if name != "lookup_ticket":
        return {"ok": False, "error": "unknown_tool"}
    try:
        args = json.loads(arguments)
        if not isinstance(args, dict) or set(args) != {"ticket_id"}:
            raise ValueError("unexpected arguments")
        ticket_id = args["ticket_id"]
        if not isinstance(ticket_id, str) or not re.fullmatch(r"IT-[0-9]{4}", ticket_id):
            raise ValueError("invalid ticket_id")
    except (ValueError, TypeError):
        return {"ok": False, "error": "invalid_arguments"}
    if ticket_id not in tickets:
        return {"ok": False, "error": "not_found", "ticket_id": ticket_id}
    return {"ok": True, "ticket": copy.deepcopy(tickets[ticket_id])}


# AI의 도구 호출을 실행하고 조회 결과를 다시 전달 
def tool_roundtrip(send, request, tickets, events):
    request = copy.deepcopy(request)
    for _ in range(4):
        response = send(request)
        if response is None or response.get("status") != "completed" or support.has_refusal(response):
            return request, response
        output = response.get("output", [])
        calls = [item for item in output if item.get("type") == "function_call"]
        if not calls:
            return request, response
        # 이유: AI는 도구 사용을 요청하고, 실제 조회는 파이썬이 실행한다,
        # call_id는 도구 요청과 결과를 연결하므로 같은 값을 유지합니다.
        request["input"].extend(copy.deepcopy(output))
        for call in calls:
            if not isinstance(call.get("call_id"), str) or not call["call_id"]:
                return request, {"status": "incomplete", "output": []}
            result = execute_tool(
                call.get("name"),
                call.get("arguments"),
                tickets
            )
            events.append({"event": "tool_result", "name": call.get("name"),
                           "call_id": call["call_id"], "ok": result["ok"], "error": result.get("error")})
            request["input"].append({"type": "function_call_output",
                                    "call_id": call["call_id"],
                                    "output": json.dumps(result, ensure_ascii=False)})
    return request, {"status": "round_limit", "output": []}


# 질문과 이미지를 AI가 처리할 입력 데이터로 변환
def image_content(question, image_path):
    """질문 문자열과 선택적 이미지 경로를 모델 입력 항목의 리스트로 변환한다.
    image_path가 None이면 텍스트만, 경로가 있으면 텍스트와 이미지를 함께 변한한다.
    """
    # 빈 질문을 API(프로그램 간 요청, 응답 창구)에 보내지 않는다.
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question is empty")
    # content는 서로 다룬 종류의 입력을 함께 담는 리스트, 첫 항목은 항상 질문 텍스트이다.
    content = [{"type": "input_text", "text": question}]
    # 이미지가 있을 때만 이미지 항목을 추가한다. URL 표현 반환은 support.image_url에 맡긴다.
    if image_path is not None:
        content.append({
            "type": "input_image",
            "image_url": support.image_url(image_path),
            "detail": "high"
        })
    # 이유: 화면은 오류 메시지와 증상을 보여 주지만 원인을 확정하는 자료는 아니다.
    # high는 세부 내용을 읽기 위한 설정이며, 필요한 경우 로그와 담당자 확인을 함께 안내한다.
    return content


# 일시적인 API 오류 발생 시 최대 3회 전송 시도 
def call_with_retry(send, request, events, sleep=time.sleep):
    """일시적 전송 오류에 한해 최대 3번 시도하고, 응답 또는 실패 표시 None을 반환한다.
    
    send: 실제 전송 함수, sleep: 대기함수, 기본값은 time.sleep이다
    각 전송의 성공, 실패와 대기 시간을 events에 누적한다. 
    """
    #range(1, 4)는 1, 2, 3. 최초 호출을 포함한 총 시도 횟수가 최대 3회이다.
    for attempt in range(1, 4):
        # perf_counter는 경과 시간 측정용이다. 현재 날짜는 구하는 함수는 아니다. 
        started = time.perf_counter()
        try:
            response = send(request)
        # support가 전송 오류가 분류해 발생시킨 예외만 여기서 재시도 대상으로 처리한다. 
        except support.TransportError as error:
            status = error.status_code
            
            # support가 전송 오류로 분류해 발생시킨 예외만 여기서 재시도 대상으로 처리한다.
            # None이라는 전제, 408: 시간 초과, 409: 충돌, 429: 요청 제한, 5xx: 서버 오류,
            # 400: 잘못된 요청, 401: 인증실패, 403: 권한 없음 등은 재시도하지 않는다. 
            retryable = (
                status is None
                or status in {408, 409, 429}
                or (isinstance(status, int) and 500 <= status <= 599)
            )
            # 오류가 재시도 대상이어도 세 번째 시도 이후에는 더 호출하지 않는다. 
            retry_now = retryable and attempt < 3

            delay = support.delay_for(attempt) if retry_now else 0
            support.append_attempt(events, attempt, started, error=error,
                                   retryable=retryable, wait_s=delay)
            if not retry_now:
                return None
            sleep(delay)
        else:
            support.append_attempt(events, attempt, started, response=response)
            return response
    # 이유: 전송 재시도는 응답을 못 받은 일시적 오류라서 같은 요청을 기다렸다가 그대로 다시 보낸다,
    # 출력 수정은 받은 응답의 내용이 규칙을 어긴 경우라서,  
    # 같은 요청 대신 틀린 출력과 수정 지시를 덧붙여 새로 요청한다.


# 프롬프트 캐시에 사용할 고유 키 생성 
def cache_settings(documents, variant):
    instructions = build_instructions(documents, variant)
    fingerprint = hashlib.sha256(instructions.encode("utf-8")).hexdigest()[:16]
    # 같은 정책과 조건은 같은 키를 사용합니다. 질문이나 현재 시각을 섞지 않습니다.
    return {"instructions": instructions,
            "prompt_cache_key": f"kant-next-pe-{variant}-{fingerprint}"}


# 입력·출력 토큰 사용량과 예상 비용 계산 
def usage_record(attempt, prices):
    response = attempt.get("response") or {}
    usage = response.get("usage") or {}
    details = usage.get("input_tokens_details") or {}
    it = usage.get("input_tokens")
    ot = usage.get("output_tokes")
    cached = details.get("cached_tokens")
    written = details.get("cache_write_tokens")
    reasoning = (usage.get("output_tokens_details") or {}).get("reasoning_tokens")
    support.validate_usage_counters(it, ot, cached, written, reasoning)
    estimate, assumption = None, None
    if it is not None and ot is not None and cached is not None:
        effective_write = written if written is not None else 0
        if it > prices["max_input_tokens"]:
            assumption = "input exceeds the supplied price tier; estimate unavailable"
        else:
            if written is None:
                assumption = "cache_write_tokens absent; assumed zero for estimate"
            ordinary = it - cached - effective_write
            # prices의 단가 키: input, cached, cache_write, output. 백만 토큰당 USD입니다.
            estimate = (
                ordinary * prices["input"]
                + cached * prices["cached"]
                + effective_write * prices["cache_write"]
                + ot * prices["output"]
            ) / 1_000_000
    observation = ("unavailable" if cached in None else "hit" if cached > 0 else "miss")
    # 이유: 캐시 읽기, 쓰기 토큰은 전체 입력에 포함되므로 일반 입력에서 빼서 이중 청구를 막고, 
    # 추론 토큰은 출력의 일부라 다시 더하지 않는다.
    # fixture의 토큰 값은 실제 측정값이 아니며, 로그에서 request_id와 단가 출저, 확인일을 함께 남긴다. 
    return support.pack_usage_record(attempt, response, prices, it, ot, cached, written,
                                     reasoning, observation, estimate, assumption)


# 프롬프트 생성부터 답변 검증까지 전체 작업 실행 
def run_pipeline(send, question, documents, tickets, variant="reasoning",
                 image_path=None, prices=None, sleep=time.sleep):
    prices = support.load_prices() if prices is None else prices
    events = []
    started = time.perf_counter()
    settings = cache_settings(documents, variant)
    request = support.base_request(settings["instructions"], question, variant)
    request.update(settings)
    request["text"] = answer_format()
    request["tools"] = [tool_schema]
    request["parallel_tool_calls"] = False
    request["input"][0]["content"] = image_content(question, image_path)

    # API 요청 시 오류가 발생하면 재시도하는 함수 
    def reliable_send(current_request):
        return call_with_retry(send, current_request, events, sleep=sleep)

    final_request, response = tool_roundtrip(reliable_send, request, tickets, events)
    result = finish_answer(reliable_send, final_request, response,
                           {document["doc_id"] for document in documents}, events)
    result["tool_calls"] = sum(event["event"] == "tool_result" for event in events)
    result["logs"] = [usage_record(event, prices) if event["event"] == "api_attempt" else event
                      for event in events]
    result["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 3)
    return result


# 선택 심화 1. 골격 없이 두 대상의 프롬프트와 비교 함수를 설계합니다.
def build_audience_instructions(documents, variant, audience):
    """newcomer/operator 지시를 직접 설계. 다른 모드는 ValueError.

    공통 정책을 유지하고, 용어 풀이와 처리 순서를 대상에 맞추세요.
    """
    raise NotImplementedError("선택 심화: build_audience_instructions를 작성하세요.")


def audit_audience_pair(newcomer, operator):
    """같은 질문의 유효한 답변 dict 두 개를 비교합니다.

    반환: same_policy(bool), different_explanation(bool), issues(list[str]).
    category, needs_human, source_ids 집합은 같아야 합니다.
    answer는 앞뒤 공백을 뺀 값이 달라야 합니다.
    issues에는 다른 정책 필드명과 필요하면 same_explanation을 담으세요.
    본문이 다르다는 사실만으로 설명이 적절하다고 결론내리지는 마세요.
    """
    raise NotImplementedError("선택 심화: audit_audience_pair를 작성하세요.")


if __name__ == "__main__":
    import sys
    raise SystemExit(support.cli(sys.modules[__name__]))

