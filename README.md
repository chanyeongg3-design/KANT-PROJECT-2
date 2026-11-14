<div align="center">

# 🚀 KANT-PROJECT-2

**LLM 기반 개발팀 지원 어시스턴트(KANT NEXT DevDesk) 구현 모음**
API 서버 · 프롬프트 엔지니어링 · LangChain

![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![Pydantic](https://img.shields.io/badge/Pydantic-E92063?style=for-the-badge&logo=pydantic&logoColor=white)
![LangChain](https://img.shields.io/badge/LangChain-1C3C3C?style=for-the-badge&logo=langchain&logoColor=white)
![OpenAI](https://img.shields.io/badge/OpenAI_API-412991?style=for-the-badge&logo=openai&logoColor=white)

</div>

---

## 📌 한눈에 보기

기업 개발팀의 **개발환경·장애 문의**에 답하는 지원 어시스턴트 **DevDesk**를 세 가지 방식으로 구현한 과제 모음입니다.
세 폴더는 같은 주제를 다루며, 각각 **서비스 계층(API 서버) → 모델 호출 계층(프롬프트) → 오케스트레이션 계층(LangChain)** 을 담당합니다.

| # | 폴더 | 한 줄 요약 | 핵심 기술 | 주요 파일 |
| :-: | :--- | :--- | :--- | :--- |
| 1 | 🌐 [**데이터 수집 & API 서버 구축**](<./데이터 수집 & API 서버 구축>) | GitHub 릴리스를 수집·정제해 문서 API로 제공하고, 질의응답·재시도·요청 제한까지 갖춘 서버 | FastAPI, httpx, Pydantic, asyncio | `app.py` |
| 2 | 💬 [**프롬프트 엔지니어링**](<./프롬프트 엔지니어링>) | 정책 프롬프트, JSON 스키마 검증, 티켓 조회 도구 호출, 이미지 입력, 재시도·비용 기록 파이프라인 | OpenAI Responses 형식, JSON Schema, Function Calling | `main.py` |
| 3 | 🔗 [**LangChain**](<./LangChain>) | 문서 검색 → 프롬프트 → 모델 → 출처 검증 → 대화 이력 → 실패 복구를 LangChain 체인으로 구성 | LangChain Core, Runnable, Pydantic | `main.py`, `AI_USAGE.md` |

---

## 🗂 저장소 구조

```text
KANT-PROJECT-2/
├── README.md
├── 데이터 수집 & API 서버 구축/
│   └── app.py              # 수집 · 정제 · 문서 API · 모델 연결 · 요청 제한 · 로깅
├── 프롬프트 엔지니어링/
│   └── main.py             # 정책 프롬프트 · 답변 검증 · 도구 호출 · 재시도 · 비용 기록
└── LangChain/
    ├── main.py             # 검색 · 체인 · 대화 이력 · 실패 복구 · 스트리밍
    └── AI_USAGE.md         # 과제 중 AI 사용 기록
```

> ℹ️ 각 코드는 과제에서 제공하는 `support.py`(공통 보조 모듈)를 `import support` 로 사용합니다. 이 저장소에는 `support.py`가 포함되어 있지 않아, 단독으로 실행하려면 해당 파일이 필요합니다.

---

## 🌐 1. 데이터 수집 & API 서버 구축

📄 [`app.py`](<./데이터 수집 & API 서버 구축/app.py>)

GitHub 공개 릴리스 데이터를 모아 정제하고, 사용자가 고른 문서만 근거로 답하는 **질의응답 API 서버**를 구성합니다.

### 처리 흐름

```text
GitHub Releases API ─▶ collect_releases ─▶ normalize_releases ─▶ 문서 저장소(메모리)
                                                                     │
사용자 질문 + 선택한 문서 ID ─▶ admit_query(요청 제한) ─▶ query_with_retry ─▶ call_model_once ─▶ 출처 검증 ─▶ 응답
```

### 단계별 구현

| 단계 | 함수 / 클래스 | 하는 일 |
| :--- | :--- | :--- |
| 수집 | `collect_releases` | 페이지 단위(`page`, `per_page`)로 릴리스를 요청하고, 성공한 페이지만 `raw_pages.json`, 결과 보고서를 `collection_report.json`에 저장. `max_pages=2`, `per_page=5`가 기본값이며 오류가 나면 실패 페이지와 원인(`http_*`, `timeout`, `connection_error`, `invalid_json_array`)을 기록하고 중단 |
| 정제 | `normalize_releases` | 원본을 **채택 / 격리(quarantine) / 제외(excluded)** 로 분류하고 이유를 남김. 잘못된 객체·ID·플래그·제목은 격리, `draft`·`prerelease`는 제외, 제목이 없으면 `tag_name`으로 대체, 빈 본문과 중복 ID 처리 |
| 텍스트 보조 | `clean_text`, `validate_url`, `validate_timestamp` | HTML 조각·공백 정리, HTTP(S) URL 검사, 시간대 포함 날짜 검사 |
| 데이터 모델 | `CourseModel`, `Document`, `QueryRequest`, `QueryReply` | Pydantic으로 자료형·길이를 엄격하게 검사하고 추가 필드를 금지. `model_validator`로 필드 간 규칙 확인 |
| 저장소 | `register_document`, `find_document` | ID·URL 중복 등록 방지, 없는 문서는 `404` 반환 |
| 모델 연결 | `build_prompt`, `call_model_once` | **선택된 문서만** 질문과 묶어 프롬프트를 만들고 비동기(`httpx`)로 호출. 응답이 선택하지 않은 문서를 출처로 쓰면 거부 |
| 실패 처리 | `query_with_retry` | 최대 2회 시도. 첫 시도의 timeout·5xx만 재시도하고, 공급자 `429`는 `503`, 최종 timeout은 `504`, 연결·형식 오류는 `502`로 정리 |
| 요청 제한 | `admit_query` | 기본 **60초에 30건**. 한도 초과 시 남은 대기 시간(초)을 반환. 모델 재시도는 새 질문으로 세지 않음 |
| 로깅 | `request_logging` | `method`, `path`, `status`, `mode`, `elapsed_ms` 다섯 필드만 기록(질문·본문·원본 URL·인증 헤더는 제외) |
| 앱 생성 | `create_app` | 위 구현을 서버 생성 함수에 연결. `fixture`(고정 데이터)와 `live`(실제 호출) 모드 지원 |

### 🧩 선택 심화
- `compare_snapshots`: 두 수집 결과를 ID별로 `added / changed / unchanged / missing` 비교 (현재 **미구현**)

---

## 💬 2. 프롬프트 엔지니어링

📄 [`main.py`](<./프롬프트 엔지니어링/main.py>)

정책 프롬프트를 설계하고, 모델 응답을 **구조화·검증·수정**하며, 도구 호출·이미지 입력·재시도·비용 기록까지 하나의 파이프라인으로 묶습니다.

### 처리 흐름

```text
build_instructions ─▶ cache_settings ─▶ 요청 구성(질문 + 이미지)
        ─▶ tool_roundtrip(티켓 조회, 최대 4라운드) ─▶ finish_answer(검증 · 1회 수정 · fallback)
        ─▶ usage_record(토큰 · 캐시 · 비용 추정) ─▶ 결과 + 로그
```

### 단계별 구현

| 단계 | 함수 | 하는 일 |
| :--- | :--- | :--- |
| 정책 프롬프트 | `build_instructions(documents, variant)` | 역할·업무 범위·근거·비밀정보·담당자 확인·답변 형식을 담은 정책 작성. `baseline`과 `reasoning` 두 조건이 있으며, `reasoning`은 확인된 사실과 미확인 사실을 구분하는 점검 지시를 추가. 참고 문서는 `doc_id` 순으로 정렬해 항상 같은 순서로 전달 |
| 응답 형식 | `answer_format` | `answer`, `source_ids`, `needs_human`, `category` 네 필드를 갖는 strict JSON Schema 정의 |
| 응답 검증 | `validate_answer` | 스키마 검증 후 빈 답변, 없는/중복 출처, 근거 없는데 담당자 확인도 없는 답변을 거부 |
| 수정 · 대체 | `finish_answer` | 검증 실패 시 **한 번만** 수정 요청. 실패·거절·미완료 응답은 담당자 확인이 필요하다는 대체 답변으로 마무리 |
| 도구 정의 | `tool_schema` | `lookup_ticket` 함수. `ticket_id`는 `IT-0000` 형식만 허용 |
| 도구 실행 | `execute_tool`, `tool_roundtrip` | 모델이 요청한 도구를 파이썬이 실제로 실행(읽기 전용)하고 `call_id`로 결과를 연결해 다시 전달. 최대 4라운드 |
| 이미지 입력 | `image_content` | 질문 텍스트와 선택적 이미지(`detail: high`)를 입력 항목으로 변환 |
| 재시도 | `call_with_retry` | 최대 3회. 연결 오류와 `408/409/429/5xx`만 재시도, 그 외(400·401·403 등)는 즉시 종료 |
| 캐시 | `cache_settings` | 지시문의 SHA-256 앞 16자로 `prompt_cache_key` 생성(질문·시각은 섞지 않음) |
| 비용 | `usage_record` | 입력·출력·캐시 읽기/쓰기 토큰으로 호출 비용 추정, 캐시 hit/miss 관측 |
| 실행 | `run_pipeline` | 위 단계를 한 번에 실행하고 도구 호출 수, 로그, 소요 시간을 반환 |

### ▶ 실행 방법 (파일 안내 기준)

```bash
uv run --frozen python main.py demo
uv run --frozen python main.py check policy
uv run --frozen python main.py run policy --live
```

### 🧩 선택 심화
- `build_audience_instructions`, `audit_audience_pair`: 신입/운영자 대상별 설명 비교 (현재 **미구현**)

---

## 🔗 3. LangChain

📄 [`main.py`](<./LangChain/main.py>) · 📝 [`AI_USAGE.md`](<./LangChain/AI_USAGE.md>)

DevDesk의 검색·생성·검증·이력·복구를 **LangChain Runnable 체인**으로 구성합니다.

### 체인 구조

```text
입력(question, history, document_ids)
   └─ RunnableParallel ─┬─ preserve_input (원본 입력 보존)
                        └─ retrieve       (키워드 검색)
        └─ merge_context ─▶ RunnableBranch ─┬─ 문서 없음 ─▶ 고정 안내 (모델 호출 안 함)
                                            └─ 문서 있음 ─▶ prompt ─▶ model ─▶ parser ─▶ validate_sources
                                                              (reliable=True면 retry 2회 + fallback)
```

### 단계별 구현

| 단계 | 함수 / 클래스 | 하는 일 |
| :--- | :--- | :--- |
| 문서 변환 | `to_documents` | 본문은 `page_content`, 나머지는 `metadata`로 분리한 `Document` 생성. 릴리스 문서에는 기본 키워드(`uv`, `릴리스`, `release`) 부여 |
| 검색 | `search_documents` | 허용된 ID로 후보를 먼저 제한하고, 키워드 일치 개수로 점수 계산(대소문자·중복 제거). `top_k`는 1~3, 동점은 원본 순서 유지 |
| 컨텍스트 | `format_context`, `build_context_chain` | 검색 문서를 제목·출처·본문 문자열로 변환하고, 질문과 이전 대화로 검색어를 만들어 병렬 체인에 연결 |
| 프롬프트 | `build_prompt_and_parser` | 시스템 정책 → 검색 문서 → 이전 대화 → 현재 질문 순서. `PydanticOutputParser`로 답변 구조화 |
| 출처 검증 | `validate_sources` | 중복 출처, 검색 결과에 없는 출처, 근거 없는 자동 확정 답변을 거부 |
| 기본 체인 | `build_primary_chain`, `build_answer_chain` | prompt → model → parser → 출처 검증. 검색 결과가 없으면 `RunnableBranch`로 모델 호출 없이 안내 |
| 대화 이력 | `get_history`, `commit_history` | 세션 ID별 `InMemoryChatMessageHistory` 분리. 정상 처리(`primary`)된 질문·답변 본문만 저장 |
| 실패 복구 | `build_resilient_chain` | 허용된 오류에 한해 최대 2회 시도 후 `fallback` 답변 반환 |
| 스트리밍 | `stream_answer` | `delta`(조각) / `reset`(재시도 시 초기화) / `final`(검증된 최종 답변) 이벤트 전달. 최대 2회 시도 |
| 관측 | `TraceHandler` | 실행 시간, 토큰 청크, 오류, 사용량 기록용 콜백 |

### ▶ 실행 방법 (파일 안내 기준)

```bash
uv run --frozen python main.py run search
```

### 🧩 선택 심화
- `review_draft`: 초안 검토 → 한 번 수정 → 재검토 흐름 (현재 **미구현**)

### 📝 AI 사용 기록
[`AI_USAGE.md`](<./LangChain/AI_USAGE.md>)에 과제 진행 중 AI에게 질문한 내용, 공유한 코드 범위, 이해한 내용, 직접 검증한 결과가 표로 정리되어 있습니다.

---

## 🧰 공통 설계 원칙

| 원칙 | 적용 위치 |
| :--- | :--- |
| **근거 있는 답변만 허용** — 검색·선택된 문서의 ID만 출처로 인정 | 1 · 2 · 3 모두 |
| **구조화된 출력** — Pydantic / JSON Schema로 형식 고정 | 1 · 2 · 3 모두 |
| **근거가 없으면 담당자 확인(`needs_human`)** | 1 · 2 · 3 모두 |
| **재시도는 일시적 오류에만, 횟수 제한** | 1(2회) · 2(3회) · 3(2회) |
| **민감 정보 최소 기록** — 로그에는 안전한 요약 필드만 | 1 |
| **실패 시 안전한 대체 답변(fallback)** | 2 · 3 |

---

## 🛠 Tech Stack

- 🐍 Python
- ⚡ FastAPI · httpx · asyncio
- ✅ Pydantic · jsonschema
- 🦜 LangChain Core
- 🤖 OpenAI 호환 API (프롬프트 엔지니어링, 도구 호출, 이미지 입력)
