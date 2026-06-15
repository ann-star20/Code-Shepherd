# 사내 코딩 컨벤션 — KMS 적재용 통합 문서

> **From**: Dev3(m3) → **To**: Dev0/KMS 담당
> **목적**: 아래 내용을 임베딩해 `convention_embeddings` 테이블에 적재해 주세요. m3가 PR 분석 시 이 테이블을 **직접 검색**(pgvector 코사인)해 코멘트에 사내 가이드를 인용합니다.

## ⚙️ 적재 규약 (반드시 동일하게)

- **임베딩 모델**: `BAAI/bge-m3` (BGE-M3), **차원 1024**, `normalize_embeddings=True` (단위 벡터, 코사인 검색용).
  - ⚠️ **저장·검색 모델이 반드시 같아야** 합니다. m3 검색도 BGE-M3·1024를 씁니다. 모델이 다르면 검색이 통째로 어긋납니다.
- **테이블**: `convention_embeddings` (m3가 원래 적재하던 그 스키마와 동일)
  ```sql
  CREATE EXTENSION IF NOT EXISTS vector;
  CREATE TABLE IF NOT EXISTS convention_embeddings (
      id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      doc_title  text NOT NULL,
      source_url text NOT NULL DEFAULT '',
      content    text NOT NULL,
      embedding  vector(1024) NOT NULL
  );
  ```
- **청킹**: **빈 줄(문단) 단위**로 끊어 한 청크 = 한 행으로 INSERT. (`doc_title`=문서 제목, `source_url`=사내 위키 링크 있으면 채움/없으면 빈 문자열, `content`=청크 본문, `embedding`=BGE-M3 벡터)
- **정량 수치는 임베딩하지 마세요**: 아래 [M3] 가이드 일부는 맨 위 YAML 프론트매터(`policy_key`, `params`)에 커버리지%·중첩깊이 같은 **숫자 정책**이 있습니다. 이 프론트매터는 **임베딩 대상이 아니라 별도 정책 테이블(`convention_policies`)용**입니다. 임베딩은 `---` 아래 **산문 본문만** 하세요. (정량을 자연어로 파싱하면 PR 판정이 깨짐 — 설계 위험 3)
- **source_url**: 가능하면 각 문서의 사내 위키 URL을 채워 주세요. 비어 있으면 코멘트 생성 LLM이 가짜 링크를 지어낼 수 있습니다.

## 📑 문서 구성

- **Part A [M2·정적분석용]** — Python 코딩 컨벤션(네이밍·선언·들여쓰기·블록·줄바꿈·빈 줄·공백). 주로 **m2(정적분석)** 가 검색.
- **Part B [M3·테스트성능용]** — 커버리지·테스트누락·엣지케이스·N+1·복잡도·메모리 6종. **m3(테스트·성능)** 가 검색.

> 두 파트를 한 테이블에 같이 넣어도 됩니다. 검색은 쿼리 기반이라 m3가 테스트/성능 이슈로 질의하면 관련 문단만 매칭되고, 무관한 문단은 점수가 낮아 자동 제외됩니다.

---

# Part A — Python 코딩 컨벤션 [M2·정적분석용]

## 이름 (Naming)

### 식별자에는 영문/숫자/언더스코어만 허용 `[identifier-char-scope]`
변수명·클래스명·함수명·메서드명에는 영어와 숫자, 언더스코어만 사용한다. 상수에는 단어 구분을 위해 언더스코어(`_`)를 사용한다. 정규표현식 `[^A-Za-z0-9_]`에 부합해야 한다.

### 한국어 발음대로의 표기 금지 `[avoid-korean-pronounce]`
식별자 이름을 한글 발음을 영어로 옮겨서 표기하지 않는다. 한국어 고유명사는 예외.
- 나쁜 예: `moohyung_jasan` (무형자산)
- 좋은 예: `intangible_assets` (무형자산)

### 대문자로 표기할 약어 명시 `[list-uppercase-abbr]`
클래스명·변수명·함수명에 쓰일 단어 중 모든 글자를 대문자로 표기할 약어 목록을 프로젝트별로 명시적으로 정의한다. 단일 프로젝트에서는 클래스명에서도 약어를 일반 단어처럼 표기하고(예: `HttpApiUrl`), 함수·변수명에서는 소문자+언더스코어를 쓴다.
- 좋은 예: `http_api_url = "https://example.com"`, `def parse_http_api_url(url): ...`

