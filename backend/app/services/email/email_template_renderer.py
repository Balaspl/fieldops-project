"""
Reusable renderer for FieldOps transactional email templates.

This service is responsible for loading application-owned Jinja email
templates and rendering them with the supplied context.

It does not:
- generate AI content
- send email
- perform CSS inlining
- generate plain-text output

Those responsibilities remain with the existing services.
"""

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined


class EmailTemplateRenderer:
    """Render reusable FieldOps email templates."""

    def __init__(self, template_dir: str | Path | None = None) -> None:
        if template_dir is None:
            template_dir = (
                Path(__file__).resolve().parents[2] / "templates" / "email"
            )

        self.template_dir = Path(template_dir)

        if not self.template_dir.is_dir():
            raise FileNotFoundError(
                f"Email template directory not found: {self.template_dir}"
            )

        self.environment = Environment(
            loader=FileSystemLoader(str(self.template_dir)),
            undefined=StrictUndefined,
            autoescape=True,
        )

    def render(
        self,
        template_name: str,
        context: dict[str, Any] | None = None,
    ) -> str:
        """
        Render an HTML email template.

        Args:
            template_name: Template filename, for example
                ``job_confirmation.html``.
            context: Variables available to the template.

        Returns:
            Rendered HTML string.
        """
        if not template_name:
            raise ValueError("template_name is required")

        if not template_name.endswith(".html"):
            raise ValueError("Email template must be an HTML template")

        template = self.environment.get_template(template_name)

        render_context = {
            "preview_text": None,
            "logo_url": None,
            "cta_url": None,
            "cta_text": None,
            "support_email": None,
            "unsubscribe_url": None,
        }

        render_context.update(context or {})

        return template.render(**render_context)

    def render_base(
        self,
        context: dict[str, Any] | None = None,
    ) -> str:
        """Render the reusable FieldOps base email template."""
        return self.render("base.html", context)