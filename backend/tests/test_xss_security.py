"""
XSS security tests for the FieldOps prompt/template rendering layer.

Security goals:
- User-controlled HTML is rendered as data, not executable HTML.
- Event-handler payloads are escaped.
- Dangerous URL schemes are rejected by safe_url.
- Legitimate URLs remain usable.
- Stored/reflected payloads remain escaped.
- Legitimate HTML formatting remains usable.
- Text-mode rendering remains unchanged.
- Unsafe Jinja expressions remain blocked.
"""

import pytest

from app.services.ai.FieldOpsAI.services.prompt_variable_injector import (
    PromptVariableInjector,
    PromptVariableInjectionError,
)


@pytest.fixture
def injector():
    """Return a fresh injector for each test."""
    PromptVariableInjector._clear_cache()
    return PromptVariableInjector()


# ============================================================================
# Basic HTML escaping
# ============================================================================


def test_html_escapes_script_tag(injector):
    payload = "<script>alert(1)</script>"

    result = injector.render(
        body="<p>{{ customer.note }}</p>",
        variables=["customer.note"],
        context={
            "customer": {
                "note": payload,
            }
        },
        html=True,
    )

    rendered = result.rendered_body

    assert "<script>" not in rendered.lower()
    assert "</script>" not in rendered.lower()
    assert "&lt;script&gt;" in rendered.lower()
    assert "alert(1)" in rendered


def test_html_escapes_script_tag_with_attributes(injector):
    payload = '<script src="https://attacker.example/x.js"></script>'

    result = injector.render(
        body="<div>{{ customer.note }}</div>",
        variables=["customer.note"],
        context={
            "customer": {
                "note": payload,
            }
        },
        html=True,
    )

    rendered = result.rendered_body.lower()

    assert "<script" not in rendered
    assert "</script>" not in rendered
    assert "&lt;script" in rendered


# ============================================================================
# Event-handler payloads
# ============================================================================


def test_html_escapes_img_onerror_payload(injector):
    payload = '<img src="x" onerror="alert(1)">'

    result = injector.render(
        body="<div>{{ customer.note }}</div>",
        variables=["customer.note"],
        context={
            "customer": {
                "note": payload,
            }
        },
        html=True,
    )

    rendered = result.rendered_body.lower()

    # No real <img> element must exist.
    assert "<img" not in rendered

    # The original payload should be visible only as escaped text.
    assert "&lt;img" in rendered
    assert "&gt;" in rendered
    assert "onerror=" in rendered
    assert "alert(1)" in rendered


def test_html_escapes_svg_onload_payload(injector):
    payload = '<svg onload="alert(1)"></svg>'

    result = injector.render(
        body="<div>{{ customer.note }}</div>",
        variables=["customer.note"],
        context={
            "customer": {
                "note": payload,
            }
        },
        html=True,
    )

    rendered = result.rendered_body.lower()

    assert "<svg" not in rendered
    assert "&lt;svg" in rendered
    assert "&gt;" in rendered
    assert "onload=" in rendered
    assert "alert(1)" in rendered


def test_html_escapes_body_onload_payload(injector):
    payload = '<body onload="alert(1)">malicious</body>'

    result = injector.render(
        body="<section>{{ customer.note }}</section>",
        variables=["customer.note"],
        context={
            "customer": {
                "note": payload,
            }
        },
        html=True,
    )

    rendered = result.rendered_body.lower()

    assert "<body" not in rendered
    assert "</body>" not in rendered
    assert "&lt;body" in rendered
    assert "&lt;/body&gt;" in rendered
    assert "onload=" in rendered


# ============================================================================
# Attribute injection
# ============================================================================


def test_html_escapes_attribute_breakout_payload(injector):
    payload = '" onmouseover="alert(1)" x="'

    result = injector.render(
        body='<div data-note="{{ customer.note }}">Customer</div>',
        variables=["customer.note"],
        context={
            "customer": {
                "note": payload,
            }
        },
        html=True,
    )

    rendered = result.rendered_body

    assert 'onmouseover="alert(1)"' not in rendered

    assert (
        "&quot;" in rendered
        or "&#34;" in rendered
        or "&#x22;" in rendered.lower()
    )


def test_html_escapes_single_quote_attribute_payload(injector):
    payload = "' onfocus='alert(1)' x='"

    result = injector.render(
        body="<div data-note='{{ customer.note }}'>Customer</div>",
        variables=["customer.note"],
        context={
            "customer": {
                "note": payload,
            }
        },
        html=True,
    )

    rendered = result.rendered_body

    assert "onfocus='alert(1)'" not in rendered

    assert (
        "&#39;" in rendered
        or "&#x27;" in rendered.lower()
    )