### 패키지/모듈 이름은 소문자로 구성 `[package-module-lowercase]`
패키지·모듈 이름은 소문자로 작성한다. 패키지명은 짧게, 모듈명은 단어 구분이 필요할 때 언더스코어(`_`)를 쓸 수 있다.
- 나쁜 예: `import naverCorp.api_gateway`
- 좋은 예: `import navercorp.api_gateway`

### 클래스 이름에 대문자 카멜표기법 적용 `[class-capwords]`
클래스 이름은 단어 첫 글자를 대문자로 시작하는 CapWords(파스칼 표기법)를 사용한다.
- 나쁜 예: `class reservation:`, `class Accesstoken:`
- 좋은 예: `class Reservation:`, `class AccessToken:`

### 클래스 이름에 명사 사용 `[class-noun]`
클래스 이름은 명사나 명사절로 짓는다.

### 추상 클래스/프로토콜 이름에 명사/형용사 사용 `[protocol-abc-noun-adj]`
인터페이스 역할을 하는 `Protocol` 또는 추상 클래스 이름은 명사/명사절 혹은 형용사/형용사절로 짓는다.
- 좋은 예: `class RowMapper(Protocol):`, `class Closable(Protocol):`

### 테스트 파일과 테스트 클래스 이름 규칙 `[test-naming]`
테스트 코드는 파일 이름을 `test_`로 시작하거나 `_test.py`로 끝낸다. 테스트 클래스는 `Test`로 시작한다. (예: `test_watcher.py`, `class TestWatcher:`)

### 함수/메서드 이름에 소문자 스네이크 표기법 `[function-method-snake-case]`
함수·메서드 이름에는 `snake_case`를 사용한다. 테스트 함수 이름에서도 언더스코어를 허용한다.
- 나쁜 예: `def renderHtml():`, `def FindUser():`
- 좋은 예: `def render_html():`, `def find_user():`

### 함수/메서드 이름은 동사/전치사 의미로 시작 `[function-method-verb-preposition]`
함수·메서드명은 동사로 시작한다. 타입 변환 함수에는 `to_`처럼 전치사 의미의 접두어를 쓸 수 있다. 특수 메서드는 `__str__`, `__repr__` 등 파이썬 정의를 사용한다.
- 예: `render_html()`, `to_string()`, `__str__()`, `with_user_id(user_id)`

### 상수는 대문자와 언더스코어로 구성 `[constant-uppercase]`
모듈 수준 또는 클래스 내부에서 상수처럼 쓰는 값은 대문자로 작성하고 복합어는 언더스코어로 구분한다.
- 좋은 예: `UNLIMITED = -1`, `POSTAL_CODE_EXPRESSION = "POST"`

### 변수에 소문자 스네이크 표기법 적용 `[var-snake-case]`
상수가 아닌 멤버변수·지역변수·파라미터에는 `snake_case`를 사용한다.
- 나쁜 예: `Authorized = True`, `AccessToken = 123`
- 좋은 예: `authorized = True`, `access_token = 123`

### 임시 변수 외에는 1글자 이름 사용 금지 `[avoid-1-char-var]`
함수 블록 범위 이상의 생명주기를 가지는 변수에는 1글자 이름을 쓰지 않는다. 반복문 인덱스·람다 파라미터 등 짧은 임시 변수에는 관례적으로 허용.
- 나쁜 예: `p = HtmlParser()`
- 좋은 예: `parser = HtmlParser()`

## 선언 (Declarations)

### 소스 파일에는 관련된 책임만 담기 `[cohesive-module]`
하나의 파일에는 강하게 관련된 클래스·함수·상수만 담는다. 서로 관련 없는 책임을 한 파일에 몰아넣지 않는다.

### 와일드카드 import 금지 `[avoid-star-import]`
import 시 와일드카드(`*`)를 쓰지 않는다. 필요한 이름을 명시하거나 모듈 자체를 import 한다.
- 나쁜 예: `from pathlib import *`
- 좋은 예: `from pathlib import Path` / `import pathlib`

