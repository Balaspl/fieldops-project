from app.services.email.email_template_renderer import (
    EmailTemplateRenderer,
)


def render_email() -> str:
    renderer = EmailTemplateRenderer()

    return renderer.render(
        "transactional.html",
        {
            "email_title": "Job Confirmation",
            "email_heading": "Your job is confirmed",
            "email_body": "Your technician appointment has been confirmed.",
            "cta_url": "https://example.com/jobs/123",
            "cta_text": "View Job",
            "support_email": "support@example.com",
            "unsubscribe_url": "https://example.com/unsubscribe",
        },
    )


def test_email_uses_table_based_layout():
    html = render_email()

    assert '<table' in html.lower()
    assert 'role="presentation"' in html


def test_email_contains_responsive_styles():
    html = render_email()

    assert "@media only screen and (max-width: 600px)" in html
    assert ".email-wrapper" in html
    assert ".email-content" in html
    assert ".cta-button" in html


def test_email_contains_dark_mode_support():
    html = render_email()

    assert '<meta name="color-scheme" content="light dark">' in html
    assert (
        '<meta name="supported-color-schemes" content="light dark">'
        in html
    )
    assert "@media (prefers-color-scheme: dark)" in html


def test_email_contains_outlook_compatible_mso_properties():
    html = render_email()

    assert "mso-hide: all" in html


def test_email_css_is_processed_by_premailer():
    html = render_email()

    assert "<style>" in html or 'style="' in html
    assert ".email-container" in html
    assert ".email-content" in html
    assert ".cta-button" in html


def test_email_contains_valid_cta_link():
    html = render_email()

    assert 'href="https://example.com/jobs/123"' in html
    assert "View Job" in html


def test_email_contains_support_and_unsubscribe_links():
    html = render_email()

    assert 'mailto:support@example.com' in html
    assert "Contact support" in html
    assert 'href="https://example.com/unsubscribe"' in html
    assert "Unsubscribe" in html


def test_email_contains_accessible_image_handling():
    renderer = EmailTemplateRenderer()

    html = renderer.render(
        "transactional.html",
        {
            "logo_url": "https://example.com/logo.png",
            "email_title": "Job Confirmation",
            "email_heading": "Your job is confirmed",
            "email_body": "Your technician appointment has been confirmed.",
        },
    )

    assert 'src="https://example.com/logo.png"' in html
    assert 'alt=""' in html
    assert 'aria-hidden="true"' in html