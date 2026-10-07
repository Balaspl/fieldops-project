"""
SQL Injection Regression Test Suite
===================================

Purpose
-------
Verify that attacker-controlled input cannot:

1. Alter SQL query semantics.
2. Bypass authentication.
3. Return unintended records through search/filter parameters.
4. Cause SQL syntax/database errors.
5. Modify or destroy application data.
6. Break normal endpoint behavior after malicious requests.

These are regression tests. They do NOT require the application to
explicitly reject SQL-looking strings. Parameterized SQLAlchemy queries
may safely accept such strings and simply return no matching records.

Expected security property:
    User input must remain DATA, never SQL.
"""

import pytest


# ---------------------------------------------------------------------------
# SQL injection payload corpus
# ---------------------------------------------------------------------------

SQL_INJECTION_PAYLOADS = [
    "' OR '1'='1",
    "' OR 1=1 --",
    "' OR '1'='1' --",
    "' OR 1=1#",
    "' OR 1=1/*",
    "') OR ('1'='1",
    "\") OR (\"1\"=\"1",
    "admin'--",
    "admin' #",
    "'; SELECT * FROM users; --",
    "'; DROP TABLE users; --",
    "'; DELETE FROM users; --",
    "'; UPDATE users SET email='attacker@example.com'; --",
    "' UNION SELECT NULL --",
    "' UNION SELECT 1,2,3 --",
    "1' UNION SELECT NULL,NULL --",
    "' AND 1=2 --",
    "' AND 'x'='y",
]