### 접근 수준은 Python 관례로 표현 `[python-visibility-convention]`
공개 API는 접두어 없이, 내부 구현 이름에는 언더스코어 하나(`_`)를 붙인다. 이름 충돌 방지가 필요할 때만 언더스코어 둘(`__`).

### 데코레이터 선언 후 새줄 사용 `[newline-after-decorator]`
데코레이터는 선언 후 새줄을 사용한다. 여러 개면 각각 한 줄씩.
- 좋은 예: `@app.get("/guests")` 다음 줄에 `def find_guests():`

### 한 줄에 한 문장 `[1-state-per-line]`
한 줄에 여러 문장을 쓰지 않는다. 세미콜론으로 잇지 않는다.
- 나쁜 예: `base = 0; weight = 2`

### 하나의 선언문에는 하나의 변수만 `[1-var-per-declaration]`
변수 선언문은 한 문장에서 하나의 변수만 다룬다.
- 나쁜 예: `base = weight = 0`

### 타입 힌트는 변수명 뒤에 선언 `[type-hint-after-name]`
타입 힌트는 변수명 뒤 콜론(`:`)으로 선언한다. 컬렉션은 `list[str]`처럼 타입 뒤에 대괄호.
- 나쁜 예: `str names = []`
- 좋은 예: `names: list[str] = []`

### 긴 숫자에는 언더스코어 사용 `[large-number-underscore]`
긴 숫자 리터럴은 자리 구분을 위해 언더스코어로 적절히 구분한다.
- 좋은 예: `base = 54_423_234_211`

### 특수 문자의 전용 선언 방식을 활용 `[special-escape]`
`\n`, `\t`, `\"` 등 전용 이스케이프가 있는 문자는 `\012` 같은 숫자 선언 대신 전용 방식을 쓴다.
- 좋은 예: `print("---\n---")`

## 들여쓰기 (Indentation)

### 스페이스 사용 `[indentation-space]`
탭 대신 스페이스로 들여쓴다. 탭과 스페이스를 섞지 않는다.

### 들여쓰기는 스페이스 4개 `[4-spaces-indent]`
1단계 들여쓰기는 스페이스 4개.

### 블럭 들여쓰기 `[block-indentation]`
클래스·함수·메서드·조건문·반복문 등 코드 블록이 생길 때마다 1단계 더 들여쓴다.

## 블록 (Blocks)

### 콜론 후 새줄과 들여쓰기 사용 `[colon-indentation-style]`
클래스/함수 선언, 조건/반복문 블록은 줄 마지막에 콜론(`:`)을 쓰고 새줄을 삽입한다. 블록 내부는 스페이스 4개로 들여쓴다.

### else, except, finally는 기준 블록과 같은 들여쓰기 수준 `[sub-flow-aligned]`
`else`, `elif`, `except`, `finally`는 대응되는 `if`/`try`와 같은 들여쓰기 수준에 쓴다.

### 빈 블럭에는 pass 또는 Ellipsis 사용 `[empty-block-pass]`
내용 없는 블록은 `pass`. 스텁·타입 선언 목적의 빈 구현에는 `...`를 쓸 수 있다.

### 조건/반복문은 여러 줄 블록으로 작성 `[prefer-multiline-control-block]`
조건문·반복문이 한 줄로 끝나더라도 여러 줄 블록으로 작성한다.
- 나쁜 예: `if exp is None: return False`
- 좋은 예: `if exp is None:` 다음 줄에 `    return False`

## 줄바꿈 (Line-wrapping)

### 최대 줄 너비 88 `[line-length-88]`
최대 줄 너비는 기본 88자 권장. 프로젝트 별도 기준이 있으면 그 기준을 따른다.

### import 선언문은 한 줄로 `[1-line-import]`
import 선언문 중간에서 줄을 바꾸지 않는다. 하나의 import 문에는 하나의 모듈.

### 줄바꿈 후 추가 들여쓰기 `[indentation-after-line-wrapping]`
줄바꿈 이후 이어지는 줄은 최초 시작 줄보다 최소 1단계 더 들여쓴다.

### 줄바꿈 허용 위치 `[line-wrapping-position]`
줄을 바꾸는 위치는 다음 중 하나: 시작 소괄호 `(` 선언 후, 콤마 `,` 후, 연산자 전, 비교/논리 연산자 전, `is/in/not in` 등, 조건 표현식의 적절한 위치.

