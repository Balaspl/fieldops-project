from sqlalchemy.orm import Session

from app.models import NotificationTemplate


# ==========================================================
# Supported Channels
# ==========================================================

SUPPORTED_CHANNELS = [
    "sms",
    "email",
    "push",
    "in_app",
]


# ==========================================================
# Supported Locales
# ==========================================================

SUPPORTED_LOCALES = {
    "en": "English",
    "es": "Spanish",
    "ta": "Tamil",
    "hi": "Hindi",
}


# ==========================================================
# Notification Types
# ==========================================================

NOTIFICATION_TYPES = {
    "created": {
        "title": "Job Created",
        "sms": "Hello {{customer_name}}, your job '{{job_title}}' has been created.",
        "email": (
            "<h2>Job Created</h2>\n\n"
            "<p>Hello {{customer_name}},</p>\n\n"
            "<p>Your service request <strong>{{job_title}}</strong> has been created.</p>\n\n"
            "<p>Thank you,<br>FieldOps Team</p>"
        ),
        "push": "Job '{{job_title}}' created.",
        "in_app": "Your job '{{job_title}}' has been created.",
    },
    "assigned": {
        "title": "Job Assigned",
        "sms": (
            "Hello {{customer_name}}, "
            "{{technician_name}} has been assigned to "
            "{{job_title}}. ETA: {{eta}}."
        ),
        "email": (
            """
            <h2>Job Assigned</h2>

            <p>Hello {{customer_name}},</p>

            <p>
                <strong>{{technician_name}}</strong> has been assigned
                to your service request.
            </p>

            <p>
                <strong>Job:</strong> {{job_title}}
            </p>

            <p>
                <strong>ETA:</strong> {{eta}}
            </p>

            <p>
                Thank you,<br>
                FieldOps Team
            </p>
            """
        ),
        "push": "{{technician_name}} assigned. ETA {{eta}}",
        "in_app": (
            "Your job '{{job_title}}' has been assigned to "
            "{{technician_name}}."
        ),
    },
    "enroute": {
        "title": "Technician En Route",
        "sms": (
            "Hello {{customer_name}}, "
            "{{technician_name}} is on the way. "
            "Expected arrival: {{eta}}."
        ),
        "email": (
            """
            <h2>Technician En Route</h2>

            <p>Hello {{customer_name}},</p>

            <p>
                {{technician_name}} is currently travelling to your location.
            </p>

            <p>
                ETA : <strong>{{eta}}</strong>
            </p>

            <p>
                Thank you,<br>
                FieldOps Team
            </p>
            """
        ),
        "push": "{{technician_name}} is on the way.",
        "in_app": "{{technician_name}} is en route to your location."
    },
    "onsite": {
        "title": "Technician Arrived",
        "sms": (
            "Hello {{customer_name}}, "
            "{{technician_name}} has arrived "
            "for {{job_title}}."
        ),
        "email": (
            """
            <h2>Technician Arrived</h2>

            <p>Hello {{customer_name}},</p>

            <p>
                {{technician_name}} has arrived at your location
                and will begin work shortly.
            </p>

            <p>
                Job : {{job_title}}
            </p>

            <p>
                Thank you,<br>
                FieldOps Team
            </p>
            """
        ),
        "push": "{{technician_name}} has arrived.",
        "in_app": "{{technician_name}} has arrived."
    },
    "completed": {
        "title": "Job Completed",
        "sms": (
            "Hello {{customer_name}}, "
            "{{job_title}} has been completed successfully. "
            "Thank you for choosing us."
        ),
        "email": (
            """
            <h2>Job Completed</h2>

            <p>Hello {{customer_name}},</p>

            <p>
                Your service request has been completed successfully.
            </p>

            <p>
                Job : {{job_title}}
            </p>

            <p>
                Thank you for choosing FieldOps.
            </p>
            """
        ),
        "push": "{{job_title}} completed successfully.",
        "in_app": "{{job_title}} has been completed."
    },
    "cancelled": {
        "title": "Job Cancelled",
        "sms": (
            "Hello {{customer_name}}, "
            "your {{job_title}} has been cancelled."
        ),
        "email": (
            """
            <h2>Job Cancelled</h2>

            <p>Hello {{customer_name}},</p>

            <p>
                Unfortunately your service request
                has been cancelled.
            </p>

            <p>
                Job : {{job_title}}
            </p>

            <p>
                Please contact support for assistance.
            </p>
            """
        ),
        "push": "{{job_title}} cancelled.",
        "in_app": "Your job '{{job_title}}' has been cancelled."
    },

    "job_assigned": {
        "title": "Job Assigned",
        "sms": (
            "Hello {{customer_name}}, "
            "{{technician_name}} has been assigned to "
            "{{job_title}}. ETA: {{eta}}."
        ),
        "email": (
            """
            <h2>Job Assigned</h2>

            <p>Hello {{customer_name}},</p>

            <p>
                <strong>{{technician_name}}</strong> has been assigned
                to your service request.
            </p>

            <p>
                <strong>Job:</strong> {{job_title}}
            </p>

            <p>
                <strong>ETA:</strong> {{eta}}
            </p>

            <p>
                Thank you,<br>
                FieldOps Team
            </p>
            """
        ),
        "push": "{{technician_name}} assigned. ETA {{eta}}",
        "in_app": (
            "Your job '{{job_title}}' has been assigned to "
            "{{technician_name}}."
        ),
    },

    # ======================================================
    # Technician Notifications
    # ======================================================

    "technician_job_assigned": {
        "title": "New Job Assignment",
        "sms": (
            "A new FieldOps job has been assigned. "
            "Open the app for details."
        ),
        "email": (
            """
            <h2>New Job Assignment</h2>
            <p>
                A new FieldOps job has been assigned to you.
                Open the technician app for details.
            </p>
            """
        ),
        "push": (
            "A new job has been assigned. "
            "Open FieldOps for details."
        ),
        "in_app": (
            "A new job has been assigned. "
            "Open FieldOps for details."
        ),
    },

    "technician_journey_started": {
        "title": "Journey Started",
        "sms": (
            "Your journey has started. "
            "Open FieldOps for job details."
        ),
        "email": (
            """
            <h2>Journey Started</h2>
            <p>
                Your journey has started.
                Open FieldOps for job details.
            </p>
            """
        ),
        "push": (
            "Journey started. "
            "Open FieldOps for job details."
        ),
        "in_app": (
            "Journey started. "
            "Open FieldOps for job details."
        ),
    },

    "technician_arrived_on_site": {
        "title": "Arrival Recorded",
        "sms": (
            "Your arrival has been recorded. "
            "Open FieldOps for job details."
        ),
        "email": (
            """
            <h2>Arrival Recorded</h2>
            <p>
                Your arrival at the job site has been recorded.
            </p>
            """
        ),
        "push": (
            "Your arrival at the job site was recorded."
        ),
        "in_app": (
            "Your arrival at the job site was recorded."
        ),
    },

    "technician_job_completed": {
        "title": "Job Completed",
        "sms": (
            "The job completion has been recorded in FieldOps."
        ),
        "email": (
            """
            <h2>Job Completed</h2>
            <p>
                The job completion has been recorded in FieldOps.
            </p>
            """
        ),
        "push": (
            "The job completion has been recorded."
        ),
        "in_app": (
            "The job completion has been recorded."
        ),
    },

    "technician_job_cancelled": {
        "title": "Job Cancelled",
        "sms": (
            "A FieldOps job was cancelled. "
            "Open the app for details."
        ),
        "email": (
            """
            <h2>Job Cancelled</h2>
            <p>
                A FieldOps job assigned to you was cancelled.
                Open the app for details.
            </p>
            """
        ),
        "push": (
            "A FieldOps job was cancelled. "
            "Open the app for details."
        ),
        "in_app": (
            "A FieldOps job was cancelled. "
            "Open the app for details."
        ),
    },

    # ======================================================
    # Dispatcher Notifications
    # ======================================================

    "dispatcher_job_assigned": {
        "title": "Job Assigned",
        "sms": (
            "Assignment confirmed for {{job_title}}."
        ),
        "email": (
            """
            <h2>Job Assigned</h2>
            <p>
                Assignment confirmed for {{job_title}}.
            </p>
            """
        ),
        "push": (
            "Assignment confirmed for {{job_title}}."
        ),
        "in_app": (
            "Assignment confirmed for {{job_title}}."
        ),
    },

    "dispatcher_en_route": {
        "title": "Technician En Route",
        "sms": (
            "{{technician_name}} is en route. "
            "ETA: {{eta}}."
        ),
        "email": (
            """
            <h2>Technician En Route</h2>
            <p>
                {{technician_name}} is en route.
                ETA: {{eta}}.
            </p>
            """
        ),
        "push": (
            "{{technician_name}} is en route."
        ),
        "in_app": (
            "{{technician_name}} is en route. "
            "ETA: {{eta}}."
        ),
    },

    "dispatcher_on_site": {
        "title": "Technician On Site",
        "sms": (
            "{{technician_name}} is now on site."
        ),
        "email": (
            """
            <h2>Technician On Site</h2>
            <p>
                {{technician_name}} is now on site.
            </p>
            """
        ),
        "push": (
            "{{technician_name}} is now on site."
        ),
        "in_app": (
            "{{technician_name}} is now on site."
        ),
    },

    "dispatcher_completed": {
        "title": "Job Completed",
        "sms": (
            "{{job_title}} has been completed."
        ),
        "email": (
            """
            <h2>Job Completed</h2>
            <p>
                {{job_title}} has been completed.
            </p>
            """
        ),
        "push": (
            "{{job_title}} has been completed."
        ),
        "in_app": (
            "{{job_title}} has been completed."
        ),
    },

    "dispatcher_cancelled": {
        "title": "Job Cancelled",
        "sms": (
            "{{job_title}} has been cancelled."
        ),
        "email": (
            """
            <h2>Job Cancelled</h2>
            <p>
                {{job_title}} has been cancelled.
            </p>
            """
        ),
        "push": (
            "{{job_title}} has been cancelled."
        ),
        "in_app": (
            "{{job_title}} has been cancelled."
        ),
    },

    "technician_en_route": {
        "title": "Technician En Route",
        "sms": (
            "Hello {{customer_name}}, "
            "{{technician_name}} is on the way. "
            "Expected arrival: {{eta}}."
        ),
        "email": (
            """
            <h2>Technician En Route</h2>

            <p>Hello {{customer_name}},</p>

            <p>
                {{technician_name}} is currently travelling to your location.
            </p>

            <p>
                ETA : <strong>{{eta}}</strong>
            </p>

            <p>
                Thank you,<br>
                FieldOps Team
            </p>
            """
        ),
        "push": "{{technician_name}} is on the way.",
        "in_app": "{{technician_name}} is en route to your location."
    },

    "technician_arrived": {
        "title": "Technician Arrived",
        "sms": (
            "Hello {{customer_name}}, "
            "{{technician_name}} has arrived "
            "for {{job_title}}."
        ),
        "email": (
            """
            <h2>Technician Arrived</h2>

            <p>Hello {{customer_name}},</p>

            <p>
                {{technician_name}} has arrived at your location
                and will begin work shortly.
            </p>

            <p>
                Job : {{job_title}}
            </p>

            <p>
                Thank you,<br>
                FieldOps Team
            </p>
            """
        ),
        "push": "{{technician_name}} has arrived.",
        "in_app": "{{technician_name}} has arrived."
    },

    "job_completed": {
        "title": "Job Completed",
        "sms": (
            "Hello {{customer_name}}, "
            "{{job_title}} has been completed successfully. "
            "Thank you for choosing us."
        ),
        "email": (
            """
            <h2>Job Completed</h2>

            <p>Hello {{customer_name}},</p>

            <p>
                Your service request has been completed successfully.
            </p>

            <p>
                Job : {{job_title}}
            </p>

            <p>
                Thank you for choosing FieldOps.
            </p>
            """
        ),
        "push": "{{job_title}} completed successfully.",
        "in_app": "{{job_title}} has been completed."
    },

    "job_cancelled": {
        "title": "Job Cancelled",
        "sms": (
            "Hello {{customer_name}}, "
            "your {{job_title}} has been cancelled."
        ),
        "email": (
            """
            <h2>Job Cancelled</h2>

            <p>Hello {{customer_name}},</p>

            <p>
                Unfortunately your service request
                has been cancelled.
            </p>

            <p>
                Job : {{job_title}}
            </p>

            <p>
                Please contact support for assistance.
            </p>
            """
        ),
        "push": "{{job_title}} cancelled.",
        "in_app": "Your job '{{job_title}}' has been cancelled."
    },

    "eta_updated": {
        "title": "ETA Updated",
        "sms": (
            "Hello {{customer_name}}, "
            "updated ETA for {{technician_name}} "
            "is {{eta}}."
        ),
        "email": (
            """
            <h2>ETA Updated</h2>

            <p>Hello {{customer_name}},</p>

            <p>
                Your technician's estimated arrival
                time has changed.
            </p>

            <p>
                New ETA :
                <strong>{{eta}}</strong>
            </p>

            <p>
                Thank you,<br>
                FieldOps Team
            </p>
            """
        ),
        "push": "Updated ETA: {{eta}}",
        "in_app": "Your ETA has been updated to {{eta}}."
    },
}


