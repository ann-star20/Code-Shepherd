### 3.8. 실시간 대시보드 및 뷰 (Frontend UI/UX)

- **5단계 파이프라인 상태 표시**: `Input` → `Crawler` → `Extractor` → `Graph Writer` → `Link Resolver` 단계별 실시간 인디케이터.
- **Human-in-the-Loop UI**: 메타데이터 추론 결과 확인 및 수동 입력 폼 (추론 신뢰도 배지, 누락 필드 경고).
- **실시간 런타임 로그**: WebSocket / SSE 기반 백그라운드 로그 콘솔 출력.
- **대화형 토폴로지 뷰**: 노드 타입별 색상 범례, 클릭 시 인스펙터 연동, 온톨로지 계층 필터링.
- **컨셉 인스펙터 패널**: 등급(critical, high), 프레임워크, 컨셉 타입(보안 메커니즘/취약점 원인/설정 속성/영향 컴포넌트)별 필터링 및 상세 대응 방안 조회.
- **가상 노드 미리보기 및 최종 승인 UI**: → 3.9절 참조.


#### 3.9.4. 프론트엔드 가상 노드 미리보기 (Virtual Node Preview)

관리자가 최종 승인 전에 **실제 그래프에 적용됐을 때의 모습**을 미리 확인할 수 있도록, 클라이언트 사이드에서 기존 Neo4j 데이터와 DRAFT 노드를 **가상으로 병합**하여 시각화한다. 실제 DB는 변경되지 않는다.

**가상 병합 렌더링 규칙**:
| 노드 유형 | 시각 처리 |
|-----------|-----------|
| 기존 확정 노드 | 기본 스타일 (실선, 불투명) |
| 신규 DRAFT 노드 | 점선 테두리, 반투명(opacity 0.65), 색상 강조 |
| DRAFT ↔ 기존 중복 (SAME_AS 후보) | 오버레이 배지 "병합 예정" + 연결선 강조 |
| 거부된 노드 | 빨간 테두리, 흐리게, 클릭 불가 |

**인터랙션**:
- 가상 노드 클릭 → 우측 인스펙터 패널에서 컨셉 상세 확인 및 개별 승인/거부 토글.
- 세션 전체 일괄 승인 버튼 `✓ 전체 승인` / `✗ 전체 거부` 제공.
- 승인 전 diff 요약: "신규 노드 N개 / 속성 업데이트 M개 / 병합(SAME_AS) K개".

**데이터 흐름 (클라이언트)**:
```
GET /api/graph/topology          → 기존 확정 노드/엣지 목록
GET /api/staging/{session_id}    → DRAFT 노드 목록
                                 ↓ 클라이언트 병합
react-force-graph 렌더링         → 가상 통합 그래프 표시
POST /api/staging/{session_id}/approve  → 최종 승인 전송
```


### 14.4. 프론트엔드 — 아토믹 디자인 패턴 기반 폴더 레이아웃

**설계 원칙**: Vite 빌드의 빠른 HMR을 살리면서, UI 컴포넌트는 원자 단위로 분리하고 비즈니스 로직과 API 통신은 `hooks` 레이어로 격리한다.

