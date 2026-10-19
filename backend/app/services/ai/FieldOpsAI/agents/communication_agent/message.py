
"""Notification copy and live-card payload.

Customers get friendly, varied Swiggy/Zomato-style text.
Technicians and admins get short, factual text.
"""
import hashlib

from .events import EVENT_STEP, STEPS, JobEvent


# Short factual labels for technician and admin notifications.
EVENT_LABEL = {
    JobEvent.JOB_CREATED: "created",
    JobEvent.TECHNICIAN_ASSIGNED: "assigned",
    JobEvent.TECHNICIAN_ACCEPTED: "accepted by technician",
    JobEvent.TECHNICIAN_REJECTED: "rejected by technician",
    JobEvent.DELAYED: "delayed (technician trip paused)",
    JobEvent.EN_ROUTE: "technician en route",
    JobEvent.ON_SITE: "technician on site",
    JobEvent.SERVICE_STARTED: "service started",
    JobEvent.COMPLETED: "completed",
    JobEvent.CANCELLED: "cancelled",
    JobEvent.CLOSED: "closed",
}


# Multiple options are retained for deterministic, varied fallback copy.
# The technician's actual name is inserted at runtime.
_COPY_PARTS = {
    JobEvent.JOB_CREATED: (
        (
            "Booked and ready ✨",
            "Your request is on the board 🧰",
            "A fresh service request 📋",
        ),
        (
            "We'll keep you posted as it moves forward.",
            "Your service request is in. We'll share the next confirmed update here.",
            "We're getting your request started.",
        ),
    ),
    JobEvent.TECHNICIAN_ASSIGNED: (
        ("A technician is assigned",),
        ("Your service request has a technician assigned. We'll keep you posted.",),
    ),
    JobEvent.TECHNICIAN_ACCEPTED: (
        (
            "{technician_name} is on it 🙌",
            "Your request has a match ✨",
            "{technician_name} picked up your request 🧰",
        ),
        (
            "{technician_name} has accepted your service request. Your job is officially in good hands.",
            "{technician_name} is ready to take care of your service request. One step closer!",
            "{technician_name} has picked up your request. We'll keep you in the loop.",
        ),
    ),
    JobEvent.TECHNICIAN_REJECTED: (
        (
            "We're finding another match",
            "A new match is underway",
            "Still on it 🔎",
        ),
        (
            "We're looking for another technician for your request.",
            "Your request is back in matching while we find another technician.",
            "We're continuing the search for the right technician.",
        ),
    ),
    JobEvent.DELAYED: (
        (
            "A timing update ⏱️",
            "A small delay 🕒",
            "Keeping you posted 📍",
        ),
        (
            "Your technician's trip is delayed. We'll share a new estimate when one is confirmed.",
            "There's a delay on the trip, and no new arrival estimate is confirmed yet.",
            "Your technician is running behind. We'll update you when we have a confirmed estimate.",
        ),
    ),
    JobEvent.EN_ROUTE: (
        (
            "{technician_name} is on the way 📍",
            "The visit is in motion 🧭",
            "{technician_name} is heading your way 🚶",
            "Your service visit is moving ✨",
        ),
        (
            "{technician_name} is heading to your service visit. The toolbox is officially en route!",
            "{technician_name} has started the trip to your location. Your job is getting closer to the finish line!",
            "{technician_name} is on the way for your service request. Stay tuned for the next update!",
            "{technician_name} is making their way to your service visit. The next stop is you!",
        ),
    ),
    JobEvent.ON_SITE: (
        (
            "{technician_name} has arrived 👋",
            "{technician_name} is at your door 📍",
            "Your technician is here 🧰",
        ),
        (
            "{technician_name} has arrived for your service visit. The next chapter starts now!",
            "{technician_name} is at your service location. Your visit is ready to roll!",
            "{technician_name} has reached your location. Help is officially here!",
        ),
    ),
    JobEvent.SERVICE_STARTED: (
        ("Service work has started",),
        ("Your technician has arrived and started work on your service request.",),
    ),
    JobEvent.COMPLETED: (
        (
            "Service complete ✅",
            "All wrapped up 🎉",
            "That's done ✨",
        ),
        (
            "Your service request is marked complete. One less thing on your to-do list!",
            "The work has been marked complete. Consider that task handled!",
            "Your job is complete. That's a wrap!",
        ),
    ),
    JobEvent.CANCELLED: (
        (
            "Your request was cancelled ℹ️",
            "A change to your service request 📋",
            "Service request cancelled ℹ️",
        ),
        (
            "Your service request is cancelled.",
            "This job has been cancelled.",
            "The service visit has been cancelled.",
        ),
    ),
    JobEvent.CLOSED: (
        (
            "Your request is closed",
            "Service request wrapped up",
            "A final update",
        ),
        (
            "Your job has been closed.",
            "This service request is now closed.",
            "The job is now marked closed.",
        ),
    ),
}


def _stable_index(
    event: JobEvent,
    job,
    version: int | None,
    size: int,
) -> int:
    """Choose a stable copy variant for this job event/version."""
    if size <= 0:
        return 0

    seed = "|".join(
        (
            str(getattr(job, "id", "")),
            event.value,
        )
    )
    event_offset = int(
        hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8],
        16,
    )
    return (event_offset + int(version or 0)) % size


