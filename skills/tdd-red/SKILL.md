---
name: tdd-red
description: TASK 항목을 입력받아 실패하는 pytest 테스트 파일을 먼저 작성합니다.
---
# Skill: tdd-red

## 트리거 조건

"테스트 먼저 만들어줘", "Red 단계 진행", "TDD 시작", "실패 테스트 작성" 등의 요청이 들어올 때

## 역할

TASK.md의 특정 TASK를 입력받아 실패하는 pytest 테스트 파일과 빈 함수 껍데기를 생성합니다.

## 입력

- `TASK.md`의 특정 TASK ID (예: T01)
- 또는 기능 설명 직접 입력

## 출력

- `test_<모듈명>.py` — pytest 테스트 파일 (실행 시 FAILED 상태)
- `<모듈명>.py` — 빈 함수 껍데기 (ImportError 방지용, 구현 없음)

## 제약사항

- 구현 코드 작성 금지 (빈 함수에 `pass`만 허용)
- 테스트 실행 시 반드시 FAILED 상태여야 함
- 각 테스트는 Given/When/Then 주석 포함
- Happy Path, Edge Case, Error Case를 각각 1개 이상 포함

## 예시

입력: T01 (할 일 추가 기능)  
출력: test_todo.py (FAILED), todo.py (pass만 있는 껍데기)
