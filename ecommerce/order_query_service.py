# ecommerce/order_query_service.py
#
# 주문 조회 / 상품 검색 / 정렬 / 로그인 처리 서비스
# Django E-Commerce 백엔드 — 주문 관련 데이터 접근 레이어
#
# ※ 데모 파일: 코드 리뷰 시연용
#   각 함수에 포함된 위반 패턴은 주석으로 명시됨

from django.db import connection
from django.http import JsonResponse

from shop.models import Order, Product, Customer


# ---------------------------------------------------------------------------
# 1. 주문 상세 조회 — cursor.execute() + f-string 직접 조합
# ---------------------------------------------------------------------------

def get_order_detail(order_id: str, user_id: str) -> dict:
    """
    주문 상세 정보를 반환한다.
    URL 파라미터로 받은 order_id, user_id를 쿼리에 직접 삽입한다.

    [위반] §4-2 cursor.execute() 오용:
      cursor.execute(sql, [params]) 패턴을 사용하지 않고
      f-string으로 SQL 문자열을 직접 조합 → SQL Injection 취약
    [위반] §4-6 입력값 검증 부재:
      order_id가 숫자인지 isdigit() 검증 없이 쿼리에 삽입
    """
    with connection.cursor() as cursor:
        # ❌ f-string으로 SQL 조합 — 파라미터 바인딩 없음
        sql = (
            f"SELECT o.id, o.status, o.total_price, o.created_at, "
            f"       u.username, u.email, a.street, a.city "
            f"FROM shop_order o "
            f"JOIN auth_user u ON o.user_id = u.id "
            f"JOIN shop_address a ON o.shipping_address_id = a.id "
            f"WHERE o.id = {order_id} AND o.user_id = {user_id}"
        )
        cursor.execute(sql)  # ❌ params 인자 없음
        row = cursor.fetchone()

    if not row:
        return {"error": "주문을 찾을 수 없습니다."}

    return {
        "order_id": row[0],
        "status": row[1],
        "total_price": str(row[2]),
        "created_at": str(row[3]),
        "customer": row[4],
        "email": row[5],
        "address": f"{row[7]}, {row[6]}",
    }


