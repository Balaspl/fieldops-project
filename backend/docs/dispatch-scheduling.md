# Automatic dispatch scheduling

Jobs persist `preferred_service_date`, `preferred_service_time`, and
`preferred_service_timezone`. A missing visit time consistently defaults to
09:00 in the owning organization's `settings.timezone`; UTC is used when the
organization has no configured timezone. The due time for automatic dispatch
is one hour before the visit.

The worker scans pending, unassigned jobs every five minutes. It also consumes
a coalesced availability-change signal from technician heartbeat, GPS location,
and availability updates, then runs the same due-time check. This makes retries
bounded, recovers missed signals after restarts, and prevents availability
events from dispatching a future appointment early. Existing jobs with null
time/timezone fields use the documented defaults.

GPS availability and Planning both accept fixes through 150 m. Planning's
`DISPATCH_MAX_GPS_ACCURACY_METERS` setting controls its fallback for less
accurate fixes: by default, readings above 150 m are excluded, while a higher
configured threshold permits those readings. The Go Online API threshold
remains independently configurable with
`GPS_AVAILABILITY_MAX_ACCURACY_METERS`. Missing and stale locations continue
to follow Planning's existing exclusion policy.
