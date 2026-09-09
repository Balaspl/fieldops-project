from dataclasses import dataclass
from typing import Any

from app.services.email.template_renderer import (
    EmailTemplateRenderer,
    RenderedEmail,
)


@dataclass
class EmailPreview:
    """
    Preview representation of a rendered FieldOps email.
    """

    template_name: str
    html: str
    text: str


class EmailPreviewService:
    """
    Render email templates with supplied preview data.

    This service does not send emails. It only renders the HTML
    and plain-text versions for development and testing.
    """

    def __init__(
        self,
        renderer: EmailTemplateRenderer | None = None,
    ):
        self.renderer = renderer or EmailTemplateRenderer()

    def preview(
        self,
        template_name: str,
        **context: Any,
    ) -> EmailPreview:
        """
        Render a template and return both HTML and plain-text previews.
        """

        rendered: RenderedEmail = self.renderer.render(
            template_name,
            **context,
        )

        return EmailPreview(
            template_name=template_name,
            html=rendered.html,
            text=rendered.text,
        )