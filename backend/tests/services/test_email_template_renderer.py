from pathlib import Path

import pytest

from app.services.email.email_template_renderer import EmailTemplateRenderer


def test_renderer_loads_default_email_template_directory():
    renderer = EmailTemplateRenderer()

    assert renderer.template_dir.is_dir()
    assert (renderer.template_dir / "base.html").is_file()


def test_render_base_template():
    renderer = EmailTemplateRenderer()

    result = renderer.render_base(
        {
            "preview_text": "Your FieldOps notification",
            "cta_url": "https://example.com",
            "cta_text": "View Job",
        }
    )

    assert "<!DOCTYPE html>" in result
    assert "FieldOps" in result
    assert "View Job" in result
    assert "https://example.com" in result


def test_render_base_with_custom_values():
    renderer = EmailTemplateRenderer()

    result = renderer.render_base(
        {
            "logo_url": "https://example.com/logo.png",
            "preview_text": "Job confirmed",
            "cta_url": "https://example.com/job/123",
            "cta_text": "View Job",
            "support_email": "support@example.com",
            "unsubscribe_url": "https://example.com/unsubscribe",
        }
    )

    assert "https://example.com/logo.png" in result
    assert "Job confirmed" in result
    assert "support@example.com" in result
    assert "https://example.com/unsubscribe" in result


def test_renderer_rejects_empty_template_name():
    renderer = EmailTemplateRenderer()

    with pytest.raises(ValueError, match="template_name is required"):
        renderer.render("")


def test_renderer_rejects_non_html_template():
    renderer = EmailTemplateRenderer()

    with pytest.raises(
        ValueError,
        match="Email template must be an HTML template",
    ):
        renderer.render("base.txt")


def test_renderer_rejects_missing_template():
    renderer = EmailTemplateRenderer()

    with pytest.raises(Exception):
        renderer.render("does_not_exist.html")


def test_renderer_uses_custom_template_directory(tmp_path: Path):
    template_dir = tmp_path / "email"
    template_dir.mkdir()

    (template_dir / "custom.html").write_text(
        """
        <html>
            <body>
                <h1>{{ heading }}</h1>
            </body>
        </html>
        """,
        encoding="utf-8",
    )

    renderer = EmailTemplateRenderer(template_dir)

    result = renderer.render(
        "custom.html",
        {"heading": "Custom Email"},
    )

    assert "Custom Email" in result


def test_renderer_escapes_html_values():
    renderer = EmailTemplateRenderer()

    result = renderer.render_base(
        {
            "cta_url": "https://example.com",
            "cta_text": "<script>alert('x')</script>",
        }
    )

    assert "<script>alert('x')</script>" not in result
    assert "&lt;script&gt;" in result

def test_renderer_supports_child_template_inheritance(tmp_path):
    template_dir = tmp_path / "email"
    template_dir.mkdir()

    (template_dir / "base.html").write_text(
        """
        <!DOCTYPE html>
        <html>
        <head>
            <title>{% block title %}FieldOps{% endblock %}</title>
        </head>
        <body>
            <header>
                {% block header %}FieldOps{% endblock %}
            </header>

            <main>
                {% block content %}
                <h1>
                    {% block heading %}FieldOps Notification{% endblock %}
                </h1>

                {% block body %}
                <p>Default body</p>
                {% endblock %}
                {% endblock %}
            </main>
        </body>
        </html>
        """,
        encoding="utf-8",
    )

    (template_dir / "test_child.html").write_text(
        """
        {% extends "base.html" %}

        {% block title %}
        Job Confirmation
        {% endblock %}

        {% block heading %}
        Your Job Is Confirmed
        {% endblock %}

        {% block body %}
        <p>Your service appointment has been confirmed.</p>
        {% endblock %}
        """,
        encoding="utf-8",
    )

    renderer = EmailTemplateRenderer(template_dir)

    result = renderer.render(
        "test_child.html",
        {
            "preview_text": "Your job has been confirmed",
        },
    )

    assert "<!DOCTYPE html>" in result
    assert "Job Confirmation" in result
    assert "Your Job Is Confirmed" in result
    assert "Your service appointment has been confirmed." in result
    assert "FieldOps" in result
    assert "Default body" not in result

def test_renderer_rejects_missing_template_directory(tmp_path):
    missing_dir = tmp_path / "does_not_exist"

    with pytest.raises(
        FileNotFoundError,
        match="Email template directory not found",
    ):
        EmailTemplateRenderer(missing_dir)

def test_render_transactional_template():
    renderer = EmailTemplateRenderer()

    result = renderer.render(
        "transactional.html",
        {
            "email_title": "Job Confirmation",
            "email_heading": "Your job is confirmed",
            "email_body": "Your technician appointment has been confirmed.",
        },
    )

    assert "FieldOps" in result
    assert "Job Confirmation" in result
    assert "Your job is confirmed" in result
    assert "Your technician appointment has been confirmed." in result
    assert "email-header" in result
    assert "email-footer" in result


def test_render_transactional_template_uses_defaults():
    renderer = EmailTemplateRenderer()

    result = renderer.render(
        "transactional.html",
        {
            "email_body": "This is the transactional message.",
        },
    )

    assert "FieldOps Notification" in result
    assert "This is the transactional message." in result


def test_transactional_template_supports_reusable_content_blocks():
    renderer = EmailTemplateRenderer()

    result = renderer.render(
        "transactional.html",
        {
            "email_title": "Job Update",
            "email_heading": "Your job has been updated",
            "email_body": "The technician is on the way.",
            "cta_url": "https://example.com/jobs/123",
            "cta_text": "View Job",
        },
    )

    assert "Your job has been updated" in result
    assert "The technician is on the way." in result
    assert "View Job" in result

    # Base template remains responsible for the shared structure.
    assert "FieldOps" in result
    assert "email-header" in result
    assert "email-footer" in result