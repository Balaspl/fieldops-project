"""Correct and complete shared customer support FAQ records.

Revision ID: e32ad70f6b8c
Revises: d8f14c62a930
"""
from alembic import op
import sqlalchemy as sa

revision = "e32ad70f6b8c"
down_revision = "d8f14c62a930"
branch_labels = None
depends_on = None

FAQS = [
    ("fieldops_overview", "What is FieldOps used for?", ["What does FieldOps do?", "How does FieldOps work?", "What is FieldOps?"], ["fieldops", "platform", "portal", "services"], "overview", "FieldOps provides a customer portal to submit and review service requests, check job progress, track a technician when live tracking is available, manage notification preferences, and access completion reports when a job has been closed."),
    ("portal_basics", "How can I use the customer portal?", ["What can I do in my portal?", "What can I do after I sign in?"], ["portal", "requests", "notifications", "tracking", "reports"], "portal", "Use the customer portal to create and review service requests, check status and tracking when available, manage notification preferences, and access reports for closed jobs. Use the Support page when you need help with your account or a request change."),
    ("request_information", "What information is required to create a service request?", ["What details do I need to book a service?", "What should I include in a request?"], ["required", "details", "information", "request", "service"], "requests", "The request form requires a title, issue description, service type, priority, service location confirmed on the map, and a 10-digit contact number. The preferred service date is optional. The form identifies any required information that is missing."),
    ("after_submission", "What happens after I submit a service request?", ["What happens next after booking?", "Where can I see the request I just submitted?"], ["submission", "request", "status", "updates"], "requests", "After submission, the request appears in Service Requests with its latest recorded status. Check that page for request details and progress. A preferred service date is a request preference, not a confirmed arrival time."),
    ("service_request_missing", "Why is my service request missing?", ["I cannot see my request", "Where did my booking go?", "My service request is not showing"], ["missing", "cannot see", "not showing", "request", "portal"], "portal", "The portal shows requests linked to your signed-in customer account. Check that you are signed into the correct account and refresh the Service Requests page. If it is still missing, contact the team through the Support page so they can check your account."),
    ("portal_page_issue", "What should I do if a portal page is not loading?", ["The page is stuck", "Why is the portal not loading?", "I see an error in the portal"], ["page", "loading", "error", "refresh", "portal"], "portal", "Refresh the page and sign in again if your session has expired. If the problem continues, contact the FieldOps team through the Support page and include the page name and the error you see."),
    ("create_service_request", "How do I create a service request?", ["How can I book a service?", "I need to request a service", "How do I book a technician?"], ["create", "book", "request", "service", "new"], "requests", "Open Service Requests in your FieldOps customer portal and choose the option to create a request. Select from the service types shown there and submit the request details. You can review its status in the same section."),
    ("available_services", "What services does FieldOps offer?", ["What kind of services do you provide?", "Which services can I book?", "What can FieldOps help with?"], ["services", "service types", "offer", "available", "catalog"], "services", "The service request form currently offers HVAC Repair, Electrical, Plumbing, Network Support, General Maintenance, Appliance Repair, Roofing & Carpentry, and CCTV & Security."),
    ("preferred_service_date", "How do preferred service dates and scheduling work?", ["Can I choose a preferred service date?", "How are appointments scheduled?", "Can I request a service date?"], ["appointment", "schedule", "date", "preference"], "appointments", "When you create a service request, you can provide a preferred service date. It records your requested date and is not a confirmed appointment or arrival time. Check the request status and tracking area in your portal for current assignment and arrival information; use the Support page for booking changes."),
    ("track_service_request", "How does technician tracking work?", ["How can I track the progress of a service request?", "How does live tracking work?", "When is live tracking available?"], ["track", "tracking", "technician", "progress", "live"], "tracking", "Open the Service Requests or tracking area in your customer portal to view your request status. Live tracking is shown when available for an en-route technician. For help with a request, use the Support page."),
    ("service_statuses", "What do the service request statuses mean?", ["What does In Progress mean?", "What do created or assigned mean?", "What are the different request statuses?"], ["status", "created", "assigned", "en route", "on site", "in progress", "completed", "cancelled", "closed"], "status", "A request can move through statuses such as CREATED (received), ASSIGNED (a technician is assigned), EN_ROUTE (on the way), ON_SITE (arrived), IN_PROGRESS (work is underway), COMPLETED (work marked complete), CANCELLED, or CLOSED. A request may also show UNASSIGNED while it is awaiting technician assignment."),
    ("customer_notifications", "How will I receive service updates?", ["Do you send notifications?", "How can I get updates about my request?", "Where are my alerts?"], ["notification", "notifications", "updates", "alerts", "email", "sms"], "notifications", "Service updates are available in the Notifications area of your FieldOps portal. You can review and manage your notification preferences there. The exact channels depend on your account's configured preferences."),
    ("completion_report", "How do I get a completion or closure report?", ["Where can I download my job report?", "Can I get proof the work is complete?", "How do I view the service report?", "What is a closure report?"], ["closure", "completion", "report", "pdf", "download", "proof"], "reports", "A closure report is a PDF for a service request linked to a job with a recorded closure. It includes the job and service, status, location, completion time, and recorded work summary. Open the job in your customer portal and use its report option when a closure record is available."),
    ("change_or_cancel_request", "How do I change or cancel a service request?", ["Can I reschedule my appointment?", "I need to cancel my booking", "How do I edit my request?"], ["change", "edit", "cancel", "reschedule", "booking"], "requests", "Open the request in Service Requests to see whether editing or cancellation is currently available. The portal allows changes only for eligible request statuses. For a reschedule or a request that cannot be changed there, contact the team through the Support page."),
]


def upgrade() -> None:
    bind = op.get_bind()
    faqs = sa.table(
        "customer_support_faqs",
        sa.column("tenant_id", sa.String(50)),
        sa.column("faq_key", sa.String(100)),
        sa.column("question", sa.String(500)),
        sa.column("alternate_questions", sa.JSON()),
        sa.column("keywords", sa.JSON()),
        sa.column("answer", sa.Text()),
        sa.column("category", sa.String(60)),
        sa.column("language", sa.String(12)),
        sa.column("is_published", sa.Integer()),
    )
    for key, question, alternatives, keywords, category, answer in FAQS:
        values = {
            "faq_key": key, "question": question,
            "alternate_questions": alternatives, "keywords": keywords,
            "answer": answer, "category": category, "language": "en",
            "is_published": 1,
        }
        existing = bind.execute(sa.select(faqs.c.faq_key).where(
            faqs.c.tenant_id.is_(None), faqs.c.faq_key == key,
        )).first()
        if existing:
            bind.execute(sa.update(faqs).where(
                faqs.c.tenant_id.is_(None), faqs.c.faq_key == key,
            ).values(**values))
        else:
            bind.execute(sa.insert(faqs).values(tenant_id=None, **values))


def downgrade() -> None:
    # Keep the reviewed shared answers intact when rolling back code.
    pass