```
frontend/
├── src/
│   ├── assets/
│   │   ├── styles/
│   │   │   └── globals.css            # Tailwind 기본 설정 (@tailwind base/components/utilities)
│   │   └── fonts/
│   │
│   ├── components/                    # 아토믹 디자인 격리 레이어
│   │   ├── atoms/                     # [원자] 최소 단위 — 상태·로직 없음
│   │   │   ├── Badge.tsx              #   도메인 라벨 배지 (security · performance · 교차)
│   │   │   ├── Button.tsx             #   범용 버튼 (승인·거부·제출)
│   │   │   ├── Spinner.tsx            #   로딩 인디케이터
│   │   │   └── StatusDot.tsx          #   파이프라인 단계 상태 점 (PENDING/RUNNING/DONE)
│   │   │
│   │   ├── molecules/                 # [분자] 원자 2개 이상 조합 — 단일 책임
│   │   │   ├── PipelineStepIndicator.tsx   # StatusDot + 단계명 텍스트 조합
│   │   │   ├── MetadataForm.tsx            # 입력 필드 + 추론 신뢰도 배지 조합
│   │   │   └── DiffSummaryCard.tsx         # 승인 전 diff 요약 (신규 N개·업데이트 M개)
│   │   │
│   │   ├── organisms/                 # [유기체] 독립 가동 UI 블록 — 훅 결합 허용
│   │   │   ├── TopologyViewer.tsx     #   react-force-graph 래퍼
│   │   │   │                          #   가상 노드 미리보기: DRAFT=점선, COMMITTED=실선
│   │   │   ├── ConceptInspector.tsx   #   우측 사이드 패널 — 노드 상세·승인/거부 토글
│   │   │   ├── LogConsole.tsx         #   SSE 실시간 로그 스트림 출력 콘솔
│   │   │   └── ApprovalPanel.tsx      #   전체 승인·거부·diff 요약 패널
│   │   │
│   │   └── templates/                 # [템플릿] 레이아웃 골격 — 빈 슬롯 구조
│   │       └── DashboardLayout.tsx    #   사이드바 + 메인뷰 + 인스펙터 3-panel 레이아웃
│   │
│   ├── pages/                         # 라우팅 페이지 — 훅·유기체 결합점
│   │   └── MainPage.tsx               #   단일 SPA 페이지 (파이프라인 대시보드)
│   │
│   ├── hooks/                         # 비즈니스 로직·전역 상태 격리
│   │   ├── usePipelineSSE.ts          #   SSE 스트림 구독 → 파이프라인 단계 상태 업데이트
│   │   ├── useGraphMerge.ts           #   기존 Neo4j 노드 + DRAFT 노드 클라이언트 병합
│   │   │                              #   가상 토폴로지 데이터 생성 (DB 미접촉)
│   │   ├── useStagingApproval.ts      #   DRAFT 노드 목록 조회·개별 승인/거부·최종 승인 API
│   │   └── useDocumentInput.ts        #   URL 입력·메타데이터 Pre-scan 자동 추론 연동
│   │
│   ├── services/                      # Axios 기반 API 통신 추상화
│   │   ├── api.ts                     #   Axios 인스턴스·baseURL·인터셉터 설정
│   │   ├── pipelineService.ts         #   파이프라인 트리거·상태 조회 API
│   │   ├── stagingService.ts          #   스테이징 CRUD·승인·diff API
│   │   └── graphService.ts            #   토폴로지 조회 API
│   │
│   ├── types/                         # TypeScript 인터페이스·도메인 타입
│   │   ├── concept.ts                 #   ConceptNode, ConceptDomain, NodeLabel
│   │   ├── pipeline.ts                #   PipelineState, AgentStep, StagingRecord
│   │   └── graph.ts                   #   GraphNode, GraphEdge, VirtualNodeStyle
│   │
│   └── utils/                         # 순수 함수·데이터 파싱
│       ├── docId.ts                   #   build_doc_id 클라이언트 사이드 구현 (표시용)
│       └── nodeStyler.ts             #   노드 상태별 시각 스타일 결정 함수
│                                      #   (DRAFT=점선, COMMITTED=실선, REJECTED=빨간 테두리)
│
├── nginx.conf                         # 프로덕션 Nginx 설정 (SPA fallback, gzip, cache)
├── Dockerfile                         # Multi-stage: node build → nginx serve
├── package.json
└── vite.config.ts                     # 빌드 도구 설정 (path alias, proxy dev server)
```

**아토믹 레이어별 책임 구분**:

| 레이어 | 상태 보유 | 훅 사용 | API 호출 | 범위 |
|--------|-----------|---------|----------|------|
| atoms | 불가 | 불가 | 불가 | 스타일·렌더링만 |
| molecules | 로컬 UI 상태만 | 불가 | 불가 | 원자 조합 |
| organisms | 가능 | 가능 | hooks 통해서만 | 독립 UI 블록 |
| templates | 불가 | 불가 | 불가 | 레이아웃 슬롯 |
| pages | 가능 | 가능 | services 통해서만 | 라우팅 조합점 |

**`useGraphMerge.ts` 핵심 동작** (SDD 스펙):

```typescript
// Arrange: 두 데이터 소스 로드
const confirmedNodes = await graphService.getTopology()     // GET /api/graph/topology
const draftNodes = await stagingService.getDraft(sessionId) // GET /api/staging/{id}

// Act: 클라이언트 사이드 가상 병합 (DB 미접촉)
const merged = mergeVirtualGraph(confirmedNodes, draftNodes)
// merged 내 DRAFT 노드: strokeDasharray=true, opacity=0.65
// merged 내 SAME_AS 후보: badge="병합 예정"

// Assert (렌더 결과 테스트): 
// - DRAFT 노드 count === draftNodes.length
// - COMMITTED 노드 style.opacity === 1
```