# ============================================================================
# URL-based XSS
# ============================================================================


@pytest.mark.parametrize(
    "payload",
    [
        "javascript:alert(1)",
        "JAVASCRIPT:alert(1)",
        "javaScript:alert(1)",
        "javascript:prompt(1)",
        "javascript:void(0)",
        "vbscript:msgbox(1)",
        "data:text/html,<script>alert(1)</script>",
        "data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==",
    ],
)
def test_safe_url_rejects_dangerous_schemes(injector, payload):
    result = injector.render(
        body='<a href="{{ url | safe_url }}">Open</a>',
        variables=["url"],
        context={
            "url": payload,
        },
        html=True,
    )

    rendered = result.rendered_body.lower()

    assert "javascript:" not in rendered
    assert "vbscript:" not in rendered
    assert "data:text/html" not in rendered
    assert 'href="#"' in rendered


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "http://example.com",
        "https://example.com/jobs/123",
        "https://example.com/path?q=test",
        "mailto:user@example.com",
        "/jobs/123",
        "./jobs/123",
        "../jobs/123",
    ],
)
def test_safe_url_allows_legitimate_urls(injector, url):
    result = injector.render(
        body='<a href="{{ url | safe_url }}">Open</a>',
        variables=["url"],
        context={
            "url": url,
        },
        html=True,
    )

    assert f'href="{url}"' in result.rendered_body


# ============================================================================
# Stored XSS
# ============================================================================


def test_stored_customer_note_is_escaped(injector):
    stored_note = (
        '<script>alert("stored-xss")</script>'
        '<img src=x onerror="alert(1)">'
    )

    result = injector.render(
        body="""
        <html>
            <body>
                <h2>Customer Note</h2>
                <div>{{ customer.note }}</div>
            </body>
        </html>
        """,
        variables=["customer.note"],
        context={
            "customer": {
                "note": stored_note,
            }
        },
        html=True,
    )

    rendered = result.rendered_body.lower()

    assert "<script" not in rendered
    assert "</script>" not in rendered
    assert "<img" not in rendered

    assert "&lt;script" in rendered
    assert "&lt;img" in rendered

    # Handler text can remain because it is inside escaped markup.
    assert "onerror=" in rendered


def test_stored_job_note_is_escaped(injector):
    stored_note = '<svg onload="alert(1)">Job details</svg>'

    result = injector.render(
        body="<p>Job note: {{ job.note }}</p>",
        variables=["job.note"],
        context={
            "job": {
                "note": stored_note,
            }
        },
        html=True,
    )

    rendered = result.rendered_body.lower()

    assert "<svg" not in rendered
    assert "</svg>" not in rendered
    assert "&lt;svg" in rendered
    assert "&lt;/svg&gt;" in rendered
    assert "onload=" in rendered


# ============================================================================
# Reflected XSS
# ============================================================================


def test_reflected_input_is_escaped(injector):
    reflected_value = '<script>alert("reflected-xss")</script>'

    result = injector.render(
        body="<p>Search results for: {{ query }}</p>",
        variables=["query"],
        context={
            "query": reflected_value,
        },
        html=True,
    )

    rendered = result.rendered_body.lower()

    assert "<script" not in rendered
    assert "</script>" not in rendered
    assert "&lt;script" in rendered
    assert "reflected-xss" in rendered


# ============================================================================
# HTML email
# ============================================================================


def test_html_email_field_is_escaped(injector):
    malicious_message = (
        '<script>alert("email-xss")</script>'
        '<img src=x onerror="alert(1)">'
    )

    result = injector.render(
        body="""
        <html>
            <body>
                <h1>Notification</h1>
                <p>{{ message }}</p>
            </body>
        </html>
        """,
        variables=["message"],
        context={
            "message": malicious_message,
        },
        html=True,
    )

    rendered = result.rendered_body.lower()

    assert "<script" not in rendered
    assert "</script>" not in rendered
    assert "<img" not in rendered

    assert "&lt;script" in rendered
    assert "&lt;img" in rendered
    assert "onerror=" in rendered


# ============================================================================
# Text mode
# ============================================================================


def test_text_template_does_not_interpret_html_as_markup(injector):
    payload = "<script>alert(1)</script>"

    result = injector.render(
        body="Customer note: {{ customer.note }}",
        variables=["customer.note"],
        context={
            "customer": {
                "note": payload,
            }
        },
        html=False,
    )

    assert result.rendered_body == (
        "Customer note: <script>alert(1)</script>"
    )


