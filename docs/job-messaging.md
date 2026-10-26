# Customer and technician job messaging

FieldOps stores a message thread against each numeric job ID. Customers enter from the assigned technician section on their job card; technicians enter from the assigned job detail or terminal job history. The conversation is persisted in PostgreSQL before a send request succeeds. History is available through the REST endpoint after reconnect, while the existing authenticated Socket.IO connection delivers new messages and delivery/read events to the authenticated participant rooms. Chat events use the `job_message*` event names and do not use GPS tracking channels.

## Access and lifecycle policy

- Customer access comes from the signed-in customer’s `ServiceRequest` ownership and tenant, linked to that job.
- Technician access comes from the signed-in technician account and the job’s current `assigned_technician_id`, including cross-tenant assignments.
- The customer can read the job’s thread history. The currently assigned technician can read and reply. A technician who is no longer assigned is denied, including after reassignment. A newly assigned technician inherits the job thread so the customer does not lose context.
- Unassigned jobs do not create a conversation. The customer card displays that chat becomes available after assignment. A history lookup is read-only if the job no longer has an assignee.
- Completed, closed, and cancelled job threads remain readable and are read-only. This keeps the job record and prior conversation intact.
- Messages are unread until history is opened or a recipient acknowledges delivery. Opening the thread marks incoming messages as read. The customer cards show only the server-confirmed unread count.

## Multi-worker deployment

For one backend process, the existing Socket.IO server delivers events in process. When the API runs with multiple workers or instances, configure `SOCKETIO_REDIS_URL` to the shared Redis URL (for example, the same Redis service used by the application). The Socket.IO Redis manager distributes `job_message`, `job_message_delivered`, and `job_message_read` events across workers. Persisted history remains the recovery path when Redis or a recipient connection is offline.

## API

- `GET /api/v1/job-messages/jobs/{job_id}` retrieves history and marks incoming messages read.
- `GET /api/v1/job-messages/jobs/{job_id}/unread-count` returns the authenticated participant’s unread count.
- `POST /api/v1/job-messages/jobs/{job_id}` persists a message and then emits it to the other participant.
- `POST /api/v1/job-messages/jobs/{job_id}/messages/{message_id}/delivered` records recipient delivery acknowledgement.

All endpoints derive customer, technician, and tenant identities from the authenticated session and database relationships. The client sends only the job ID and message text.
