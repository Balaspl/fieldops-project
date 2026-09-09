from app.services.email.email_preview import (
    EmailPreview,
    EmailPreviewService,
)


def test_email_preview_service_returns_html_and_text():
    service = EmailPreviewService()

    preview = service.preview(
        "email/transactional.html",
        email_title="Job Confirmation",
        email_heading="Your job is confirmed",
        email_body="Your FieldOps job has been confirmed.",
    )

    assert isinstance(preview, EmailPreview)
    assert preview.template_name == "email/transactional.html"

    assert preview.html
    assert "FieldOps" in preview.html
    assert "Your job is confirmed" in preview.html
    assert "Your FieldOps job has been confirmed." in preview.html

    assert preview.text
    assert "FieldOps" in preview.text
    assert "Your FieldOps job has been confirmed." in preview.text


def test_email_preview_service_uses_injected_renderer():
    class FakeRenderer:
        def render(self, template_name, **context):
            from app.services.email.template_renderer import (
                RenderedEmail,
            )

            assert template_name == "transactional.html"
            assert context["email_title"] == "Test Email"

            return RenderedEmail(
                html="<html><body>Test</body></html>",
                text="Test",
            )

    service = EmailPreviewService(renderer=FakeRenderer())

    preview = service.preview(
        "transactional.html",
        email_title="Test Email",
    )

    assert preview.template_name == "transactional.html"
    assert preview.html == "<html><body>Test</body></html>"
    assert preview.text == "Test"