# Payloads that should never authenticate as a real user.
AUTH_SQL_INJECTION_PAYLOADS = [
    "' OR '1'='1",
    "' OR 1=1 --",
    "' OR 1=1#",
    "admin'--",
    "' UNION SELECT NULL --",
    "'; DROP TABLE users; --",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def assert_safe_collection_response(response):
    """
    A SQL-injection attempt against a collection endpoint must not produce
    a server/database error.

    A secure parameterized query may return:
        200 + []

    It may also legitimately return a validation error such as:
        400 / 422

    What must NOT happen:
        500
        SQL/database exception
        successful query manipulation
    """

    assert response.status_code != 500, (
        "SQL injection payload caused an internal server error: "
        f"{response.status_code} {response.text}"
    )

    if response.status_code == 200:
        data = response.json()

        assert isinstance(data, list), (
            "Expected a collection response from the endpoint"
        )

        return data

    # Validation/rejection is also acceptable.
    assert response.status_code in {
        400,
        401,
        403,
        404,
        422,
        429,
    }, (
        "Unexpected response to SQL injection payload: "
        f"{response.status_code} {response.text}"
    )

    return None


# ===========================================================================
# AUTHENTICATION SQL INJECTION
# ===========================================================================


@pytest.mark.parametrize(
    "payload",
    AUTH_SQL_INJECTION_PAYLOADS,
)
def test_login_email_sql_injection_cannot_authenticate(client, payload):
    """
    SQL injection in the login email must never authenticate a user.

    Security requirement:
        A malicious email must be treated as a literal email value.

    Expected:
        401 Unauthorized
        or another safe validation/rate-limit response.

    Must never:
        - return access_token
        - return refresh_token
        - return 200
        - return 500
    """

    response = client.post(
        "/auth/login",
        json={
            "email": payload,
            "password": "WrongPassword123!",
        },
    )

    assert response.status_code != 200, (
        "Potential authentication SQL injection vulnerability: "
        f"payload={payload!r}, response={response.text}"
    )

    assert response.status_code != 500, (
        "SQL injection caused an internal server error: "
        f"payload={payload!r}, response={response.text}"
    )

    assert response.status_code in {
        400,
        401,
        403,
        422,
        423,
        429,
    }


@pytest.mark.parametrize(
    "payload",
    AUTH_SQL_INJECTION_PAYLOADS,
)
def test_login_password_sql_injection_cannot_bypass_auth(
    client,
    payload,
):
    """
    SQL injection placed in the password must not bypass authentication.

    The email is deliberately invalid so this test verifies that the
    password field cannot influence the SQL authentication predicate.
    """

    response = client.post(
        "/auth/login",
        json={
            "email": "nonexistent-sql-regression@example.invalid",
            "password": payload,
        },
    )

    assert response.status_code != 200, (
        "Potential authentication bypass through password SQL injection: "
        f"payload={payload!r}"
    )

    assert response.status_code != 500, (
        "SQL injection caused an internal server error: "
        f"payload={payload!r}, response={response.text}"
    )


# ===========================================================================
# JOB SEARCH SQL INJECTION
# ===========================================================================


@pytest.mark.parametrize(
    "payload",
    SQL_INJECTION_PAYLOADS,
)
def test_jobs_search_sql_injection_does_not_return_all_records(
    client,
    override_auth,
    authenticated_user,
    payload,
):
    """
    Verify that /jobs/?search=... cannot transform a normal search into
    an always-true SQL predicate.

    A classic vulnerable implementation could turn:

        search = "' OR 1=1 --"

    into an SQL condition equivalent to:

        WHERE customer_name LIKE '%' OR 1=1

    The application uses SQLAlchemy filtering and should instead treat
    the payload as literal text.
    """

    override_auth(authenticated_user)

    response = client.get(
        "/jobs/",
        params={"search": payload},
    )

    data = assert_safe_collection_response(response)

    if data is not None:
        # These payloads should not normally match legitimate records.
        # If the endpoint contains a deliberately seeded record matching
        # the payload, the test may need to use a more unique payload.
        assert len(data) == 0, (
            "SQL injection payload unexpectedly returned records: "
            f"payload={payload!r}, returned={len(data)}"
        )


@pytest.mark.parametrize(
    "payload",
    SQL_INJECTION_PAYLOADS,
)
def test_jobs_location_sql_injection_is_treated_as_data(
    client,
    override_auth,
    authenticated_user,
    payload,
):
    """
    Verify that the location filter cannot be converted into arbitrary SQL.
    """

    override_auth(authenticated_user)

    response = client.get(
        "/jobs/",
        params={"location": payload},
    )

    data = assert_safe_collection_response(response)

    if data is not None:
        assert len(data) == 0, (
            "Location SQL injection unexpectedly returned records: "
            f"payload={payload!r}"
        )


@pytest.mark.parametrize(
    "payload",
    SQL_INJECTION_PAYLOADS,
)
def test_jobs_status_sql_injection_is_treated_as_data(
    client,
    override_auth,
    authenticated_user,
    payload,
):
    """
    Verify that the status filter cannot alter the SQL predicate.
    """

    override_auth(authenticated_user)

    response = client.get(
        "/jobs/",
        params={"status": payload},
    )

    data = assert_safe_collection_response(response)

    if data is not None:
        assert len(data) == 0, (
            "Status SQL injection unexpectedly returned records: "
            f"payload={payload!r}"
        )


@pytest.mark.parametrize(
    "payload",
    SQL_INJECTION_PAYLOADS,
)
def test_jobs_priority_sql_injection_is_treated_as_data(
    client,
    override_auth,
    authenticated_user,
    payload,
):
    """
    Verify that the priority filter cannot alter SQL semantics.
    """

    override_auth(authenticated_user)

    response = client.get(
        "/jobs/",
        params={"priority": payload},
    )

    data = assert_safe_collection_response(response)

    if data is not None:
        assert len(data) == 0, (
            "Priority SQL injection unexpectedly returned records: "
            f"payload={payload!r}"
        )


@pytest.mark.parametrize(
    "payload",
    SQL_INJECTION_PAYLOADS,
)
def test_jobs_service_type_sql_injection_is_treated_as_data(
    client,
    override_auth,
    authenticated_user,
    payload,
):
    """
    Verify that service_type cannot be used to inject SQL.
    """

    override_auth(authenticated_user)

    response = client.get(
        "/jobs/",
        params={"service_type": payload},
    )

    data = assert_safe_collection_response(response)

    if data is not None:
        assert len(data) == 0, (
            "Service type SQL injection unexpectedly returned records: "
            f"payload={payload!r}"
        )


@pytest.mark.parametrize(
    "payload",
    SQL_INJECTION_PAYLOADS,
)
def test_jobs_sla_sql_injection_is_treated_as_data(
    client,
    override_auth,
    authenticated_user,
    payload,
):
    """
    Verify that SLA filtering cannot be manipulated through SQL injection.
    """

    override_auth(authenticated_user)

    response = client.get(
        "/jobs/",
        params={"sla": payload},
    )

    data = assert_safe_collection_response(response)

    if data is not None:
        assert len(data) == 0, (
            "SLA SQL injection unexpectedly returned records: "
            f"payload={payload!r}"
        )


# ===========================================================================
# PENDING JOB SEARCH
# ===========================================================================


@pytest.mark.parametrize(
    "payload",
    SQL_INJECTION_PAYLOADS,
)
def test_pending_jobs_search_sql_injection_is_blocked(
    client,
    override_auth,
    authenticated_user,
    payload,
):
    """
    Verify that /jobs/pending?search=... cannot bypass pending-job filters.
    """

    override_auth(authenticated_user)

    response = client.get(
        "/jobs/pending",
        params={"search": payload},
    )

    data = assert_safe_collection_response(response)

    if data is not None:
        assert len(data) == 0, (
            "Pending jobs SQL injection unexpectedly returned records: "
            f"payload={payload!r}"
        )


# ===========================================================================
# SQL COMMENT / UNION REGRESSION CASES
# ===========================================================================


@pytest.mark.parametrize(
    "payload",
    [
        "'--",
        "' #",
        "'/*",
        "*/ OR 1=1 --",
        "' UNION SELECT NULL --",
        "' UNION ALL SELECT NULL --",
        "1 UNION SELECT 1",
    ],
)
def test_jobs_comment_and_union_payloads_are_not_executed(
    client,
    override_auth,
    authenticated_user,
    payload,
):
    """
    Specifically exercise SQL comment and UNION-style payloads.

    These are important because a vulnerable string-concatenated query
    may terminate the original predicate and append attacker SQL.
    """

    override_auth(authenticated_user)

    response = client.get(
        "/jobs/",
        params={"search": payload},
    )

    data = assert_safe_collection_response(response)

    if data is not None:
        assert len(data) == 0, (
            "Comment/UNION SQL payload unexpectedly returned records: "
            f"payload={payload!r}"
        )


# ===========================================================================
# DATABASE-DESTRUCTIVE PAYLOAD REGRESSION
# ===========================================================================


@pytest.mark.parametrize(
    "payload",
    [
        "'; DROP TABLE users; --",
        "'; DROP TABLE jobs; --",
        "'; DELETE FROM users; --",
        "'; DELETE FROM jobs; --",
        "'; UPDATE users SET email='attacker@example.com'; --",
    ],
)
def test_destructive_sql_payloads_cannot_execute(
    client,
    override_auth,
    authenticated_user,
    payload,
):
    """
    Regression test for stacked/destructive SQL statements.

    The endpoint must treat these values as ordinary search strings.

    We intentionally do NOT execute raw SQL in this test. The security
    property is verified through the API boundary.
    """

    override_auth(authenticated_user)

    response = client.get(
        "/jobs/",
        params={"search": payload},
    )

    assert response.status_code != 500, (
        "Destructive SQL payload reached an unsafe database execution path: "
        f"payload={payload!r}, response={response.text}"
    )

    if response.status_code == 200:
        data = response.json()

        assert isinstance(data, list)

        assert len(data) == 0, (
            "Destructive SQL payload unexpectedly returned records: "
            f"payload={payload!r}"
        )


# ===========================================================================
# SQL INJECTION MUST NOT BREAK NORMAL FUNCTIONALITY
# ===========================================================================


def test_normal_job_search_still_works_after_sql_injection_attempts(
    client,
    override_auth,
    authenticated_user,
):
    """
    Security regression must not break normal search behavior.

    This test sends malicious requests first and then makes a normal
    request. A secure implementation should continue working normally.
    """

    override_auth(authenticated_user)

    for payload in SQL_INJECTION_PAYLOADS:
        response = client.get(
            "/jobs/",
            params={"search": payload},
        )

        assert response.status_code != 500

    # Normal, harmless search value.
    response = client.get(
        "/jobs/",
        params={"search": "zzzz-no-sql-regression-match-12345"},
    )

    assert response.status_code == 200

    data = response.json()

    assert isinstance(data, list)

    # This deliberately unique value should not match seeded jobs.
    assert data == []


# ===========================================================================
# SQL WILDCARD + INJECTION COMBINATION
# ===========================================================================


@pytest.mark.parametrize(
    "payload",
    [
        "%' OR '1'='1",
        "%%' OR 1=1 --",
        "_' OR '1'='1",
        "%admin%' OR 1=1 --",
        "%%' UNION SELECT NULL --",
    ],
)
def test_jobs_like_wildcard_injection_does_not_bypass_filter(
    client,
    override_auth,
    authenticated_user,
    payload,
):
    """
    Exercise payloads containing SQL LIKE wildcards together with
    injection syntax.

    This catches implementations that correctly parameterize values
    but accidentally construct LIKE expressions unsafely.
    """

    override_auth(authenticated_user)

    response = client.get(
        "/jobs/",
        params={"search": payload},
    )

    data = assert_safe_collection_response(response)

    if data is not None:
        assert len(data) == 0, (
            "LIKE/injection payload unexpectedly returned records: "
            f"payload={payload!r}"
        )


# ===========================================================================
# AUTH RESPONSE MUST NOT LEAK DATABASE DETAILS
# ===========================================================================


@pytest.mark.parametrize(
    "payload",
    AUTH_SQL_INJECTION_PAYLOADS,
)
def test_login_sql_injection_does_not_leak_sql_errors(
    client,
    payload,
):
    """
    SQL errors must never be exposed to an attacker.

    Even if a malformed payload reaches validation or database handling,
    the response must not expose SQL syntax, table names, or database
    implementation details.
    """

    response = client.post(
        "/auth/login",
        json={
            "email": payload,
            "password": "NotARealPassword123!",
        },
    )

    assert response.status_code != 500

    body = response.text.lower()

    forbidden_error_fragments = [
        "sql syntax",
        "syntax error",
        "postgresql",
        "psycopg",
        "sqlite",
        "sqlalchemy",
        "select * from",
        "drop table",
        "delete from",
        "update users",
    ]

    for fragment in forbidden_error_fragments:
        assert fragment not in body, (
            f"Database implementation detail leaked in response: "
            f"{fragment!r}; response={response.text!r}"
        )