## 빈 줄 (Blank lines)

### 모듈 docstring 후 빈 줄 삽입 `[blankline-after-module-docstring]`
모듈 docstring이 있으면 그 뒤에 빈 줄을 삽입하고 import 문을 작성한다.

### import 선언의 순서와 빈 줄 삽입 `[import-grouping]`
import는 ① 표준 라이브러리 ② 서드파티 ③ 로컬 애플리케이션 순서로 그룹을 묶어 선언한다. 그룹 사이에 빈 줄, 같은 그룹 내에서는 알파벳 순 정렬.

### 최상위 함수/클래스 사이에 빈 줄 2줄 삽입 `[blankline-between-top-level-defs]`
모듈 수준 함수·클래스 선언 사이에는 빈 줄 2줄.

### 메서드 사이에 빈 줄 1줄 삽입 `[blankline-between-methods]`
클래스 내부 메서드 선언 사이에는 빈 줄 1줄.

## 공백 (Whitespace)

### 공백으로 줄을 끝내지 않음 `[no-trailing-spaces]`
빈 줄 포함, 모든 줄을 탭/공백으로 끝내지 않는다.

### 괄호 내부에 불필요한 공백 미삽입 `[no-extra-space-inside-brackets]`
리스트·튜플·딕셔너리·함수 호출 괄호 내부에 불필요한 공백을 넣지 않는다.
- 나쁜 예: `values = [ 1, 2, 3 ]`, `get_user( user_id )`
- 좋은 예: `values = [1, 2, 3]`, `get_user(user_id)`

### 제어문 키워드 뒤에 소괄호 사용 지양 `[avoid-parentheses-after-control-keyword]`
`if, for, while, except, with, match` 뒤에는 특별한 이유가 없다면 소괄호를 쓰지 않는다.
- 나쁜 예: `if (max_line > LIMITED):`
- 좋은 예: `if max_line > LIMITED:`

### 식별자와 여는 소괄호 사이에 공백 미삽입 `[no-space-between-identifier-parentheses]`
함수 선언/호출/데코레이터 뒤 여는 소괄호 사이에 공백을 넣지 않는다.
- 나쁜 예: `class StringProcessor ():`, `def remove_ending_dot (original):`

### 타입 변환 함수 호출의 공백 규칙 `[type-conversion-whitespace]`
`str(), int(), float(), bool()` 등은 함수명과 소괄호 사이/내부에 공백을 넣지 않는다.
- 나쁜 예: `message = str ( raw_line )`
- 좋은 예: `message = str(raw_line)`

### 타입 힌트 대괄호의 공백 규칙 `[type-hint-whitespace]`
타입 힌트 대괄호(`[`, `]`) 주위: `[` 뒤·`]` 앞에 공백 없음, 타입명과 `[` 사이 공백 없음, 콤마 뒤에는 공백.
- 좋은 예: `names: list[str] = []`, `options: dict[str, int] = {}`

### 콤마의 뒤에만 공백 삽입 `[space-after-comma]`
콤마(`,`)에는 뒤에만 공백을 삽입한다.
- 나쁜 예: `def display(level,message,index):`
- 좋은 예: `def display(level, message, index):`

### 콜론의 공백 규칙 `[colon-whitespace]`
제어문/함수/클래스 선언의 마지막 콜론 앞에는 공백 없음. 딕셔너리 키:값은 콜론 앞 공백 없음·뒤 공백 있음. 타입 힌트는 변수명 뒤 콜론 앞 공백 없음·뒤 공백 있음. 슬라이싱은 콜론 앞뒤 공백 없음.
- 좋은 예: `user = {"id": 1, "name": "Kim"}`, `user_id: int = 1`, `first_three = values[:3]`

### 이항/삼항 연산자의 앞 뒤에 공백 삽입 `[space-around-binary-ternary-operator]`
이항 연산자·조건 표현식의 주요 연산자 앞뒤에 공백.
- 좋은 예: `final_score += weight * raw_score - absent_count`, `message = "valid" if is_valid else "invalid"`

