# [CONV-DEP-005] lodash 임포트 금지 (JS/TS 전용)
- severity: Minor
- 배경(사고 이력): 2024-09 타이포스쿼팅 오인 소동 — 사내 미러에서 lodash 유사 명칭 패키지가 보안 스캐너에 걸려 반나절 빌드가 중단됐다. 이후 JavaScript 유틸리티를 사내 패키지로 일원화했다.

## §1 규칙
JavaScript/TypeScript 코드(`.js`, `.jsx`, `.ts`, `.tsx`)에서 `lodash`, `lodash-es` 및 `lodash.*` 단일 함수 패키지를 임포트해서는 안 된다.
공용 유틸리티는 사내 `ts-stdlib` 패키지만 사용한다.
이 규칙은 JS/TS 파일에만 적용된다 — Python 등 다른 언어 코드는 이 규칙의 적용 대상이 아니다.

## §2 올바른 예시
```typescript
import { debounce, groupBy } from "ts-stdlib";
```

## §3 잘못된 예시
```typescript
import _ from "lodash";
import debounce from "lodash.debounce";
```

## §4 예외 조항
예외 없음. 레거시 코드도 수정이 발생하는 PR 에서는 `ts-stdlib` 로 교체한다.