def _technician_name(technician) -> str | None:
    """Return a verified technician name, if one is available."""
    if technician is None:
        return None

    raw_name = getattr(technician, "technician_name", None)
    if not isinstance(raw_name, str):
        return None

    name = " ".join(raw_name.split())
    return name or None


def _first_name(technician) -> str | None:
    name = _technician_name(technician)
    return name.split(maxsplit=1)[0] if name else None


def personalize_customer_title(
    event: JobEvent,
    title: str,
    technician,
) -> str:
    """Personalize a customer title with the actual technician's first name."""
    first_name = _first_name(technician)

    if not first_name:
        return title

    if first_name.casefold() in title.casefold():
        return title

    named_titles = {
        JobEvent.TECHNICIAN_ACCEPTED:
            f"{first_name} picked up your request 🙌",
        JobEvent.EN_ROUTE:
            f"{first_name} is on the way 📍",
        JobEvent.ON_SITE:
            f"{first_name} has arrived 👋",
        JobEvent.COMPLETED:
            f"{first_name} wrapped it up ✅",
    }

    return named_titles.get(event, title)


def _render_customer_copy(
    event: JobEvent,
    job,
    technician,
    version: int | None,
) -> tuple[str, str]:
    """Build varied customer-facing copy using verified context."""
    titles, bodies = _COPY_PARTS.get(
        event,
        (
            ("A service update",),
            ("There's an update to your service request.",),
        ),
    )

    # Use the same variant index for title and body when both lists align.
    variant_count = min(len(titles), len(bodies))
    index = _stable_index(event, job, version, variant_count)

    name = _technician_name(technician)
    first_name = _first_name(technician)

    title = titles[index % len(titles)]
    body = bodies[index % len(bodies)]

    # Do not show unresolved placeholders or invent a technician name.
    if name:
        title = title.replace("{technician_name}", first_name or name)
        body = body.replace("{technician_name}", first_name or name)
    else:
        title = title.replace("{technician_name}", "Your technician")
        body = body.replace("{technician_name}", "Your technician")

    title = personalize_customer_title(event, title, technician)

    # Do not claim that a particular technician is assigned for an
    # event where a specific technician is not actually available.
    if event == JobEvent.TECHNICIAN_REJECTED:
        pass

    if event == JobEvent.EN_ROUTE:
        eta_min = getattr(job, "eta_min", None)

        if isinstance(eta_min, (int, float)) and not isinstance(eta_min, bool):
            if eta_min >= 0:
                eta_text = (
                    f"The latest estimated arrival is about "
                    f"{int(eta_min)} minutes."
                )
                body = f"{body} {eta_text}"

        body = f"{body} Tap Track live to follow the visit 👀"

    elif event == JobEvent.TECHNICIAN_ACCEPTED:
        body = f"{body} Open the job card for the latest details 👀"

    elif event == JobEvent.COMPLETED:
        body = f"{body} When you're ready, tell us how it went ⭐"

    service_type = (
        getattr(job, "service_type", None) or ""
    ).strip()

    if service_type and event == JobEvent.JOB_CREATED:
        body = (
            f"Your {service_type.lower()} request is in. "
            "We'll share the next confirmed update here."
        )

    return title, body


def build_copy(
    event: JobEvent,
    recipient,
    job,
    technician,
    version: int | None = None,
) -> tuple[str, str]:
    """Return (title, body) for the specified recipient."""
    if recipient.role == "customer":
        return _render_customer_copy(
            event=event,
            job=job,
            technician=technician,
            version=version,
        )

    # Technician/admin notifications remain short and factual.
    label = EVENT_LABEL.get(event, event.value)
    title = f"Job #{job.id} {label}"

    parts = [
        getattr(job, "service_type", None),
        getattr(job, "customer_name", None),
        _technician_name(technician),
    ]
    body = " · ".join(
        str(part).strip()
        for part in parts
        if isinstance(part, str) and part.strip()
    )

    return title, body


def build_card(event: JobEvent, job, technician) -> dict:
    """Build live-card metadata for notifications.notification_metadata.

    The frontend uses this payload for progress, technician details,
    ETA, and available actions. The technician's phone number is omitted.
    """
    job_id = job.id

    if event in (JobEvent.EN_ROUTE, JobEvent.ON_SITE):
        actions = [
            {
                "label": "Track live",
                "route": f"/jobs/{job_id}/track",
                "primary": True,
            }
        ]
    elif event == JobEvent.COMPLETED:
        actions = [
            {
                "label": "Rate",
                "route": f"/jobs/{job_id}/rate",
                "primary": True,
            }
        ]
    elif event == JobEvent.CANCELLED:
        actions = [
            {
                "label": "Book again",
                "route": "/jobs/new",
                "primary": True,
            }
        ]
    else:
        actions = [
            {
                "label": "View job",
                "route": f"/jobs/{job_id}",
                "primary": True,
            }
        ]

    name = _technician_name(technician)

    return {
        "steps": STEPS,
        "step": EVENT_STEP.get(event, 0),
        "state": (
            "cancelled"
            if event == JobEvent.CANCELLED
            else "active"
        ),
        "technician": {"name": name} if name else None,
        "eta_min": getattr(job, "eta_min", None),
        "eta_updated_at": getattr(job, "eta_updated_at", None),
        "actions": actions,
    }
