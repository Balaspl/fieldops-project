# Secret management

Application secrets are supplied at runtime through environment variables or a deployment secret manager. Do not commit secret values or include them in logs, error messages, or API responses.

## Configuration inventory

| Setting | Used for | Required |
| --- | --- | --- |
| `JWT_SECRET` | API and WebSocket JWT signing and verification | Always |
| `DATABASE_URL` | Database connection, including credentials in the URL | Backend runtime |
| `MFA_ENCRYPTION_KEY` | MFA-related encryption | When MFA encryption is enabled |
| `DATA_ENCRYPTION_KEY` | Authenticated encryption for selected personal/contact fields at rest | Always; injected into backend and migration processes |
| `GROQ_API_KEY` | Groq provider | When the Groq provider is enabled |
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` | SMS delivery | When Twilio is enabled |
| `SMTP_PASSWORD` | SMTP email delivery | When authenticated SMTP is enabled |
| `OIDC_CLIENT_SECRET` | OIDC authorization | When the configured OIDC provider requires it |
| `GOOGLE_MAPS_API_KEY`, `OLA_MAPS_API_KEY` | Map and geocoding integrations | When the respective integration is enabled |
| `KAFKA_*_PASSWORD` | Kafka broker and service principals | When Kafka authentication is enabled |

`backend/app/secret.py` validates `JWT_SECRET` and `DATA_ENCRYPTION_KEY`, and rejects known placeholder values in configured secret settings in production. Production is selected with `APP_ENV=production` (also accepts `ENVIRONMENT=production` or `ENV=production`); production JWT secrets must contain at least 32 characters. Provide randomly generated values from the deployment's secret store. Development and test environments must also explicitly provide a data-encryption key; tests use a test-only key from `conftest.py`.

## Injection

Configure the values in the deployment platform's secret manager and inject them into the backend process. For Docker Compose, provide values through the operator-managed environment or secret integration before starting services. Keep local `.env` files untracked and restrict their file permissions. Never put live credentials in the Compose file, image, or source tree.

## Rotation

1. Generate a new credential in the provider or secret manager.
2. Update the deployment secret and roll out the application with the new value.
3. For `JWT_SECRET`, coordinate the rollout because tokens signed with the previous key will no longer verify; users may need to authenticate again. For zero-downtime JWT rotation, implement a planned key ID and overlap window before rotating.
4. Verify the integration is healthy, then revoke the old provider credential.
5. Review deployment logs to confirm validation errors do not contain secret values.

For encrypted personal/contact fields, follow the field classification, migration, and controlled key-rotation procedure in [sensitive-data-at-rest.md](sensitive-data-at-rest.md). Never replace `DATA_ENCRYPTION_KEY` without re-encrypting the database fields with the documented rotation procedure.