### 단항 연산자와 연산 대상 사이에 공백을 미삽입 `[no-space-unary-operator]`
단항 연산자와 대상 사이에 공백을 넣지 않는다.
- 좋은 예: `point = scores[-index] * -1`, `is_valid = not active`

### 주석문 기호 전후의 공백 삽입 `[space-around-comment]`
명령문과 같은 줄에 주석을 붙일 때 `#` 앞에는 공백 2개, `#` 뒤에는 공백 1개.
- 좋은 예: `print(True)  # 앞 공백 2, 뒤 공백 1`

---

# Part B — 테스트·성능 가이드 [M3·테스트성능용]

> 아래 6종은 m3 탐지기(TEST-001/003/004, PERF-001/002/003)와 짝. **맨 위 YAML 프론트매터(숫자 정책)는 임베딩하지 말고 정책 테이블용으로, `---` 아래 산문만 임베딩**하세요.

## 1) 테스트 커버리지 가이드 — TEST-001 (커버리지 미충족)
*(정량 정책: 기본 0.80 / payment·auth 0.90 / legacy 0.70 — 프론트매터, 임베딩 제외)*

**우리 팀의 원칙** — 테스트는 "있으면 좋은 것"이 아니라 변경의 일부입니다. 새 코드나 고친 코드에는 그 동작을 확인하는 테스트가 함께 와야 하며, 테스트 없는 변경은 리뷰에서 되돌려 보냅니다. 커버리지 숫자는 목표가 아니라 "검증되지 않은 코드가 얼마나 들어왔는지"를 보는 신호입니다.

**모듈마다 기준이 다릅니다** — 결제·인증처럼 사고가 곧 금전·보안 피해로 이어지는 모듈은 더 엄격한 기준을, 손대기 어려운 레거시는 한시적으로 완화한 기준을 적용합니다. 기준 수치는 정책으로 관리하며, 바꾸려면 숫자만 고쳐 다시 적재하면 됩니다(코드 수정·배포 불필요).

**커버리지가 낮다는 지적을 받으면** — 숫자를 채우려 의미 없는 테스트를 늘리지 마세요. 변경한 함수의 핵심 동작, 분기(조건문 양쪽), 실패 경로부터 덮는 것이 우선입니다. 라인은 지나갔지만 분기는 놓치는 경우가 많으니, 조건문이 있으면 참/거짓 양쪽을 모두 테스트했는지 확인하세요.

## 2) 테스트 누락 가이드 — TEST-004 (테스트 누락)
**우리 팀의 원칙** — 외부에서 호출되는 public 함수에는 단위 테스트가 하나 이상 있어야 합니다. "간단해서 필요 없다"고 느껴지는 함수일수록 나중에 조용히 동작이 바뀌어도 아무도 모르게 되는 위험이 큽니다. 테스트는 그 함수가 "지금 무엇을 하기로 약속했는지"를 코드로 박아두는 계약서입니다.

**무엇을 먼저 테스트하나** — 비즈니스 규칙이 든 함수, 돈·권한·외부 데이터를 다루는 함수, 버그 영향이 큰 함수부터. 단순 위임 래퍼나 자명한 getter는 우선순위가 낮습니다.

**테스트 작성·배치 규칙** — 테스트는 대상 모듈과 짝이 되는 위치(`tests/`)에 두고, 이름에서 "무엇을 검증하는지"가 드러나게 짓습니다. 한 테스트는 한 가지를 검증하고, 새 함수를 추가하는 PR이면 그 함수의 테스트도 같은 PR에 포함하는 것이 기본값입니다.

## 3) 엣지케이스 가이드 — TEST-003 (엣지케이스 누락)
**우리 팀의 원칙** — 정상 입력만 테스트한 코드는 절반만 검증된 코드입니다. 실제 장애는 대부분 "예상 못 한 입력"에서 납니다. 함수가 받는 값의 경계와 빈 상태를 항상 함께 생각하고 테스트하세요.

**꼭 확인하는 입력들** — `None`, 빈 문자열·빈 리스트·빈 딕셔너리, 숫자의 0과 음수, 비율·할인율처럼 범위가 있는 값의 경계(0, 1, 범위 밖), 리스트의 첫/마지막/범위 밖 인덱스. 인자 이름이 `price`, `rate`, `ids`, `count`, `items` 패턴이면 특히 빠뜨리기 쉽습니다.

