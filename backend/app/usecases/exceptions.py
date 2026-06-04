"""유스케이스 계층 커스텀 예외."""


class StagingConflictError(Exception):
    """SELECT FOR UPDATE SKIP LOCKED가 0행을 반환할 때 발생.

    동일 session_id에 대한 동시 approve 요청 중
    다른 트랜잭션이 이미 DRAFT 행을 잠금 보유 중임을 의미한다.
    """