def test_text_template_preserves_legitimate_message_content(injector):
    result = injector.render(
        body="Hello {{ customer.name }}, your job is {{ job.id }}.",
        variables=[
            "customer.name",
            "job.id",
        ],
        context={
            "customer": {
                "name": "Dharsan",
            },
            "job": {
                "id": "JOB-123",
            },
        },
        html=False,
    )

    assert result.rendered_body == (
        "Hello Dharsan, your job is JOB-123."
    )


# ============================================================================
# Legitimate HTML formatting
# ============================================================================


def test_legitimate_html_formatting_remains_usable(injector):
    result = injector.render(
        body="""
        <div>
            <h1>Job Notification</h1>
            <p>Hello {{ customer.name }}</p>
            <strong>Job #{{ job.id }}</strong>
        </div>
        """,
        variables=[
            "customer.name",
            "job.id",
        ],
        context={
            "customer": {
                "name": "Dharsan",
            },
            "job": {
                "id": "JOB-100",
            },
        },
        html=True,
    )

    rendered = result.rendered_body

    assert "<h1>Job Notification</h1>" in rendered
    assert "<p>Hello Dharsan</p>" in rendered
    assert "<strong>Job #JOB-100</strong>" in rendered


def test_html_template_allows_safe_variable_text(injector):
    result = injector.render(
        body="<p>Hello {{ customer.name }}</p>",
        variables=["customer.name"],
        context={
            "customer": {
                "name": "John",
            }
        },
        html=True,
    )

    assert result.rendered_body == "<p>Hello John</p>"


# ============================================================================
# Multiple payloads
# ============================================================================


def test_multiple_xss_payloads_are_escaped(injector):
    result = injector.render(
        body="""
        <div>
            <p>{{ customer.name }}</p>
            <p>{{ customer.note }}</p>
            <p>{{ job.description }}</p>
        </div>
        """,
        variables=[
            "customer.name",
            "customer.note",
            "job.description",
        ],
        context={
            "customer": {
                "name": '<img src=x onerror="alert(1)">',
                "note": '<svg onload="alert(2)">',
            },
            "job": {
                "description": '<script>alert(3)</script>',
            },
        },
        html=True,
    )

    rendered = result.rendered_body.lower()

    assert "<img" not in rendered
    assert "<svg" not in rendered
    assert "<script" not in rendered

    assert "&lt;img" in rendered
    assert "&lt;svg" in rendered
    assert "&lt;script" in rendered

    # These strings are harmless inside escaped text.
    assert "onerror=" in rendered
    assert "onload=" in rendered


# ============================================================================
# Jinja sandbox security
# ============================================================================


def test_dunder_access_is_rejected(injector):
    with pytest.raises(PromptVariableInjectionError):
        injector.render(
            body="{{ customer.__class__ }}",
            variables=["customer.__class__"],
            context={
                "customer": {
                    "name": "John",
                }
            },
            html=True,
        )


def test_dynamic_getitem_is_rejected(injector):
    with pytest.raises(PromptVariableInjectionError):
        injector.render(
            body="{{ customer[key] }}",
            variables=[
                "customer",
                "key",
            ],
            context={
                "customer": {
                    "name": "John",
                },
                "key": "name",
            },
            html=True,
        )


def test_unsafe_filter_is_rejected(injector):
    with pytest.raises(PromptVariableInjectionError):
        injector.render(
            body="{{ customer.name | random }}",
            variables=["customer.name"],
            context={
                "customer": {
                    "name": "John",
                }
            },
            html=True,
        )


# ============================================================================
# Existing variable path regression
# ============================================================================


def test_static_list_path_still_renders(injector):
    declarations = injector.infer_declarations(
        body="{{ technicians[0].name }}"
    )

    assert declarations == [
        "technicians.0.name",
    ]

    result = injector.render(
        body="{{ technicians[0].name }}",
        variables=declarations,
        context={
            "technicians": [
                {
                    "name": "Bob",
                }
            ]
        },
    )

    assert result.rendered_body == "Bob"


def test_nested_customer_job_context_renders(injector):
    result = injector.render(
        body=(
            "Customer: {{ customer.name }} | "
            "Job: {{ job.id }} | "
            "Status: {{ job.status }}"
        ),
        variables=[
            "customer.name",
            "job.id",
            "job.status",
        ],
        context={
            "customer": {
                "name": "Alice",
            },
            "job": {
                "id": "JOB-42",
                "status": "IN_PROGRESS",
            },
        },
        html=False,
    )

    assert result.rendered_body == (
        "Customer: Alice | Job: JOB-42 | Status: IN_PROGRESS"
    )


