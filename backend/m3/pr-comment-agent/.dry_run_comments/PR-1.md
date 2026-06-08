## 🤖 자동 리뷰 (rework · Major 3 · Minor 3)

### 🟡 Major: SEC-001 (src/auth.py:15)
하드코딩된 비밀키가 감지되었습니다.

💡 환경 변수 또는 secrets manager를 사용하세요.

### 🟡 Major: SEC-002 (src/auth.py:30)
SQL 쿼리에 사용자 입력이 직접 포함되어 있습니다.

💡 파라미터화된 쿼리(prepared statement)를 사용하세요.

### 🟡 Major: QUAL-001 (src/db.py:10)
함수 복잡도가 기준치(10)를 초과합니다.

💡 함수를 작은 단위로 분리하세요.

### 🔵 Minor: QUAL-002 (src/db.py:20)
미사용 import가 있습니다.

💡 불필요한 import를 제거하세요.

### 🔵 Minor: TEST-001 (src/tests/)
라인 커버리지 45% — 목표치(80%) 미달.

💡 핵심 비즈니스 로직에 대한 단위 테스트를 추가하세요.

### 🔵 Minor: PERF-001 (src/posts.py:7)
루프 내부에서 DB 쿼리가 반복 호출됩니다 (N+1 패턴).

💡 쿼리를 루프 밖으로 이동하거나 select_related를 사용하세요.