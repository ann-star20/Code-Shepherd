# **A2 SDD — Pipeline API 완성 설계**

## **2. 목표 (TO-BE)**

### **2.1. 추가 및 수정할 엔드포인트 명세**

#### **① GET /api/pipeline/logs/{session_id}**

* **역할**: pipeline_logs 테이블의 세부 이력 데이터와 documents.state 조인 결과를 반환하여 프론트엔드의 각 스피너/체크 아이콘 및 세부 롤링 텍스트를 실시간 동기화합니다.  
* **응답 뼈대 스키마**:

{  
  "session_id": "3a2f9e1c-4b5d-6e7f-8a9b-0c1d2e3f4g5h",  
  "doc_state": "EXTRACTED",   
  "current_step": 3,  
  "logs": [  
    {   
      "ts": "2026-06-07T17:34:15Z",   
      "agent": "Extractor",   
      "level": "INFO",   
      "message": "Gemini-2.5-Flash 가동 중. 보안 메커니즘 및 설정 속성 추출 시작 (Tokens: 12,361)"   
    }  
  ]  
}

* **프론트엔드 소비 방식**: 2초 주기 단기 폴링(Short Polling) 가동.

#### **② GET /api/staging/{session_id} (경로 및 규격 통일)**

* **역할**: 스테이징 레이어 보관소에 격리된 DRAFT 또는 DOMAIN_PENDING 상태의 개념 추출 스키마 목록과 병합 통계를 클라이언트 융합 훅(useGraphMerge.ts)에 내려줍니다.  
* **응답 뼈대 스키마**:

{  
  "session_id": "3a2f9e1c-4b5d-6e7f-8a9b-0c1d2e3f4g5h",  
  "concepts": [  
    {   
      "id": "uuid-string",   
      "state": "DRAFT",   
      "concept_json": {   
        "concept_name": "CrossSiteRequestForgery",   
        "domains": ["security"],  
        "concept_type": "vulnerability_root_cause"  
      }   
    }  
  ],  
  "diff": { "virtual_new": 1, "virtual_match_merge": 1, "unknown_domains_count": 0 }  
}

### **2.2. 최신 하이브리드 UX 프론트엔드 연동 흐름 (End-to-End)**

[1. 입력]     POST /api/documents { urls: [...] }  
              ➔ { documents: [{ doc_id }] }

[2. Prescan]  POST /api/documents/{doc_id}/prescan  
              ➔ { framework, version, lang, infer_confidence }  
              ★ HITL 분기: 미등록 도메인 포획 시 DOMAIN_PENDING 인터락 팝업 활성화,  
                복구 API 처리 완료 전까지 Step 2(Crawler) 진입을 강제 차단.

[3. 트리거]   POST /api/pipeline/trigger { doc_id }  
              ➔ { session_id }

[4. 폴링 시작] GET /api/pipeline/logs/{session_id}  (2초 주기 무한 루프)  
              - 1단계 LOADING (스피너) ➔ subText 롤링 처리  
              - 2단계 LOADING (스피너) ➔ 크롤러 원문 정제 로그 수집 및 토스트 팝업  
              - 3단계 LOADING (스피너) ➔ Gemini Flash 응답 대기 (중요 전환점 발생 시 토스트 팝업)  
                
              ★ 폴링 제어 경계선: doc_state == "EXTRACTED" 상태여도 폴링을 끊지 않음!  
                Writer 워커가 RDB 스테이징 적재를 무결하게 완료하여 프론트엔드에   
                "가상 뷰어 준비 완료" 사인을 보낼 때까지 스피너 유지 및 subText 롤링 유지.

[5. HITL 게이트] doc_state가 완전히 수렴되어 가상 토폴로지가 완성되면 폴링 일시 중단.  
              - GET /api/staging/{session_id} 호출 ➔useGraphMerge.ts 융합 가동  
              - 대시보드 캔버스 상에 노란색 점선 테두리(DRAFT) 가상 노드 시각화 오버레이  
              - 관리자 최종 검토 ➔ 개별 토글 혹은 하단 바 [✓ 최종 승인 게이트 통과] 클릭  
              - POST /api/staging/{session_id}/approve 전송

[6. 최종 폴링] GET /api/pipeline/logs/{session_id} 재가동  
              - doc_state == "COMMITTED" 검출 시 폴링 영구 중단.  
              - 4대 마스터 크롬 트랜잭션 커밋 완료 확인 ➔ 점선 가상 노드가 영속 실선 노드로 치환됨.

## **3. TDD 구현 순서**

### **Step 1 — 테스트 코드 먼저 작성 (RED)**

tests/harness/test_pipeline_logs_api.py를 신설하여 아래 3대 시나리오 하네스를 선언합니다.

* test_logs_returns_pipeline_log_rows (로그 히스토리 배열 로드 무결성)  
* test_logs_includes_doc_state (JOIN을 통한 출처 문서 최신 상태 동기화 확인)  
* test_logs_empty_for_unknown_session (부재한 세션 인입 시 페일세이프 검증)

### **Step 2 — 엔드포인트 구현 ➔ GREEN**

interfaces/api/pipeline.py 컨트롤러 내부에 GET /logs/{session_id} 라우터를 구현하여 테스트를 통과시킵니다.

### **Step 3 — Staging 경로 동기화 및 가상 병합 인터페이스 검증**

staging.py 내의 GET /{session_id} API 스펙이 변환 계약 필드를 완전하게 소화하여 딕셔너리를 누락 없이 리턴하는지 점검합니다.

### **Step 4 — 프론트엔드 리팩토링 및 연동**

MainPage.tsx 내의 구형 LogConsole 검은색 패널 마크업을 과감히 소거합니다. 대신 진행 상태 스피너 컴포넌트 내부로 subText 노드를 밀어 넣고, 중요 분기점 로그를 토스트(Toast) 팝업 및 우측 슬라이딩 디버그 서랍(Drawer)으로 파이프 처리합니다.

## **4. 인프라 실행 명령 (Environment Mode Execution)**

개발 및 TDD 하네스 구동 중에는 **LLM만 가짜 객체로 대체할 뿐, 저장소 검증을 위해 PostgreSQL과 Neo4j 컨테이너는 필수로 기동**되어야 합니다.

# ① Mock 모드 실행 (Gemini 통신 차단, 실제 DB 적재 및 수렴 검증용)  
# 볼륨 클린 포맷 및 .env.mock 환경변수를 동적으로 덮어써서 uvicorn 실시간 리로드 가동  
docker compose -f docker-compose.yml -f docker-compose.mock.yml up -d postgres redis neo4j backend celery_worker

# ② Production 상용 모드 실행 (실제 Gemini 2.5 Flash API 타격 및 LangSmith 프로덕션 트레이싱 가동)  
APP_MODE=production GEMINI_API_KEY=AIzaSy... LANGCHAIN_TRACING_V2=true docker compose up -d --build  
