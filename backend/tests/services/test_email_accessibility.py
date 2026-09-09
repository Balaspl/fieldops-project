from app.services.email.email_template_renderer import (
    EmailTemplateRenderer,
)


def test_email_base_template_has_accessibility_landmarks():
    renderer = EmailTemplateRenderer()

    result = renderer.render_base()

    assert '<html lang="en">' in result
    assert 'role="banner"' in result
    assert "<main>" in result
    assert 'role="contentinfo"' in result


def test_email_base_template_uses_presentational_layout_tables():
    renderer = EmailTemplateRenderer()

    result = renderer.render_base()

    assert result.count('role="presentation"') >= 2


def test_email_logo_is_marked_decorative():
    renderer = EmailTemplateRenderer()

    result = renderer.render_base(
        {
            "logo_url": "https://example.com/logo.png",
        }
    )

    assert 'src="https://example.com/logo.png"' in result
    assert 'alt=""' in result
    assert 'aria-hidden="true"' in result


def test_email_cta_has_accessible_label():
    renderer = EmailTemplateRenderer()

    result = renderer.render_base(
        {
            "cta_url": "https://example.com/job/123",
            "cta_text": "View Job",
        }
    )

    assert 'href="https://example.com/job/123"' in result
    assert 'aria-label="View Job"' in result


def test_email_footer_links_have_accessible_labels():
    renderer = EmailTemplateRenderer()

    result = renderer.render_base(
        {
            "support_email": "support@example.com",
            "unsubscribe_url": "https://example.com/unsubscribe",
        }
    )

    assert 'aria-label="Contact FieldOps support"' in result
    assert 'aria-label="Unsubscribe from FieldOps emails"' in result