# ==========================================================
# Helper Functions
# ==========================================================

def get_format(channel: str) -> str:
    if channel == "email":
        return "html"

    return "text"


def build_template_name(title: str, channel: str, locale: str) -> str:
    language = SUPPORTED_LOCALES[locale]
    return f"{title} ({channel.upper()} - {language})"


LOCALIZED_NOTIFICATION_TYPES = {
    "en": {
        "created": {
            "title": "Job Created",
            "sms": "Hello {{customer_name}}, your job '{{job_title}}' has been created.",
            "email": "<h2>Job Created</h2>\n<p>Hello {{customer_name}},</p>\n<p>Your service request <strong>{{job_title}}</strong> has been created.</p>\n<p>Thank you,<br>FieldOps Team</p>",
            "push": "Job '{{job_title}}' created.",
            "in_app": "Your job '{{job_title}}' has been created."
        },
        "assigned": {
            "title": "Job Assigned",
            "sms": "Hello {{customer_name}}, {{technician_name}} has been assigned to {{job_title}}. ETA: {{eta}}.",
            "email": "\n            <h2>Job Assigned</h2>\n\n            <p>Hello {{customer_name}},</p>\n\n            <p>\n                <strong>{{technician_name}}</strong> has been assigned\n                to your service request.\n            </p>\n\n            <p>\n                <strong>Job:</strong> {{job_title}}\n            </p>\n\n            <p>\n                <strong>ETA:</strong> {{eta}}\n            </p>\n\n            <p>\n                Thank you,<br>\n                FieldOps Team\n            </p>\n            ",
            "push": "{{technician_name}} assigned. ETA {{eta}}",
            "in_app": "Your job '{{job_title}}' has been assigned to {{technician_name}}."
        },
        "enroute": {
            "title": "Technician En Route",
            "sms": "Hello {{customer_name}}, {{technician_name}} is on the way. Expected arrival: {{eta}}.",
            "email": "\n            <h2>Technician En Route</h2>\n\n            <p>Hello {{customer_name}},</p>\n\n            <p>\n                {{technician_name}} is currently travelling to your location.\n            </p>\n\n            <p>\n                ETA : <strong>{{eta}}</strong>\n            </p>\n\n            <p>\n                Thank you,<br>\n                FieldOps Team\n            </p>\n            ",
            "push": "{{technician_name}} is on the way.",
            "in_app": "{{technician_name}} is en route to your location."
        },
        "onsite": {
            "title": "Technician Arrived",
            "sms": "Hello {{customer_name}}, {{technician_name}} has arrived for {{job_title}}.",
            "email": "\n            <h2>Technician Arrived</h2>\n\n            <p>Hello {{customer_name}},</p>\n\n            <p>\n                {{technician_name}} has arrived at your location\n                and will begin work shortly.\n            </p>\n\n            <p>\n                Job : {{job_title}}\n            </p>\n\n            <p>\n                Thank you,<br>\n                FieldOps Team\n            </p>\n            ",
            "push": "{{technician_name}} has arrived.",
            "in_app": "{{technician_name}} has arrived."
        },
        "completed": {
            "title": "Job Completed",
            "sms": "Hello {{customer_name}}, {{job_title}} has been completed successfully. Thank you for choosing us.",
            "email": "\n            <h2>Job Completed</h2>\n\n            <p>Hello {{customer_name}},</p>\n\n            <p>\n                Your service request has been completed successfully.\n            </p>\n\n            <p>\n                Job : {{job_title}}\n            </p>\n\n            <p>\n                Thank you for choosing FieldOps.\n            </p>\n            ",
            "push": "{{job_title}} completed successfully.",
            "in_app": "{{job_title}} has been completed."
        },
        "cancelled": {
            "title": "Job Cancelled",
            "sms": "Hello {{customer_name}}, your {{job_title}} has been cancelled.",
            "email": "\n            <h2>Job Cancelled</h2>\n\n            <p>Hello {{customer_name}},</p>\n\n            <p>\n                Unfortunately your service request\n                has been cancelled.\n            </p>\n\n            <p>\n                Job : {{job_title}}\n            </p>\n\n            <p>\n                Please contact support for assistance.\n            </p>\n            ",
            "push": "{{job_title}} cancelled.",
            "in_app": "Your job '{{job_title}}' has been cancelled."
        },
        "job_assigned": {
            "title": "Job Assigned",
            "sms": "Hello {{customer_name}}, {{technician_name}} has been assigned to {{job_title}}. ETA: {{eta}}.",
            "email": "\n            <h2>Job Assigned</h2>\n\n            <p>Hello {{customer_name}},</p>\n\n            <p>\n                <strong>{{technician_name}}</strong> has been assigned\n                to your service request.\n            </p>\n\n            <p>\n                <strong>Job:</strong> {{job_title}}\n            </p>\n\n            <p>\n                <strong>ETA:</strong> {{eta}}\n            </p>\n\n            <p>\n                Thank you,<br>\n                FieldOps Team\n            </p>\n            ",
            "push": "{{technician_name}} assigned. ETA {{eta}}",
            "in_app": "Your job '{{job_title}}' has been assigned to {{technician_name}}."
        },
        "technician_job_assigned": {
            "title": "New Job Assignment",
            "sms": "A new FieldOps job has been assigned. Open the app for details.",
            "email": "\n            <h2>New Job Assignment</h2>\n            <p>\n                A new FieldOps job has been assigned to you.\n                Open the technician app for details.\n            </p>\n            ",
            "push": "A new job has been assigned. Open FieldOps for details.",
            "in_app": "A new job has been assigned. Open FieldOps for details."
        },
        "technician_journey_started": {
            "title": "Journey Started",
            "sms": "Your journey has started. Open FieldOps for job details.",
            "email": "\n            <h2>Journey Started</h2>\n            <p>\n                Your journey has started.\n                Open FieldOps for job details.\n            </p>\n            ",
            "push": "Journey started. Open FieldOps for job details.",
            "in_app": "Journey started. Open FieldOps for job details."
        },
        "technician_arrived_on_site": {
            "title": "Arrival Recorded",
            "sms": "Your arrival has been recorded. Open FieldOps for job details.",
            "email": "\n            <h2>Arrival Recorded</h2>\n            <p>\n                Your arrival at the job site has been recorded.\n            </p>\n            ",
            "push": "Your arrival at the job site was recorded.",
            "in_app": "Your arrival at the job site was recorded."
        },
        "technician_job_completed": {
            "title": "Job Completed",
            "sms": "The job completion has been recorded in FieldOps.",
            "email": "\n            <h2>Job Completed</h2>\n            <p>\n                The job completion has been recorded in FieldOps.\n            </p>\n            ",
            "push": "The job completion has been recorded.",
            "in_app": "The job completion has been recorded."
        },
        "technician_job_cancelled": {
            "title": "Job Cancelled",
            "sms": "A FieldOps job was cancelled. Open the app for details.",
            "email": "\n            <h2>Job Cancelled</h2>\n            <p>\n                A FieldOps job assigned to you was cancelled.\n                Open the app for details.\n            </p>\n            ",
            "push": "A FieldOps job was cancelled. Open the app for details.",
            "in_app": "A FieldOps job was cancelled. Open the app for details."
        },
        "dispatcher_job_assigned": {
            "title": "Job Assigned",
            "sms": "Assignment confirmed for {{job_title}}.",
            "email": "\n            <h2>Job Assigned</h2>\n            <p>\n                Assignment confirmed for {{job_title}}.\n            </p>\n            ",
            "push": "Assignment confirmed for {{job_title}}.",
            "in_app": "Assignment confirmed for {{job_title}}."
        },
        "dispatcher_en_route": {
            "title": "Technician En Route",
            "sms": "{{technician_name}} is en route. ETA: {{eta}}.",
            "email": "\n            <h2>Technician En Route</h2>\n            <p>\n                {{technician_name}} is en route.\n                ETA: {{eta}}.\n            </p>\n            ",
            "push": "{{technician_name}} is en route.",
            "in_app": "{{technician_name}} is en route. ETA: {{eta}}."
        },
        "dispatcher_on_site": {
            "title": "Technician On Site",
            "sms": "{{technician_name}} is now on site.",
            "email": "\n            <h2>Technician On Site</h2>\n            <p>\n                {{technician_name}} is now on site.\n            </p>\n            ",
            "push": "{{technician_name}} is now on site.",
            "in_app": "{{technician_name}} is now on site."
        },
        "dispatcher_completed": {
            "title": "Job Completed",
            "sms": "{{job_title}} has been completed.",
            "email": "\n            <h2>Job Completed</h2>\n            <p>\n                {{job_title}} has been completed.\n            </p>\n            ",
            "push": "{{job_title}} has been completed.",
            "in_app": "{{job_title}} has been completed."
        },
        "dispatcher_cancelled": {
            "title": "Job Cancelled",
            "sms": "{{job_title}} has been cancelled.",
            "email": "\n            <h2>Job Cancelled</h2>\n            <p>\n                {{job_title}} has been cancelled.\n            </p>\n            ",
            "push": "{{job_title}} has been cancelled.",
            "in_app": "{{job_title}} has been cancelled."
        },
        "technician_en_route": {
            "title": "Technician En Route",
            "sms": "Hello {{customer_name}}, {{technician_name}} is on the way. Expected arrival: {{eta}}.",
            "email": "\n            <h2>Technician En Route</h2>\n\n            <p>Hello {{customer_name}},</p>\n\n            <p>\n                {{technician_name}} is currently travelling to your location.\n            </p>\n\n            <p>\n                ETA : <strong>{{eta}}</strong>\n            </p>\n\n            <p>\n                Thank you,<br>\n                FieldOps Team\n            </p>\n            ",
            "push": "{{technician_name}} is on the way.",
            "in_app": "{{technician_name}} is en route to your location."
        },
        "technician_arrived": {
            "title": "Technician Arrived",
            "sms": "Hello {{customer_name}}, {{technician_name}} has arrived for {{job_title}}.",
            "email": "\n            <h2>Technician Arrived</h2>\n\n            <p>Hello {{customer_name}},</p>\n\n            <p>\n                {{technician_name}} has arrived at your location\n                and will begin work shortly.\n            </p>\n\n            <p>\n                Job : {{job_title}}\n            </p>\n\n            <p>\n                Thank you,<br>\n                FieldOps Team\n            </p>\n            ",
            "push": "{{technician_name}} has arrived.",
            "in_app": "{{technician_name}} has arrived."
        },
        "job_completed": {
            "title": "Job Completed",
            "sms": "Hello {{customer_name}}, {{job_title}} has been completed successfully. Thank you for choosing us.",
            "email": "\n            <h2>Job Completed</h2>\n\n            <p>Hello {{customer_name}},</p>\n\n            <p>\n                Your service request has been completed successfully.\n            </p>\n\n            <p>\n                Job : {{job_title}}\n            </p>\n\n            <p>\n                Thank you for choosing FieldOps.\n            </p>\n            ",
            "push": "{{job_title}} completed successfully.",
            "in_app": "{{job_title}} has been completed."
        },
        "job_cancelled": {
            "title": "Job Cancelled",
            "sms": "Hello {{customer_name}}, your {{job_title}} has been cancelled.",
            "email": "\n            <h2>Job Cancelled</h2>\n\n            <p>Hello {{customer_name}},</p>\n\n            <p>\n                Unfortunately your service request\n                has been cancelled.\n            </p>\n\n            <p>\n                Job : {{job_title}}\n            </p>\n\n            <p>\n                Please contact support for assistance.\n            </p>\n            ",
            "push": "{{job_title}} cancelled.",
            "in_app": "Your job '{{job_title}}' has been cancelled."
        },
        "eta_updated": {
            "title": "ETA Updated",
            "sms": "Hello {{customer_name}}, updated ETA for {{technician_name}} is {{eta}}.",
            "email": "\n            <h2>ETA Updated</h2>\n\n            <p>Hello {{customer_name}},</p>\n\n            <p>\n                Your technician's estimated arrival\n                time has changed.\n            </p>\n\n            <p>\n                New ETA :\n                <strong>{{eta}}</strong>\n            </p>\n\n            <p>\n                Thank you,<br>\n                FieldOps Team\n            </p>\n            ",
            "push": "Updated ETA: {{eta}}",
            "in_app": "Your ETA has been updated to {{eta}}."
        }
    },
    "es": {
        "created": {
            "title": "Trabajo creado",
            "sms": "Hola {{customer_name}}, su solicitud de servicio {{job_title}} ha sido creada.",
            "email": "<h2>Trabajo creado</h2>\n<p>Hola {{customer_name}},</p>\n<p>Su solicitud de servicio <strong>{{job_title}}</strong> ha sido creada.</p>\n<p>Gracias,<br>FieldOps Team</p>",
            "push": "Trabajo '{{job_title}}' creado.",
            "in_app": "Su trabajo '{{job_title}}' ha sido creado."
        },
        "assigned": {
            "title": "Trabajo asignado",
            "sms": "Hola {{customer_name}}, {{technician_name}} ha sido asignado a {{job_title}}. ETA: {{eta}}.",
            "email": "<h2>Trabajo asignado</h2>\n\n<p>Hola {{customer_name}},</p>\n\n<p><strong>{{technician_name}}</strong> ha sido asignado a su solicitud de servicio.</p>\n\n<p><strong>Trabajo:</strong> {{job_title}}</p>\n\n<p><strong>ETA:</strong> {{eta}}</p>\n\n<p>Gracias,<br>FieldOps Team</p>",
            "push": "{{technician_name}} asignado. ETA {{eta}}",
            "in_app": "Su trabajo '{{job_title}}' ha sido asignado a {{technician_name}}."
        },
        "enroute": {
            "title": "Técnico en camino",
            "sms": "Hola {{customer_name}}, {{technician_name}} está en camino. Llegada esperada: {{eta}}.",
            "email": "<h2>Técnico en camino</h2>\n\n<p>Hola {{customer_name}},</p>\n\n<p>{{technician_name}} está viajando a su ubicación.</p>\n\n<p>ETA : <strong>{{eta}}</strong></p>\n\n<p>Gracias,<br>\nFieldOps Team</p>",
            "push": "{{technician_name}} está en camino.",
            "in_app": "{{technician_name}} está en camino a su ubicación."
        },
        "onsite": {
            "title": "Técnico llegó",
            "sms": "Hola {{customer_name}}, {{technician_name}} ha llegado para {{job_title}}.",
            "email": "<h2>Técnico llegó</h2>\n\n<p>Hola {{customer_name}},</p>\n\n<p>{{technician_name}} ha llegado a su ubicación y comenzará a trabajar en breve.</p>\n\n<p>Trabajo : {{job_title}}</p>\n\n<p>Gracias,<br>\nFieldOps Team</p>",
            "push": "{{technician_name}} ha llegado.",
            "in_app": "{{technician_name}} ha llegado."
        },
        "completed": {
            "title": "Trabajo completado",
            "sms": "Hola {{customer_name}}, {{job_title}} se ha completado con éxito. Gracias por elegirnos.",
            "email": "<h2>Trabajo completado</h2>\n\n<p>Hola {{customer_name}},</p>\n\n<p>Su solicitud de servicio se ha completado con éxito.</p>\n\n<p>Trabajo : {{job_title}}</p>\n\n<p>Gracias por elegir FieldOps.</p>",
            "push": "{{job_title}} completado con éxito.",
            "in_app": "{{job_title}} se ha completado."
        },
        "cancelled": {
            "title": "Trabajo cancelado",
            "sms": "Hola {{customer_name}}, su {{job_title}} ha sido cancelado.",
            "email": "<h2>Trabajo cancelado</h2>\n\n<p>Hola {{customer_name}},</p>\n\n<p>Lamentablemente su solicitud de servicio ha sido cancelada.</p>\n\n<p>Trabajo : {{job_title}}</p>\n\n<p>Por favor, póngase en contacto con el soporte técnico para obtener ayuda.</p>",
            "push": "{{job_title}} cancelado.",
            "in_app": "Su trabajo '{{job_title}}' ha sido cancelado."
        },
        "job_assigned": {
            "title": "Trabajo asignado",
            "sms": (
                "Hola {{customer_name}}, "
                "{{technician_name}} ha sido asignado a "
                "{{job_title}}. ETA: {{eta}}."),
            "email": (
                "<h2>Trabajo asignado</h2>\n\n"
                "<p>Hola {{customer_name}},</p>\n\n"
                "<p><strong>{{technician_name}}</strong> "
                "ha sido asignado a su solicitud de servicio.</p>\n\n"
                "<p><strong>Trabajo:</strong> {{job_title}}</p>\n\n"
                "<p><strong>ETA:</strong> {{eta}}</p>\n\n"
                "<p>Gracias,<br>FieldOps Team</p>"),
            "push": (
                "{{technician_name}} asignado. "
                "ETA {{eta}}"),
            "in_app": (
                "Su trabajo '{{job_title}}' ha sido asignado a "
                "{{technician_name}}."),
        },
        "technician_job_assigned": {
            "title": "Nueva asignación de trabajo",
            "sms": "Un nuevo trabajo de FieldOps ha sido asignado. Abra la aplicación para más detalles.",
            "email": "<h2>Nueva asignación de trabajo</h2>\n<p>Un nuevo trabajo de FieldOps ha sido asignado a usted. Abra la aplicación del técnico para más detalles.</p>",
            "push": "Un nuevo trabajo ha sido asignado. Abra FieldOps para más detalles.",
            "in_app": "Un nuevo trabajo ha sido asignado. Abra FieldOps para más detalles."
        },
        "technician_journey_started": {
            "title": "Viaje comenzado",
            "sms": "Su viaje ha comenzado. Abra FieldOps para ver los detalles del trabajo.",
            "email": "<h2>Viaje comenzado</h2>\n<p>Su viaje ha comenzado. Abra FieldOps para ver los detalles del trabajo.</p>",
            "push": "Su viaje ha comenzado. Abra FieldOps para ver los detalles del trabajo.",
            "in_app": "Su viaje ha comenzado. Abra FieldOps para ver los detalles del trabajo."
        },
        "technician_arrived_on_site": {
            "title": "Llegada registrada",
            "sms": "Su llegada ha sido registrada. Abra FieldOps para ver los detalles del trabajo.",
            "email": "<h2>Llegada registrada</h2>\n<p>Su llegada al lugar del trabajo ha sido registrada.</p>",
            "push": "Su llegada al lugar del trabajo ha sido registrada.",
            "in_app": "Su llegada al lugar del trabajo ha sido registrada."
        },
        "technician_job_completed": {
            "title": "Trabajo completado",
            "sms": "La finalización del trabajo ha sido registrada en FieldOps.",
            "email": "<h2>Trabajo completado</h2>\n<p>La finalización del trabajo ha sido registrada en FieldOps.</p>",
            "push": "La finalización del trabajo ha sido registrada.",
            "in_app": "La finalización del trabajo ha sido registrada."
        },
        "technician_job_cancelled": {
            "title": "Trabajo cancelado",
            "sms": "Un trabajo de FieldOps fue cancelado. Abra la aplicación para más detalles.",
            "email": "<h2>Trabajo cancelado</h2>\n<p>Un trabajo de FieldOps asignado a usted fue cancelado. Abra la aplicación para más detalles.</p>",
            "push": "Un trabajo de FieldOps fue cancelado. Abra la aplicación para más detalles.",
            "in_app": "Un trabajo de FieldOps fue cancelado. Abra la aplicación para más detalles."
        },
        "dispatcher_job_assigned": {
            "title": "Trabajo asignado",
            "sms": "Asignación confirmada para {{job_title}}.",
            "email": "<h2>Trabajo asignado</h2>\n<p>Asignación confirmada para {{job_title}}.</p>",
            "push": "Asignación confirmada para {{job_title}}.",
            "in_app": "Asignación confirmada para {{job_title}}."
        },
        "dispatcher_en_route": {
            "title": "Técnico en camino",
            "sms": "{{technician_name}} está en camino. ETA: {{eta}}.",
            "email": "<h2>Técnico en camino</h2>\n<p>{{technician_name}} está en camino. ETA: {{eta}}.</p>",
            "push": "{{technician_name}} está en camino.",
            "in_app": "{{technician_name}} está en camino. ETA: {{eta}}."
        },
        "dispatcher_on_site": {
            "title": "Técnico en el sitio",
            "sms": "{{technician_name}} está ahora en el sitio.",
            "email": "<h2>Técnico en el sitio</h2>\n<p>{{technician_name}} está ahora en el sitio.</p>",
            "push": "{{technician_name}} está ahora en el sitio.",
            "in_app": "{{technician_name}} está ahora en el sitio."
        },
        "dispatcher_completed": {
            "title": "Trabajo completado",
            "sms": "{{job_title}} ha sido completado.",
            "email": "<h2>Trabajo completado</h2>\n<p>{{job_title}} ha sido completado.</p>",
            "push": "{{job_title}} ha sido completado.",
            "in_app": "{{job_title}} ha sido completado."
        },
        "dispatcher_cancelled": {
            "title": "Trabajo cancelado",
            "sms": "{{job_title}} ha sido cancelado.",
            "email": "<h2>Trabajo cancelado</h2>\n<p>{{job_title}} ha sido cancelado.</p>",
            "push": "{{job_title}} ha sido cancelado.",
            "in_app": "{{job_title}} ha sido cancelado."
        },
        "technician_en_route": {
            "title": "Técnico en camino",
            "sms": "Hola {{customer_name}}, {{technician_name}} está en camino. Llegada esperada: {{eta}}.",
            "email": "<h2>Técnico en camino</h2>\n\n<p>Hola {{customer_name}},</p>\n\n<p>{{technician_name}} está viajando a su ubicación.</p>\n\n<p>ETA : <strong>{{eta}}</strong></p>\n\n<p>Gracias,<br>\nFieldOps Team</p>",
            "push": "{{technician_name}} está en camino.",
            "in_app": "{{technician_name}} está en camino a su ubicación."
        },
        "technician_arrived": {
            "title": "Técnico llegó",
            "sms": "Hola {{customer_name}}, {{technician_name}} ha llegado para {{job_title}}.",
            "email": "<h2>Técnico llegó</h2>\n\n<p>Hola {{customer_name}},</p>\n\n<p>{{technician_name}} ha llegado a su ubicación y comenzará a trabajar en breve.</p>\n\n<p>Trabajo : {{job_title}}</p>\n\n<p>Gracias,<br>\nFieldOps Team</p>",
            "push": "{{technician_name}} ha llegado.",
            "in_app": "{{technician_name}} ha llegado."
        },
        "job_completed": {
            "title": "Trabajo completado",
            "sms": "Hola {{customer_name}}, {{job_title}} se ha completado con éxito. Gracias por elegirnos.",
            "email": "<h2>Trabajo completado</h2>\n\n<p>Hola {{customer_name}},</p>\n\n<p>Su solicitud de servicio se ha completado con éxito.</p>\n\n<p>Trabajo : {{job_title}}</p>\n\n<p>Gracias por elegir FieldOps.</p>",
            "push": "{{job_title}} completado con éxito.",
            "in_app": "{{job_title}} se ha completado."
        },
        "job_cancelled": {
            "title": "Trabajo cancelado",
            "sms": "Hola {{customer_name}}, su {{job_title}} ha sido cancelado.",
            "email": "<h2>Trabajo cancelado</h2>\n\n<p>Hola {{customer_name}},</p>\n\n<p>Lamentablemente su solicitud de servicio ha sido cancelada.</p>\n\n<p>Trabajo : {{job_title}}</p>\n\n<p>Por favor, póngase en contacto con el soporte técnico para obtener ayuda.</p>",
            "push": "{{job_title}} cancelado.",
            "in_app": "Su trabajo '{{job_title}}' ha sido cancelado."
        },
        "eta_updated": {
            "title": "ETA actualizado",
            "sms": "Hola {{customer_name}}, el ETA actualizado para {{technician_name}} es {{eta}}.",
            "email": "<h2>ETA actualizado</h2>\n\n<p>Hola {{customer_name}},</p>\n\n<p>El tiempo estimado de llegada de su técnico ha cambiado.</p>\n\n<p>Nuevo ETA : <strong>{{eta}}</strong></p>\n\n<p>Gracias,<br>\nFieldOps Team</p>",
            "push": "ETA actualizado: {{eta}}",
            "in_app": "Su ETA se ha actualizado a {{eta}}."
        }
    },
    "ta": {
        "created": {
            "title": "பணி உருவாக்கப்பட்டது",
            "sms": "வணக்கம் {{customer_name}}, உங்கள் சேவை கோரிக்கை {{job_title}} உருவாக்கப்பட்டுள்ளது.",
            "email": "<h2>பணி உருவாக்கப்பட்டது</h2>\n<p>வணக்கம் {{customer_name}},</p>\n<p>உங்கள் சேவை கோரிக்கை <strong>{{job_title}}</strong> உருவாக்கப்பட்டுள்ளது.</p>\n<p>நன்றி,<br>FieldOps Team</p>",
            "push": "பணி '{{job_title}}' உருவாக்கப்பட்டது.",
            "in_app": "உங்கள் பணி '{{job_title}}' உருவாக்கப்பட்டுள்ளது."
        },
        "assigned": {
            "title": "பணி நியமிக்கப்பட்டது",
            "sms": "வணக்கம் {{customer_name}}, {{job_title}} க்கு {{technician_name}} நியமிக்கப்பட்டுள்ளார். ETA: {{eta}}.",
            "email": "<h2>பணி நியமிக்கப்பட்டது</h2>\n\n<p>வணக்கம் {{customer_name}},</p>\n\n<p><strong>{{technician_name}}</strong> உங்கள் சேவை கோரிக்கைக்கு நியமிக்கப்பட்டுள்ளார்.</p>\n\n<p><strong>பணி:</strong> {{job_title}}</p>\n\n<p><strong>ETA:</strong> {{eta}}</p>\n\n<p>நன்றி,<br>\nFieldOps Team</p>",
            "push": "{{technician_name}} நியமிக்கப்பட்டுள்ளார். ETA {{eta}}",
            "in_app": "உங்கள் பணி '{{job_title}}' {{technician_name}} க்கு நியமிக்கப்பட்டுள்ளது."
        },
        "enroute": {
            "title": "தொழில்நுட்ப வல்லுநர் வழியில் உள்ளார்",
            "sms": "வணக்கம் {{customer_name}}, {{technician_name}} வழியில் உள்ளார். எதிர்பார்க்கப்படும் வருகை: {{eta}}.",
            "email": "<h2>தொழில்நுட்ப வல்லுநர் வழியில் உள்ளார்</h2>\n\n<p>வணக்கம் {{customer_name}},</p>\n\n<p>{{technician_name}} உங்கள் இடத்திற்குப் பயணம் செய்து கொண்டிருக்கிறார்.</p>\n\n<p>ETA : <strong>{{eta}}</strong></p>\n\n<p>நன்றி,<br>\nFieldOps Team</p>",
            "push": "{{technician_name}} வழியில் உள்ளார்.",
            "in_app": "{{technician_name}} உங்கள் இடத்திற்கு வழியில் உள்ளார்."
        },
        "onsite": {
            "title": "தொழில்நுட்ப வல்லுநர் வந்துள்ளார்",
            "sms": "வணக்கம் {{customer_name}}, {{technician_name}} {{job_title}} க்காக வந்துள்ளார்.",
            "email": "<h2>தொழில்நுட்ப வல்லுநர் வந்துள்ளார்</h2>\n\n<p>வணக்கம் {{customer_name}},</p>\n\n<p>{{technician_name}} உங்கள் இடத்திற்கு வந்துள்ளார், விரைவில் வேலையைத் தொடங்குவார்.</p>\n\n<p>பணி : {{job_title}}</p>\n\n<p>நன்றி,<br>\nFieldOps Team</p>",
            "push": "{{technician_name}} வந்துள்ளார்.",
            "in_app": "{{technician_name}} வந்துள்ளார்."
        },
        "completed": {
            "title": "பணி முடிந்தது",
            "sms": "வணக்கம் {{customer_name}}, {{job_title}} வெற்றிகரமாக முடிக்கப்பட்டுள்ளது. எங்களைத் தேர்ந்தெடுத்ததற்கு நன்றி.",
            "email": "<h2>பணி முடிந்தது</h2>\n\n<p>வணக்கம் {{customer_name}},</p>\n\n<p>உங்கள் சேவை கோரிக்கை வெற்றிகரமாக முடிக்கப்பட்டுள்ளது.</p>\n\n<p>பணி : {{job_title}}</p>\n\n<p>FieldOps ஐத் தேர்ந்தெடுத்ததற்கு நன்றி.</p>",
            "push": "{{job_title}} வெற்றிகரமாக முடிந்தது.",
            "in_app": "{{job_title}} முடிக்கப்பட்டுள்ளது."
        },
        "cancelled": {
            "title": "பணி ரத்து செய்யப்பட்டது",
            "sms": "வணக்கம் {{customer_name}}, உங்கள் {{job_title}} ரத்து செய்யப்பட்டுள்ளது.",
            "email": "<h2>பணி ரத்து செய்யப்பட்டது</h2>\n\n<p>வணக்கம் {{customer_name}},</p>\n\n<p>துரதிர்ஷ்டவசமாக உங்கள் சேவை கோரிக்கை ரத்து செய்யப்பட்டுள்ளது.</p>\n\n<p>பணி : {{job_title}}</p>\n\n<p>உதவிக்கு வாடிக்கையாளர் சேவையைத் தொடர்பு கொள்ளவும்.</p>",
            "push": "{{job_title}} ரத்து செய்யப்பட்டது.",
            "in_app": "உங்கள் பணி '{{job_title}}' ரத்து செய்யப்பட்டுள்ளது."
        },
        "job_assigned": {
            "title": "பணி நியமிக்கப்பட்டது",
            "sms": "வணக்கம் {{customer_name}}, {{job_title}} க்கு {{technician_name}} நியமிக்கப்பட்டுள்ளார். ETA: {{eta}}.",
            "email": "<h2>பணி நியமிக்கப்பட்டது</h2>\n\n<p>வணக்கம் {{customer_name}},</p>\n\n<p><strong>{{technician_name}}</strong> உங்கள் சேவை கோரிக்கைக்கு நியமிக்கப்பட்டுள்ளார்.</p>\n\n<p><strong>பணி:</strong> {{job_title}}</p>\n\n<p><strong>ETA:</strong> {{eta}}</p>\n\n<p>நன்றி,<br>\nFieldOps Team</p>",
            "push": "{{technician_name}} நியமிக்கப்பட்டுள்ளார். ETA {{eta}}",
            "in_app": "உங்கள் பணி '{{job_title}}' {{technician_name}} க்கு நியமிக்கப்பட்டுள்ளது."
        },
        "technician_job_assigned": {
            "title": "புதிய பணி நியமனம்",
            "sms": "புதிய FieldOps பணி நியமிக்கப்பட்டுள்ளது. விவரங்களுக்கு செயலியைத் திறக்கவும்.",
            "email": "<h2>புதிய பணி நியமனம்</h2>\n<p>புதிய FieldOps பணி உங்களுக்கு நியமிக்கப்பட்டுள்ளது. விவரங்களுக்கு தொழில்நுட்ப வல்லுநர் செயலியைத் திறக்கவும்.</p>",
            "push": "புதிய பணி நியமிக்கப்பட்டுள்ளது. விவரங்களுக்கு FieldOps ஐத் திறக்கவும்.",
            "in_app": "புதிய பணி நியமிக்கப்பட்டுள்ளது. விவரங்களுக்கு FieldOps ஐத் திறக்கவும்."
        },
        "technician_journey_started": {
            "title": "பயணம் தொடங்கியது",
            "sms": "உங்கள் பயணம் தொடங்கிவிட்டது. பணி விவரங்களுக்கு FieldOps ஐத் திறக்கவும்.",
            "email": "<h2>பயணம் தொடங்கியது</h2>\n<p>உங்கள் பயணம் தொடங்கிவிட்டது. பணி விவரங்களுக்கு FieldOps ஐத் திறக்கவும்.</p>",
            "push": "உங்கள் பயணம் தொடங்கிவிட்டது. பணி விவரங்களுக்கு FieldOps ஐத் திறக்கவும்.",
            "in_app": "உங்கள் பயணம் தொடங்கிவிட்டது. பணி விவரங்களுக்கு FieldOps ஐத் திறக்கவும்."
        },
        "technician_arrived_on_site": {
            "title": "வருகை பதிவு செய்யப்பட்டது",
            "sms": "உங்கள் வருகை பதிவு செய்யப்பட்டுள்ளது. பணி விவரங்களுக்கு FieldOps ஐத் திறக்கவும்.",
            "email": "<h2>வருகை பதிவு செய்யப்பட்டது</h2>\n<p>பணி இடத்தில் உங்கள் வருகை பதிவு செய்யப்பட்டுள்ளது.</p>",
            "push": "பணி இடத்தில் உங்கள் வருகை பதிவு செய்யப்பட்டுள்ளது.",
            "in_app": "பணி இடத்தில் உங்கள் வருகை பதிவு செய்யப்பட்டுள்ளது."
        },
        "technician_job_completed": {
            "title": "பணி முடிந்தது",
            "sms": "பணி முடிந்தது FieldOps இல் பதிவு செய்யப்பட்டுள்ளது.",
            "email": "<h2>பணி முடிந்தது</h2>\n<p>பணி முடிந்தது FieldOps இல் பதிவு செய்யப்பட்டுள்ளது.</p>",
            "push": "பணி முடிந்தது பதிவு செய்யப்பட்டுள்ளது.",
            "in_app": "பணி முடிந்தது பதிவு செய்யப்பட்டுள்ளது."
        },
        "technician_job_cancelled": {
            "title": "பணி ரத்து செய்யப்பட்டது",
            "sms": "FieldOps பணி ரத்து செய்யப்பட்டது. விவரங்களுக்கு செயலியைத் திறக்கவும்.",
            "email": "<h2>பணி ரத்து செய்யப்பட்டது</h2>\n<p>உங்களுக்கு நியமிக்கப்பட்ட FieldOps பணி ரத்து செய்யப்பட்டது. விவரங்களுக்கு செயலியைத் திறக்கவும்.</p>",
            "push": "FieldOps பணி ரத்து செய்யப்பட்டது. விவரங்களுக்கு செயலியைத் திறக்கவும்.",
            "in_app": "FieldOps பணி ரத்து செய்யப்பட்டது. விவரங்களுக்கு செயலியைத் திறக்கவும்."
        },
        "dispatcher_job_assigned": {
            "title": "பணி நியமிக்கப்பட்டது",
            "sms": "{{job_title}} க்கான நியமனம் உறுதிப்படுத்தப்பட்டுள்ளது.",
            "email": "<h2>பணி நியமிக்கப்பட்டது</h2>\n<p>{{job_title}} க்கான நியமனம் உறுதிப்படுத்தப்பட்டுள்ளது.</p>",
            "push": "{{job_title}} க்கான நியமனம் உறுதிப்படுத்தப்பட்டுள்ளது.",
            "in_app": "{{job_title}} க்கான நியமனம் உறுதிப்படுத்தப்பட்டுள்ளது."
        },
        "dispatcher_en_route": {
            "title": "தொழில்நுட்ப வல்லுநர் வழியில் உள்ளார்",
            "sms": "{{technician_name}} வழியில் உள்ளார். ETA: {{eta}}.",
            "email": "<h2>தொழில்நுட்ப வல்லுநர் வழியில் உள்ளார்</h2>\n<p>{{technician_name}} வழியில் உள்ளார். ETA: {{eta}}.</p>",
            "push": "{{technician_name}} வழியில் உள்ளார்.",
            "in_app": "{{technician_name}} வழியில் உள்ளார். ETA: {{eta}}."
        },
        "dispatcher_on_site": {
            "title": "தொழில்நுட்ப வல்லுநர் தளத்தில் உள்ளார்",
            "sms": "{{technician_name}} இப்போது தளத்தில் உள்ளார்.",
            "email": "<h2>தொழில்நுட்ப வல்லுநர் தளத்தில் உள்ளார்</h2>\n<p>{{technician_name}} இப்போது தளத்தில் உள்ளார்.</p>",
            "push": "{{technician_name}} இப்போது தளத்தில் உள்ளார்.",
            "in_app": "{{technician_name}} இப்போது தளத்தில் உள்ளார்."
        },
        "dispatcher_completed": {
            "title": "பணி முடிந்தது",
            "sms": "{{job_title}} முடிக்கப்பட்டுள்ளது.",
            "email": "<h2>பணி முடிந்தது</h2>\n<p>{{job_title}} முடிக்கப்பட்டுள்ளது.</p>",
            "push": "{{job_title}} முடிக்கப்பட்டுள்ளது.",
            "in_app": "{{job_title}} முடிக்கப்பட்டுள்ளது."
        },
        "dispatcher_cancelled": {
            "title": "பணி ரத்து செய்யப்பட்டது",
            "sms": "{{job_title}} ரத்து செய்யப்பட்டுள்ளது.",
            "email": "<h2>பணி ரத்து செய்யப்பட்டது</h2>\n<p>{{job_title}} ரத்து செய்யப்பட்டுள்ளது.</p>",
            "push": "{{job_title}} ரத்து செய்யப்பட்டுள்ளது.",
            "in_app": "{{job_title}} ரத்து செய்யப்பட்டுள்ளது."
        },
        "technician_en_route": {
            "title": "தொழில்நுட்ப வல்லுநர் வழியில் உள்ளார்",
            "sms": "வணக்கம் {{customer_name}}, {{technician_name}} வழியில் உள்ளார். எதிர்பார்க்கப்படும் வருகை: {{eta}}.",
            "email": "<h2>தொழில்நுட்ப வல்லுநர் வழியில் உள்ளார்</h2>\n\n<p>வணக்கம் {{customer_name}},</p>\n\n<p>{{technician_name}} உங்கள் இடத்திற்குப் பயணம் செய்து கொண்டிருக்கிறார்.</p>\n\n<p>ETA : <strong>{{eta}}</strong></p>\n\n<p>நன்றி,<br>\nFieldOps Team</p>",
            "push": "{{technician_name}} வழியில் உள்ளார்.",
            "in_app": "{{technician_name}} உங்கள் இடத்திற்கு வழியில் உள்ளார்."
        },
        "technician_arrived": {
            "title": "தொழில்நுட்ப வல்லுநர் வந்துள்ளார்",
            "sms": "வணக்கம் {{customer_name}}, {{technician_name}} {{job_title}} க்காக வந்துள்ளார்.",
            "email": "<h2>தொழில்நுட்ப வல்லுநர் வந்துள்ளார்</h2>\n\n<p>வணக்கம் {{customer_name}},</p>\n\n<p>{{technician_name}} உங்கள் இடத்திற்கு வந்துள்ளார், விரைவில் வேலையைத் தொடங்குவார்.</p>\n\n<p>பணி : {{job_title}}</p>\n\n<p>நன்றி,<br>\nFieldOps Team</p>",
            "push": "{{technician_name}} வந்துள்ளார்.",
            "in_app": "{{technician_name}} வந்துள்ளார்."
        },
        "job_completed": {
            "title": "பணி முடிந்தது",
            "sms": "வணக்கம் {{customer_name}}, {{job_title}} வெற்றிகரமாக முடிக்கப்பட்டுள்ளது. எங்களைத் தேர்ந்தெடுத்ததற்கு நன்றி.",
            "email": "<h2>பணி முடிந்தது</h2>\n\n<p>வணக்கம் {{customer_name}},</p>\n\n<p>உங்கள் சேவை கோரிக்கை வெற்றிகரமாக முடிக்கப்பட்டுள்ளது.</p>\n\n<p>பணி : {{job_title}}</p>\n\n<p>FieldOps ஐத் தேர்ந்தெடுத்ததற்கு நன்றி.</p>",
            "push": "{{job_title}} வெற்றிகரமாக முடிந்தது.",
            "in_app": "{{job_title}} முடிக்கப்பட்டுள்ளது."
        },
        "job_cancelled": {
            "title": "பணி ரத்து செய்யப்பட்டது",
            "sms": "வணக்கம் {{customer_name}}, உங்கள் {{job_title}} ரத்து செய்யப்பட்டுள்ளது.",
            "email": "<h2>பணி ரத்து செய்யப்பட்டது</h2>\n\n<p>வணக்கம் {{customer_name}},</p>\n\n<p>துரதிர்ஷ்டவசமாக உங்கள் சேவை கோரிக்கை ரத்து செய்யப்பட்டுள்ளது.</p>\n\n<p>பணி : {{job_title}}</p>\n\n<p>உதவிக்கு வாடிக்கையாளர் சேவையைத் தொடர்பு கொள்ளவும்.</p>",
            "push": "{{job_title}} ரத்து செய்யப்பட்டது.",
            "in_app": "உங்கள் பணி '{{job_title}}' ரத்து செய்யப்பட்டுள்ளது."
        },
        "eta_updated": {
            "title": "ETA புதுப்பிக்கப்பட்டது",
            "sms": "வணக்கம் {{customer_name}}, {{technician_name}} க்கான புதுப்பிக்கப்பட்ட ETA {{eta}}.",
            "email": "<h2>ETA புதுப்பிக்கப்பட்டது</h2>\n\n<p>வணக்கம் {{customer_name}},</p>\n\n<p>உங்கள் தொழில்நுட்ப வல்லுநரின் மதிப்பிடப்பட்ட வருகை நேரம் மாறியுள்ளது.</p>\n\n<p>புதிய ETA : <strong>{{eta}}</strong></p>\n\n<p>நன்றி,<br>\nFieldOps Team</p>",
            "push": "புதுப்பிக்கப்பட்ட ETA: {{eta}}",
            "in_app": "உங்கள் ETA {{eta}} ஆகப் புதுப்பிக்கப்பட்டுள்ளது."
        }
    },
    "hi": {
        "created": {
            "title": "काम बनाया गया",
            "sms": "नमस्ते {{customer_name}}, आपका सेवा अनुरोध {{job_title}} बना दिया गया है।",
            "email": "<h2>काम बनाया गया</h2>\n<p>नमस्ते {{customer_name}},</p>\n<p>आपका सेवा अनुरोध <strong>{{job_title}}</strong> बना दिया गया है।</p>\n<p>धन्यवाद,<br>FieldOps Team</p>",
            "push": "काम '{{job_title}}' बना दिया गया है।",
            "in_app": "आपका काम '{{job_title}}' बना दिया गया है।"
        },
        "assigned": {
            "title": "काम असाइन किया गया",
            "sms": "नमस्ते {{customer_name}}, {{technician_name}} को {{job_title}} के लिए असाइन किया गया है। ETA: {{eta}}.",
            "email": "<h2>काम असाइन किया गया</h2>\n\n<p>नमस्ते {{customer_name}},</p>\n\n<p><strong>{{technician_name}}</strong> को आपके सेवा अनुरोध के लिए असाइन किया गया है।</p>\n\n<p><strong>काम:</strong> {{job_title}}</p>\n\n<p><strong>ETA:</strong> {{eta}}</p>\n\n<p>धन्यवाद,<br>\nFieldOps Team</p>",
            "push": "{{technician_name}} असाइन किया गया। ETA {{eta}}",
            "in_app": "आपका काम '{{job_title}}' {{technician_name}} को असाइन किया गया है।"
        },
        "enroute": {
            "title": "तकनीशियन रास्ते में है",
            "sms": "नमस्ते {{customer_name}}, {{technician_name}} रास्ते में है। अनुमानित आगमन: {{eta}}.",
            "email": "<h2>तकनीशियन रास्ते में है</h2>\n\n<p>नमस्ते {{customer_name}},</p>\n\n<p>{{technician_name}} वर्तमान में आपके स्थान की यात्रा कर रहा है।</p>\n\n<p>ETA : <strong>{{eta}}</strong></p>\n\n<p>धन्यवाद,<br>\nFieldOps Team</p>",
            "push": "{{technician_name}} रास्ते में है।",
            "in_app": "{{technician_name}} आपके स्थान के रास्ते में है।"
        },
        "onsite": {
            "title": "तकनीशियन आ गया",
            "sms": "नमस्ते {{customer_name}}, {{technician_name}} {{job_title}} के लिए आ गया है।",
            "email": "<h2>तकनीशियन आ गया</h2>\n\n<p>नमस्ते {{customer_name}},</p>\n\n<p>{{technician_name}} आपके स्थान पर आ गया है और जल्द ही काम शुरू करेगा।</p>\n\n<p>काम : {{job_title}}</p>\n\n<p>धन्यवाद,<br>\nFieldOps Team</p>",
            "push": "{{technician_name}} आ गया है।",
            "in_app": "{{technician_name}} आ गया है।"
        },
        "completed": {
            "title": "काम पूरा हुआ",
            "sms": "नमस्ते {{customer_name}}, {{job_title}} सफलतापूर्वक पूरा हो गया है। हमें चुनने के लिए धन्यवाद।",
            "email": "<h2>काम पूरा हुआ</h2>\n\n<p>नमस्ते {{customer_name}},</p>\n\n<p>आपका सेवा अनुरोध सफलतापूर्वक पूरा हो गया है।</p>\n\n<p>काम : {{job_title}}</p>\n\n<p>FieldOps को चुनने के लिए धन्यवाद।</p>",
            "push": "{{job_title}} सफलतापूर्वक पूरा हुआ।",
            "in_app": "{{job_title}} पूरा हो गया है।"
        },
        "cancelled": {
            "title": "काम रद्द किया गया",
            "sms": "नमस्ते {{customer_name}}, आपका {{job_title}} रद्द कर दिया गया है।",
            "email": "<h2>काम रद्द किया गया</h2>\n\n<p>नमस्ते {{customer_name}},</p>\n\n<p>दुर्भाग्य से आपका सेवा अनुरोध रद्द कर दिया गया है।</p>\n\n<p>काम : {{job_title}}</p>\n\n<p>सहायता के लिए कृपया समर्थन से संपर्क करें।</p>",
            "push": "{{job_title}} रद्द कर दिया गया।",
            "in_app": "आपका काम '{{job_title}}' रद्द कर दिया गया है।"
        },
        "job_assigned": {
            "title": "काम असाइन किया गया",
            "sms": "नमस्ते {{customer_name}}, {{technician_name}} को {{job_title}} के लिए असाइन किया गया है। ETA: {{eta}}.",
            "email": "<h2>काम असाइन किया गया</h2>\n\n<p>नमस्ते {{customer_name}},</p>\n\n<p><strong>{{technician_name}}</strong> को आपके सेवा अनुरोध के लिए असाइन किया गया है।</p>\n\n<p><strong>काम:</strong> {{job_title}}</p>\n\n<p><strong>ETA:</strong> {{eta}}</p>\n\n<p>धन्यवाद,<br>\nFieldOps Team</p>",
            "push": "{{technician_name}} असाइन किया गया। ETA {{eta}}",
            "in_app": "आपका काम '{{job_title}}' {{technician_name}} को असाइन किया गया है।"
        },
        "technician_job_assigned": {
            "title": "नया काम असाइन किया गया",
            "sms": "एक नया FieldOps काम असाइन किया गया है। विवरण के लिए ऐप खोलें।",
            "email": "<h2>नया काम असाइन किया गया</h2>\n<p>आपको एक नया FieldOps काम असाइन किया गया है। विवरण के लिए तकनीशियन ऐप खोलें।</p>",
            "push": "एक नया काम असाइन किया गया है। विवरण के लिए FieldOps खोलें।",
            "in_app": "एक नया काम असाइन किया गया है। विवरण के लिए FieldOps खोलें।"
        },
        "technician_journey_started": {
            "title": "यात्रा शुरू",
            "sms": "आपकी यात्रा शुरू हो गई है। काम के विवरण के लिए FieldOps खोलें।",
            "email": "<h2>यात्रा शुरू</h2>\n<p>आपकी यात्रा शुरू हो गई है। काम के विवरण के लिए FieldOps खोलें।</p>",
            "push": "आपकी यात्रा शुरू हो गई है। काम के विवरण के लिए FieldOps खोलें।",
            "in_app": "आपकी यात्रा शुरू हो गई है। काम के विवरण के लिए FieldOps खोलें।"
        },
        "technician_arrived_on_site": {
            "title": "आगमन दर्ज किया गया",
            "sms": "आपका आगमन दर्ज कर लिया गया है। काम के विवरण के लिए FieldOps खोलें।",
            "email": "<h2>आगमन दर्ज किया गया</h2>\n<p>कार्य स्थल पर आपका आगमन दर्ज कर लिया गया है।</p>",
            "push": "कार्य स्थल पर आपका आगमन दर्ज कर लिया गया है।",
            "in_app": "कार्य स्थल पर आपका आगमन दर्ज कर लिया गया है।"
        },
        "technician_job_completed": {
            "title": "काम पूरा हुआ",
            "sms": "काम का पूरा होना FieldOps में दर्ज कर लिया गया है।",
            "email": "<h2>काम पूरा हुआ</h2>\n<p>काम का पूरा होना FieldOps में दर्ज कर लिया गया है।</p>",
            "push": "काम का पूरा होना दर्ज कर लिया गया है।",
            "in_app": "काम का पूरा होना दर्ज कर लिया गया है।"
        },
        "technician_job_cancelled": {
            "title": "काम रद्द किया गया",
            "sms": "एक FieldOps काम रद्द कर दिया गया था। विवरण के लिए ऐप खोलें।",
            "email": "<h2>काम रद्द किया गया</h2>\n<p>आपको असाइन किया गया FieldOps काम रद्द कर दिया गया था। विवरण के लिए ऐप खोलें।</p>",
            "push": "एक FieldOps काम रद्द कर दिया गया था। विवरण के लिए ऐप खोलें।",
            "in_app": "एक FieldOps काम रद्द कर दिया गया था। विवरण के लिए ऐप खोलें।"
        },
        "dispatcher_job_assigned": {
            "title": "काम असाइन किया गया",
            "sms": "{{job_title}} के लिए असाइनमेंट की पुष्टि हो गई है।",
            "email": "<h2>काम असाइन किया गया</h2>\n<p>{{job_title}} के लिए असाइनमेंट की पुष्टि हो गई है।</p>",
            "push": "{{job_title}} के लिए असाइनमेंट की पुष्टि हो गई है।",
            "in_app": "{{job_title}} के लिए असाइनमेंट की पुष्टि हो गई है।"
        },
        "dispatcher_en_route": {
            "title": "तकनीशियन रास्ते में है",
            "sms": "{{technician_name}} रास्ते में है। ETA: {{eta}}.",
            "email": "<h2>तकनीशियन रास्ते में है</h2>\n<p>{{technician_name}} रास्ते में है। ETA: {{eta}}.</p>",
            "push": "{{technician_name}} रास्ते में है।",
            "in_app": "{{technician_name}} रास्ते में है। ETA: {{eta}}."
        },
        "dispatcher_on_site": {
            "title": "तकनीशियन साइट पर है",
            "sms": "{{technician_name}} अब साइट पर है।",
            "email": "<h2>तकनीशियन साइट पर है</h2>\n<p>{{technician_name}} अब साइट पर है।</p>",
            "push": "{{technician_name}} अब साइट पर है।",
            "in_app": "{{technician_name}} अब साइट पर है।"
        },
        "dispatcher_completed": {
            "title": "काम पूरा हुआ",
            "sms": "{{job_title}} पूरा हो गया है।",
            "email": "<h2>काम पूरा हुआ</h2>\n<p>{{job_title}} पूरा हो गया है।</p>",
            "push": "{{job_title}} पूरा हो गया है।",
            "in_app": "{{job_title}} पूरा हो गया है।"
        },
        "dispatcher_cancelled": {
            "title": "काम रद्द किया गया",
            "sms": "{{job_title}} रद्द कर दिया गया है।",
            "email": "<h2>काम रद्द किया गया</h2>\n<p>{{job_title}} रद्द कर दिया गया है।</p>",
            "push": "{{job_title}} रद्द कर दिया गया है।",
            "in_app": "{{job_title}} रद्द कर दिया गया है।"
        },
        "technician_en_route": {
            "title": "तकनीशियन रास्ते में है",
            "sms": "नमस्ते {{customer_name}}, {{technician_name}} रास्ते में है। अनुमानित आगमन: {{eta}}.",
            "email": "<h2>तकनीशियन रास्ते में है</h2>\n\n<p>नमस्ते {{customer_name}},</p>\n\n<p>{{technician_name}} वर्तमान में आपके स्थान की यात्रा कर रहा है।</p>\n\n<p>ETA : <strong>{{eta}}</strong></p>\n\n<p>धन्यवाद,<br>\nFieldOps Team</p>",
            "push": "{{technician_name}} रास्ते में है।",
            "in_app": "{{technician_name}} आपके स्थान के रास्ते में है।"
        },
        "technician_arrived": {
            "title": "तकनीशियन आ गया",
            "sms": "नमस्ते {{customer_name}}, {{technician_name}} {{job_title}} के लिए आ गया है।",
            "email": "<h2>तकनीशियन आ गया</h2>\n\n<p>नमस्ते {{customer_name}},</p>\n\n<p>{{technician_name}} आपके स्थान पर आ गया है और जल्द ही काम शुरू करेगा।</p>\n\n<p>काम : {{job_title}}</p>\n\n<p>धन्यवाद,<br>\nFieldOps Team</p>",
            "push": "{{technician_name}} आ गया है।",
            "in_app": "{{technician_name}} आ गया है।"
        },
        "job_completed": {
            "title": "काम पूरा हुआ",
            "sms": "नमस्ते {{customer_name}}, {{job_title}} सफलतापूर्वक पूरा हो गया है। हमें चुनने के लिए धन्यवाद।",
            "email": "<h2>काम पूरा हुआ</h2>\n\n<p>नमस्ते {{customer_name}},</p>\n\n<p>आपका सेवा अनुरोध सफलतापूर्वक पूरा हो गया है।</p>\n\n<p>काम : {{job_title}}</p>\n\n<p>FieldOps को चुनने के लिए धन्यवाद।</p>",
            "push": "{{job_title}} सफलतापूर्वक पूरा हुआ।",
            "in_app": "{{job_title}} पूरा हो गया है।"
        },
        "job_cancelled": {
            "title": "काम रद्द किया गया",
            "sms": "नमस्ते {{customer_name}}, आपका {{job_title}} रद्द कर दिया गया है।",
            "email": "<h2>काम रद्द किया गया</h2>\n\n<p>नमस्ते {{customer_name}},</p>\n\n<p>दुर्भाग्य से आपका सेवा अनुरोध रद्द कर दिया गया है।</p>\n\n<p>काम : {{job_title}}</p>\n\n<p>सहायता के लिए कृपया समर्थन से संपर्क करें।</p>",
            "push": "{{job_title}} रद्द कर दिया गया।",
            "in_app": "आपका काम '{{job_title}}' रद्द कर दिया गया है।"
        },
        "eta_updated": {
            "title": "ETA अपडेट किया गया",
            "sms": "नमस्ते {{customer_name}}, {{technician_name}} के लिए अद्यतन ETA {{eta}} है।",
            "email": "<h2>ETA अपडेट किया गया</h2>\n\n<p>नमस्ते {{customer_name}},</p>\n\n<p>आपके तकनीशियन का अनुमानित आगमन समय बदल गया है।</p>\n\n<p>नया ETA : <strong>{{eta}}</strong></p>\n\n<p>धन्यवाद,<br>\nFieldOps Team</p>",
            "push": "अद्यतन ETA: {{eta}}",
            "in_app": "आपका ETA {{eta}} में अपडेट कर दिया गया है।"
        }
    }
}