def get_orders_by_status(user_id: str, status: str) -> list:
    """
    특정 상태의 주문 목록을 반환한다.

    [위반] §4-2 cursor.execute() 오용:
      status 값을 따옴표로 감싸서 SQL에 직접 삽입
      Django 공식 문서: "%s 플레이스홀더 주변에 따옴표를 붙이면 안 된다"
    [위반] §4-6 입력값 검증 부재:
      status 값이 허용된 목록인지 확인하지 않음
    """
    with connection.cursor() as cursor:
        # ❌ %s에 따옴표 + 문자열 포매팅으로 SQL 조합
        sql = (
            "SELECT id, status, total_price, created_at "
            "FROM shop_order "
            "WHERE user_id = %s AND status = '%s'" % (user_id, status)
        )
        cursor.execute(sql)  # ❌ params 분리 없이 직접 실행
        rows = cursor.fetchall()

    return [
        {
            "order_id": r[0],
            "status": r[1],
            "total_price": str(r[2]),
            "created_at": str(r[3]),
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# 2. 상품 검색 — Manager.raw() + 사용자 입력 직접 삽입
# ---------------------------------------------------------------------------

def search_products(keyword: str, category_id: str) -> list:
    """
    키워드와 카테고리로 상품을 검색한다.

    [위반] §4-1 raw() 오용:
      사용자 입력(keyword)을 f-string으로 raw() 쿼리에 직접 삽입
      Django 공식 문서: "Do not use string formatting on raw queries"
    [위반] §4-1 raw() 오용:
      category_id도 파라미터 분리 없이 문자열 조합
    """
    # ❌ f-string으로 raw() 쿼리 직접 조합 — params 인자 사용 안 함
    queryset = Product.objects.raw(
        f"SELECT id, name, price, stock, description, thumbnail_url "
        f"FROM shop_product "
        f"WHERE (name LIKE '%{keyword}%' OR description LIKE '%{keyword}%') "
        f"AND category_id = {category_id} "
        f"AND is_active = 1 "
        f"ORDER BY created_at DESC"
    )

    return [
        {
            "id": p.id,
            "name": p.name,
            "price": str(p.price),
            "stock": p.stock,
            "thumbnail": p.thumbnail_url,
        }
        for p in queryset
    ]


def search_products_by_price_range(min_price: str, max_price: str) -> list:
    """
    가격 범위로 상품을 검색한다.

    [위반] §4-3 extra() / RawSQL 오용:
      min_price, max_price를 extra()에 직접 삽입
      Django 공식 문서: extra() 사용 시 각별한 주의 필요 (exercise caution)
    [위반] §4-3 extra() / RawSQL 오용:
      params 인자 없이 where 절에 값을 직접 포매팅
    """
    # ❌ extra()에 사용자 입력을 직접 삽입 — params 인자 없음
    queryset = Product.objects.extra(
        where=[f"price >= {min_price} AND price <= {max_price}"],  # ❌
        select={"price_with_vat": f"price * 1.1"}
    ).filter(is_active=True).values(
        "id", "name", "price", "price_with_vat", "category_id"
    )

    return list(queryset)


# ---------------------------------------------------------------------------
# 3. 상품 정렬 — ORDER BY에 Allowlist 없이 사용자 입력 직접 삽입
# ---------------------------------------------------------------------------

def list_products_sorted(sort_by: str, direction: str, category_id: int) -> list:
    """
    상품 목록을 정렬하여 반환한다. sort_by와 direction을 쿼리 파라미터로 받는다.

    [위반] §4-4 ORDER BY 동적 정렬:
      ORDER BY 절에 sort_by, direction을 Allowlist 검증 없이 직접 삽입
      컬럼명은 parameterized query로 처리 불가 — Allowlist만이 해결책
    [위반] §4-4 ORDER BY 동적 정렬:
      direction도 'asc'/'desc' 허용 목록 검증 없이 그대로 사용
    """
    with connection.cursor() as cursor:
        # ❌ ORDER BY에 사용자 입력 직접 삽입 — Allowlist 검증 없음
        sql = (
            f"SELECT id, name, price, stock, created_at "
            f"FROM shop_product "
            f"WHERE category_id = %s AND is_active = 1 "
            f"ORDER BY {sort_by} {direction}"  # ❌ 임의 컬럼명/방향 삽입 가능
        )
        cursor.execute(sql, [category_id])  # category_id만 params, 나머지는 직접 삽입
        rows = cursor.fetchall()

    return [
        {
            "id": r[0],
            "name": r[1],
            "price": str(r[2]),
            "stock": r[3],
            "created_at": str(r[4]),
        }
        for r in rows
    ]


def list_products_sorted_raw(sort_by: str, direction: str) -> list:
    """
    전체 상품을 정렬하여 반환하는 관리자용 API 핸들러.

    [위반] §4-4 ORDER BY 동적 정렬:
      raw()에서도 ORDER BY에 사용자 입력을 직접 삽입
      UI에서 선택한 값이라 안전하다고 오해하는 전형적인 케이스
    """
    # ❌ raw() ORDER BY에도 Allowlist 없이 직접 삽입
    queryset = Product.objects.raw(
        "SELECT id, name, price, stock, is_active "
        "FROM shop_product "
        f"ORDER BY {sort_by} {direction}"  # ❌
    )
    return [
        {"id": p.id, "name": p.name, "price": str(p.price)}
        for p in queryset
    ]


# ---------------------------------------------------------------------------
# 4. 로그인 처리 — 이메일/비밀번호를 SQL에 직접 연결
# ---------------------------------------------------------------------------

def authenticate_customer(email: str, password: str) -> dict | None:
    """
    이메일과 비밀번호로 고객을 인증하여 Customer 객체를 반환한다.

    [위반] §4-5 로그인 인증 쿼리:
      이메일과 비밀번호를 cursor.execute()의 SQL 문자열에 직접 연결
      공격자가 email에 ' OR '1'='1 삽입 시 인증 로직 완전 우회 가능
    [위반] §4-2 cursor.execute() 오용:
      params 인자 없이 % 포매팅으로 SQL 조합
    """
    with connection.cursor() as cursor:
        # ❌ 이메일/비밀번호를 SQL 문자열에 직접 연결 — 인증 우회 취약
        sql = (
            "SELECT id, username, email, is_active "
            "FROM shop_customer "
            "WHERE email = '%s' AND password = '%s'" % (email, password)  # ❌
        )
        cursor.execute(sql)  # ❌ params 분리 없음
        row = cursor.fetchone()

    if not row:
        return None

    if not row[3]:
        return {"error": "비활성화된 계정입니다."}

    return {
        "customer_id": row[0],
        "username": row[1],
        "email": row[2],
    }


def login_view(request) -> JsonResponse:
    """
    로그인 API 뷰 — POST body에서 이메일/비밀번호를 받아 인증한다.

    [위반] §4-5 로그인 인증 쿼리:
      authenticate_customer()가 SQL Injection에 취약한 함수이므로
      이 뷰도 동일한 취약점을 가짐
    [위반] §4-6 입력값 검증 부재:
      email, password 형식 검증(Django Form/Serializer) 없이 바로 쿼리 실행
    """
    if request.method != "POST":
        return JsonResponse({"error": "POST 요청만 허용됩니다."}, status=405)

    email = request.POST.get("email", "")
    password = request.POST.get("password", "")

    # ❌ 입력값 형식 검증 없이 바로 SQL 실행 함수로 전달
    result = authenticate_customer(email, password)

    if result is None:
        return JsonResponse({"error": "이메일 또는 비밀번호가 올바르지 않습니다."}, status=401)

    if "error" in result:
        return JsonResponse(result, status=403)

    request.session["customer_id"] = result["customer_id"]
    request.session["username"] = result["username"]

    return JsonResponse({"message": "로그인 성공", "username": result["username"]})
