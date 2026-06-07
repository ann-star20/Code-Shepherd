---
name: task-breakdown
description: PRD.md를 읽어 원자적 TASK 단위로 분해하고 TASK.md를 생성합니다.
---
# Skill: task-breakdown

## 트리거 조건

"TASK로 분해해줘", "TASK.md 만들어줘", "PRD를 태스크로 나눠줘" 등의 요청이 들어올 때

## 역할

PRD.md의 기능 목록을 원자적 TASK 단위로 분해하여 TASK.md를 생성합니다.

## 입력

- `PRD.md` (프로젝트 루트에 위치)

## 출력

- `TASK.md` (프로젝트 루트에 생성)
- 각 TASK: ID, 우선순위, 제목, 완료 조건(체크박스), 예상 테스트명, 의존 관계

## 제약사항

- TASK 하나는 30분~2시간 이내 완료 가능한 크기
- 완료 조건은 pytest로 검증 가능하게 작성
- "잘 작동한다", "적절히 처리" 같은 모호한 완료 조건 금지

## 예시

입력: PRD.md (할 일 추가/조회/완료/삭제 기능)  
출력: TASK.md (T01 추가, T02 조회, T03 완료, T04 삭제 — 각 TASK에 완료 조건 포함)