**지적을 받으면** — "이 입력이 들어오면 어떻게 동작해야 하는가"를 먼저 정하세요. 막아야 하면 명시적으로 검증·예외 처리하고, 허용한다면 그 동작을 테스트로 고정합니다. 조용히 잘못된 값을 반환하는 것이 가장 위험합니다 — 차라리 빨리, 분명하게 실패하게 만드세요.

## 4) N+1 쿼리 가이드 — PERF-002 (N+1 쿼리)
**우리 팀의 원칙** — 반복문 안에서 DB나 외부 API를 호출하는 패턴(N+1)은 리뷰에서 막습니다. 항목이 10개일 때는 멀쩡해 보여도, 운영에서 수천 개가 되면 호출이 그 수만큼 늘어 응답 지연·DB 부하의 주범이 됩니다. 목록을 다루기 전에 "한 번에 가져올 수 있는가"를 먼저 묻습니다.

**표준 해결책** — 연관 데이터를 미리 함께 불러옵니다. SQLAlchemy에서는 `selectinload`(목록 관계)·`joinedload`(단일 관계)를 상황에 맞게, 직접 쿼리면 반복문 밖에서 ID 목록으로 한 번에 조회 후 메모리에서 매핑합니다. 핵심은 "루프 횟수만큼 쿼리가 늘지 않게".

**지적을 받으면** — 그 호출이 정말 반복마다 필요한지 봅니다. 대부분 루프 밖으로 끌어내 한 번에 조회하도록 바꿀 수 있습니다. 캐싱으로 N+1을 가리기보다 호출 자체를 줄이는 것이 우선입니다.

## 5) 시간복잡도 가이드 — PERF-001 (시간복잡도)
*(정량 정책: minor_depth 2 / major_depth 3 — 프론트매터, 임베딩 제외)*

**우리 팀의 원칙** — 중첩 루프가 깊어질수록 데이터가 늘 때 처리 시간이 급격히 증가합니다(O(n²), O(n³)…). 일정 깊이 이상의 중첩 루프는 리뷰에서 반드시 확인하고 줄일 수 없는지 따집니다. 데이터가 적은 지금은 문제없어 보여도, 규모가 커지면 가장 먼저 느려지는 지점입니다.

**줄이는 방법** — 대부분의 중첩 루프는 자료구조를 바꾸면 평탄해집니다. 안쪽 루프가 "바깥 항목을 찾는" 용도면 딕셔너리·집합(set)으로 O(1) 조회하도록 바꿔 이중 루프를 단일 루프로 낮춥니다. 정렬·그룹핑으로 비교 횟수를 줄이는 방법도 자주 씁니다.

**지적을 받으면** — "이 루프가 비교하는 대상"을 보고 미리 인덱싱(dict/set)할 수 있는지 확인하세요. 알고리즘 변경이 어렵다면 입력 크기에 상한이 보장되는지를 근거로 남겨 리뷰어가 판단하게 합니다.

## 6) 메모리 누수 가이드 — PERF-003 (메모리 누수)
**우리 팀의 원칙** — 프로세스가 오래 사는 서버에서는 "조금씩 쌓이는" 메모리가 결국 장애로 이어집니다. 전역(모듈 레벨) 컬렉션에 데이터를 계속 append 하며 비우지 않는 패턴을 특히 경계합니다. 한 요청에선 작아 보여도 같은 코드가 수만 번 실행되면 메모리가 무한히 늡니다.

**자주 나오는 위험 패턴** — 모듈 전역 리스트·딕셔너리(예: `EVENTS = []`)에 요청마다 추가하고 제거하지 않는 경우, 만료·최대 크기 없는 자작 캐시, 클로저·콜백이 큰 객체를 계속 참조해 해제되지 못하는 경우.

**지적을 받으면** — 그 컬렉션이 "언제 비워지는가"를 명확히 하세요. 요청 범위 데이터라면 전역이 아니라 함수 안 지역 변수로, 캐시가 필요하면 최대 크기·만료가 있는 구조(`functools.lru_cache`, TTL 캐시)를 씁니다. "왜 전역에 쌓아야 하는가"에 답할 수 없다면 대개 누수입니다.
