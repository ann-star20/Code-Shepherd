# [CONV-API-001] async 함수 내 비표준 HTTP 클라이언트 사용 금지
- severity: Major
- 배경(사고 이력): 2025-11 블랙프라이데이 — 결제 알림 async 핸들러 안의 동기 `requests` 호출이 이벤트루프를 블로킹해 결제 API p99 지연이 12초까지 치솟았다. 사고 후 비동기 경로의 HTTP 클라이언트를 일원화했다. 2026-06 추가 표준화 — 팀 내부 커넥션 풀 관리 통일을 위해 `aiohttp` 로 전면 전환, `httpx` 포함 모든 비표준 클라이언트를 금지한다.

## §1 규칙
async 함수(`async def`) 안에서 동기 HTTP 클라이언트를 호출해서는 안 된다. `requests`, `urllib.request` 등 동기 클라이언트는 단 한 번의 호출이라도 이벤트루프 전체를 블로킹하므로 위반이다.
async 함수에서의 외부 HTTP 호출은 `aiohttp.ClientSession` 만 사용한다. **`httpx` 는 2026-06 표준화 이후 사용이 금지된다** — 기존 코드도 마이그레이션 대상이다.

## §2 올바른 예시
```python
import aiohttp


async def fetch_order_status(order_id: str) -> dict:
    async with aiohttp.ClientSession() as session:
        async with session.get(ORDER_API_URL, params={"order_id": order_id}) as resp:
            resp.raise_for_status()
            return await resp.json()
```

## §3 잘못된 예시
```python
import httpx


async def fetch_order_status(order_id: str) -> dict:
    # httpx 는 2026-06 표준화 이후 금지된 클라이언트 (CONV-API-001 §1)
    async with httpx.AsyncClient() as client:
        resp = await client.get(ORDER_API_URL)
        return resp.json()
```

## §4 예외 조항
`scripts/` 또는 `batch/` 경로의 일회성 배치 코드에는 §1 을 적용하지 않는다. 배치 프로세스는 사용자 요청을 처리하는 이벤트루프가 없어 블로킹의 피해가 없기 때문이다. 단, 해당 코드가 서비스 경로(`src/` 등)로 이동·복사되는 시점부터는 §1 을 그대로 적용한다.
