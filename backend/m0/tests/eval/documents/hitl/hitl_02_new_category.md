# 양자컴퓨팅 기반 암호화 기술 가이드

## 개요

양자컴퓨팅(Quantum Computing)은 기존 이진법 비트 대신 양자비트(qubit)를 사용하여
지수적으로 증가하는 연산 능력을 제공한다.

## 양자 암호화의 필요성

RSA, ECC 등 현재 널리 사용되는 공개키 암호 체계는
충분히 강력한 양자 컴퓨터가 등장하면 Shor 알고리즘으로 수분 내에 해독 가능하다.

## 주요 기술

### 양자 키 분배 (QKD)

- BB84 프로토콜: 광자의 편광 상태를 이용한 키 교환
- E91 프로토콜: 양자 얽힘(Entanglement)을 활용

### 격자 기반 암호 (Post-Quantum Cryptography)

- CRYSTALS-Kyber: NIST 표준 선정 (2024)
- CRYSTALS-Dilithium: 디지털 서명 표준

## 현황

NIST는 2024년 Post-Quantum Cryptography 표준 3종을 확정했다.
IBM, Google, IonQ 등이 상용 양자 컴퓨터 서비스를 제공 중이다.

## 우리 팀 대응 방안

2026년까지 TLS 1.3 + 하이브리드 PQC 도입 검토.
현재 사용 중인 RSA-2048 키의 마이그레이션 계획 수립 필요.
