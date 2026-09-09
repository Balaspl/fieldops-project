from dataclasses import dataclass
from pathlib import Path
from typing import Any

import html2text
from jinja2 import Environment, FileSystemLoader, select_autoescape
from premailer import transform


TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "templates"


@dataclass
class RenderedEmail:
    html: str
    text: str


class EmailTemplateRenderer:
    """
    Render FieldOps email templates into HTML and plain-text formats.

    HTML is processed with Premailer so CSS from <style> blocks is
    converted into inline CSS for better email-client compatibility.
    """

    def __init__(
        self,
        template_dir: Path | list[Path] | None = None,
    ):
        self.template_dir = template_dir or TEMPLATE_DIR

        if isinstance(self.template_dir, list):
            search_paths = list(self.template_dir)
        else:
            search_paths = [self.template_dir]

        email_template_dirs = [
            path / "email"
            for path in search_paths
            if path.is_dir() and (path / "email").is_dir()
        ]

        for email_template_dir in email_template_dirs:
            if email_template_dir not in search_paths:
                search_paths.append(email_template_dir)

        self.environment = Environment(
            loader=FileSystemLoader(search_paths),
            autoescape=select_autoescape(
                enabled_extensions=("html", "xml"),
                default=True,
            ),
        )

    def render(
        self,
        template_name: str,
        **context: Any,
    ) -> RenderedEmail:
        """
        Render an HTML email template and generate its plain-text version.

        Example:
            renderer = EmailTemplateRenderer()

            email = renderer.render(
                "email/base.html",
                heading="Job Confirmed",
                body="Your job has been confirmed.",
            )

            print(email.html)
            print(email.text)
        """

        html_template = self.environment.get_template(template_name)

        html = html_template.render(**context)

        inlined_html = transform(
            html,
            remove_classes=False,
            strip_important=False,
        )

        text = self._html_to_text(inlined_html)

        return RenderedEmail(
            html=inlined_html,
            text=text,
        )

    @staticmethod
    def _html_to_text(html: str) -> str:
        """
        Convert rendered HTML into a readable plain-text email.
        """

        converter = html2text.HTML2Text()
        converter.ignore_links = False
        converter.ignore_images = True
        converter.body_width = 0
        converter.unicode_snob = True

        text = converter.handle(html)

        return text.strip()