# ============================================================================
# HTML special characters
# ============================================================================


def test_html_escapes_special_characters(injector):
    payload = '<tag attr="value"> & test'

    result = injector.render(
        body="<div>{{ value }}</div>",
        variables=["value"],
        context={
            "value": payload,
        },
        html=True,
    )

    rendered = result.rendered_body

    assert "<tag" not in rendered
    assert "&lt;tag" in rendered
    assert "&amp;" in rendered

    assert (
        "&#34;" in rendered
        or "&quot;" in rendered
        or "&#x22;" in rendered.lower()
    )


# ============================================================================
# Mixed-case XSS payloads
# ============================================================================


@pytest.mark.parametrize(
    "payload",
    [
        "<SCRIPT>alert(1)</SCRIPT>",
        "<ScRiPt>alert(1)</ScRiPt>",
        "<IMG SRC=x ONERROR=alert(1)>",
        "<SvG OnLoAd=alert(1)>",
    ],
)
def test_mixed_case_xss_payloads_are_escaped(injector, payload):
    result = injector.render(
        body="<div>{{ value }}</div>",
        variables=["value"],
        context={
            "value": payload,
        },
        html=True,
    )

    rendered = result.rendered_body.lower()

    assert "<script" not in rendered
    assert "<img" not in rendered
    assert "<svg" not in rendered
    assert "&lt;" in rendered


# ============================================================================
# None handling
# ============================================================================


def test_optional_none_value_does_not_produce_html(injector):
    result = injector.render(
        body="<p>{{ customer.note }}</p>",
        variables=[
            {
                "name": "customer.note",
                "required": False,
                "default": "",
            }
        ],
        context={
            "customer": {
                "note": None,
            }
        },
        html=True,
    )

    assert result.rendered_body == "<p></p>"


# ============================================================================
# Legitimate action URL
# ============================================================================


def test_safe_https_url_with_html_template(injector):
    url = "https://example.com/jobs/123/accept?token=abc123"

    result = injector.render(
        body='<a href="{{ action_url | safe_url }}">Accept Job</a>',
        variables=["action_url"],
        context={
            "action_url": url,
        },
        html=True,
    )

    assert (
        f'<a href="{url}">Accept Job</a>'
        in result.rendered_body
    )


def test_javascript_url_is_replaced_with_hash(injector):
    result = injector.render(
        body='<a href="{{ action_url | safe_url }}">Accept</a>',
        variables=["action_url"],
        context={
            "action_url": "javascript:alert(document.domain)",
        },
        html=True,
    )

    assert '<a href="#">Accept</a>' in result.rendered_body
    assert "javascript:" not in result.rendered_body.lower()


# ============================================================================
# Strong escaped-element regression tests
# ============================================================================


def test_escaped_img_payload_is_not_an_actual_img_element(injector):
    payload = '<img src="x" onerror="alert(1)">'

    result = injector.render(
        body="{{ value }}",
        variables=["value"],
        context={
            "value": payload,
        },
        html=True,
    )

    rendered = result.rendered_body

    assert rendered.startswith("&lt;img")
    assert rendered.endswith("&gt;")
    assert "<img" not in rendered


def test_escaped_script_payload_is_not_an_actual_script_element(injector):
    payload = "<script>alert(document.domain)</script>"

    result = injector.render(
        body="{{ value }}",
        variables=["value"],
        context={
            "value": payload,
        },
        html=True,
    )

    rendered = result.rendered_body

    assert rendered.startswith("&lt;script&gt;")
    assert rendered.endswith("&lt;/script&gt;")
    assert "<script" not in rendered.lower()


# ============================================================================
# Multiple HTML contexts
# ============================================================================


def test_payload_is_escaped_in_text_context(injector):
    payload = "<script>alert(1)</script>"

    result = injector.render(
        body="<p>{{ value }}</p>",
        variables=["value"],
        context={
            "value": payload,
        },
        html=True,
    )

    assert "<script" not in result.rendered_body.lower()
    assert "&lt;script" in result.rendered_body.lower()


def test_payload_is_escaped_in_attribute_context(injector):
    payload = '" onmouseover="alert(1)"'

    result = injector.render(
        body='<div title="{{ value }}">Hello</div>',
        variables=["value"],
        context={
            "value": payload,
        },
        html=True,
    )

    rendered = result.rendered_body

    assert 'onmouseover="alert(1)"' not in rendered

    assert (
        "&#34;" in rendered
        or "&quot;" in rendered
        or "&#x22;" in rendered.lower()
    )