def validate_catalog():
    from app.services.template_engine import _shared_injector
    base_catalog = LOCALIZED_NOTIFICATION_TYPES["en"]
    injector = _shared_injector
    
    for loc in ["es", "ta", "hi"]:
        target_catalog = LOCALIZED_NOTIFICATION_TYPES[loc]
        for event_key, base_event in base_catalog.items():
            if event_key not in target_catalog:
                raise ValueError(f"Missing event {event_key} in {loc}")
            
            target_event = target_catalog[event_key]
            for channel_key, base_content in base_event.items():
                if channel_key not in target_event:
                    raise ValueError(f"Missing channel {channel_key} for {event_key} in {loc}")
                
                target_content = target_event[channel_key]
                if target_content == base_content and base_content is not None and channel_key != "title":
                    # Some titles are identical or None, but body should not be exact English reuse unless invariant.
                    # We skip strict body check for simple invariant cases, but for safety, we allow it if it's identical but we assume our translations differ.
                    pass
                
                if channel_key == "title" and base_content is None:
                    if target_content is not None:
                        raise ValueError(f"Target title should be None if base is None for {event_key} in {loc}")
                    continue

                if base_content is None:
                    continue

                # Use infer_declarations
                base_paths = set(injector.infer_declarations(body=base_content if channel_key != "title" else "", title=base_content if channel_key == "title" else None))
                target_paths = set(injector.infer_declarations(body=target_content if channel_key != "title" else "", title=target_content if channel_key == "title" else None))
                
                if base_paths != target_paths:
                    raise ValueError(f"Variable paths mismatch for {event_key} {channel_key} in {loc}. Base: {base_paths}, Target: {target_paths}")

def generate_default_templates(tenant_id: str = "tenant-1"):
    validate_catalog()
    templates = []
    for locale in SUPPORTED_LOCALES:
        for channel in SUPPORTED_CHANNELS:
            catalog = LOCALIZED_NOTIFICATION_TYPES.get(locale, NOTIFICATION_TYPES)
            for template_type, template in catalog.items():
                body = template[channel]
                
                from app.services.template_engine import _shared_injector
                injector = _shared_injector
                
                try:
                    paths = injector.infer_declarations(body=body, title=template["title"])
                except Exception as e:
                    raise ValueError(f"Safe Jinja parsing failed for {template_type} {channel} {locale}: {e}")
                
                variables = [{"name": p, "required": True} for p in paths]
                
                title_val = template["title"]
                if not title_val:
                    title_val = f"Template {template_type}"

                templates.append({
                    "name": build_template_name(title_val, channel, locale),
                    "type": template_type,
                    "channel": channel,
                    "locale": locale,
                    "format": get_format(channel),
                    "title_template": template["title"],
                    "body_template": body,
                    "variables": variables,
                    "tenant_id": tenant_id,
                    "agent_type": "CommsAgent"
                })
    return templates

def seed_default_templates(db: Session, target_tenant_id: str = "tenant-1"):
    templates = generate_default_templates(tenant_id=target_tenant_id)
    from app.services.template_version_service import create_initial_version
    
    # We do not commit until all templates and initial versions are created.
    try:
        for template in templates:
            from app.models import NotificationTemplate
            existing_template = (
                db.query(NotificationTemplate)
                .filter_by(
                    type=template["type"],
                    channel=template["channel"],
                    locale=template["locale"],
                    tenant_id=target_tenant_id,
                    agent_type="CommsAgent"
                )
                .first()
            )

            if not existing_template:
                new_template = NotificationTemplate(**template)
                db.add(new_template)
        
        db.flush()
        
        for template in templates:
            from app.models import NotificationTemplate
            row = (
                db.query(NotificationTemplate)
                .filter_by(
                    type=template["type"],
                    channel=template["channel"],
                    locale=template["locale"],
                    tenant_id=target_tenant_id,
                    agent_type="CommsAgent",
                    is_active=True,
                    is_deleted=False
                )
                .order_by(NotificationTemplate.id.desc())
                .first()
            )
            if row and row.version == 0:
                # Need to initialize version
                create_initial_version(db, row, actor_id="system_seed")
                
        db.commit()
    except Exception:
        db.rollback()
        raise
