# Kafka Broker Configuration

## Purpose

This document defines the Kafka broker configuration used by the FieldOps event-streaming infrastructure for local and deployment environments.

## Broker Configuration

The Kafka broker runs as a single-node KRaft broker/controller in the repository Compose configuration.

- Node ID: `1`
- Process roles: `broker,controller`
- Controller quorum: `1@kafka:9093`
- Kafka listener: `INTERNAL://:9092,EXTERNAL://:29092`
- Controller listener: `CONTROLLER://:9093`
- Topic auto-creation: disabled
- Default partitions: `3`
- Default replication factor: `1` for the local single-broker setup; production-capable multi-broker environments should use `3`
- Minimum in-sync replicas: `1` locally; production-capable multi-broker environments should use `2`

## Environment-Driven Settings

| Variable | Default | Purpose |
|---|---|---|
| `KAFKA_PORT` | `29092` | Host port exposed for Kafka clients |
| `KAFKA_LISTENERS` | `INTERNAL://:9092,EXTERNAL://:29092,CONTROLLER://:9093` | Broker and controller listener bindings |
| `KAFKA_ADVERTISED_LISTENERS` | `INTERNAL://kafka:9092,EXTERNAL://localhost:29092` | Addresses advertised to Kafka clients |
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:29092` | Backend producer/consumer bootstrap address |
| `KAFKA_TOPICS` | `fieldops.job.events,fieldops.gps.events,fieldops.sla.events,fieldops.notification.events,fieldops.billing.events,fieldops.payment.events,fieldops.audit.events` | Comma-separated FieldOps Kafka topics initialized by `kafka-init` |
| `KAFKA_CONSUMER_GROUP` | `fieldops` | Consumer group used by the backend consumer |
| `KAFKA_DISPATCH_CONSUMER_GROUP` | `fieldops-dispatch` | Consumer group for dispatch processing |
| `KAFKA_GPS_CONSUMER_GROUP` | `fieldops-gps` | Consumer group for GPS tracking |
| `KAFKA_NOTIFICATIONS_CONSUMER_GROUP` | `fieldops-notifications` | Consumer group for notifications |
| `KAFKA_SLA_CONSUMER_GROUP` | `fieldops-sla` | Consumer group for SLA monitoring |
| `KAFKA_BILLING_CONSUMER_GROUP` | `fieldops-billing` | Consumer group for billing |
| `KAFKA_PAYMENT_CONSUMER_GROUP` | `fieldops-payment` | Consumer group for payment processing |
| `KAFKA_AUDIT_CONSUMER_GROUP` | `fieldops-audit` | Consumer group for audit processing |
| `KAFKA_DEFAULT_REPLICATION_FACTOR` | `1` | Default replication factor for broker-created topics |
| `KAFKA_REPLICATION_FACTOR` | `1` | Replication factor used by `kafka-init` when creating FieldOps topics |
| `KAFKA_MIN_INSYNC_REPLICAS` | `1` | Minimum in-sync replicas required for topic writes |
| `KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR` | `1` | Replication factor for Kafka consumer-offset storage |
| `KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR` | `1` | Replication factor for Kafka transaction state |
| `KAFKA_TRANSACTION_STATE_LOG_MIN_ISR` | `1` | Minimum in-sync replicas for Kafka transaction state |
| `KAFKA_ACKS` | `all` | Producer acknowledgement level used for durable event publication |

Deployment environments should set `KAFKA_ADVERTISED_LISTENERS` and `KAFKA_BOOTSTRAP_SERVERS` to addresses reachable by the corresponding clients.

Do not commit credentials, passwords, API keys, or other secrets.

## Topic Initialization

The `kafka-init` Compose service waits for the Kafka broker healthcheck and creates the configured FieldOps topics with their required partition counts.

Topic partition strategy:

| Topic | Partitions | Partition Key | Ordering Scope |
|---|---:|---|---|
| `fieldops.job.events` | `6` | `job_id` | Same job |
| `fieldops.gps.events` | `12` | `job_id` | Same job |
| `fieldops.sla.events` | `6` | `job_id` | Same job |
| `fieldops.notification.events` | `6` | `tenant_id` | Same tenant |
| `fieldops.billing.events` | `3` | `tenant_id` | Same tenant |
| `fieldops.payment.events` | `3` | `tenant_id` | Same tenant |
| `fieldops.audit.events` | `6` | `tenant_id` | Same tenant |

The local Kafka broker uses a replication factor of `1` because it is a single-broker development setup.

Kafka guarantees ordering only within a partition. Stable partition keys ensure related events are routed to the same partition and therefore preserve ordering within that key's scope.

Partition increases should be avoided unless required because changing the partition count can change the partition mapping for keyed events.

## Consumer Group Ownership

Each FieldOps Kafka processing domain uses a dedicated consumer group so unrelated consumers do not share offsets or compete for the same partitions.

| Topic | Consumer Group | Processing Domain |
|---|---|---|
| `fieldops.job.events` | `fieldops-dispatch` | Dispatch |
| `fieldops.gps.events` | `fieldops-gps` | GPS tracking |
| `fieldops.notification.events` | `fieldops-notifications` | Notifications |
| `fieldops.sla.events` | `fieldops-sla` | SLA monitoring |
| `fieldops.billing.events` | `fieldops-billing` | Billing |
| `fieldops.payment.events` | `fieldops-payment` | Payment |
| `fieldops.audit.events` | `fieldops-audit` | Audit |

Consumer group names are environment-driven through the corresponding `KAFKA_*_CONSUMER_GROUP` variables in `compose.yaml`. The defaults provide stable group IDs for local development.

Multiple consumer instances using the same group can distribute partitions for that processing domain. Consumers for different processing domains must use different group IDs so each domain receives its own logical stream.

## Replication and Durability

Replication settings are environment-driven so the same Compose configuration can support both local single-broker development and multi-broker deployment environments.

### Local Single-Broker Environment

The local development setup uses:

- Replication factor: `1`
- Minimum in-sync replicas: `1`
- Producer acknowledgements: `all`

With only one broker, there is no replica available on another broker. Therefore, a broker failure can make locally stored events unavailable. This is an expected limitation of the single-broker development environment.

### Multi-Broker Deployment Environment

A production-capable multi-broker environment should use:

- Replication factor: `3`
- Minimum in-sync replicas: `2`
- Producer acknowledgements: `all`
- Offset topic replication factor: `3`
- Transaction state replication factor: `3`
- Transaction state minimum in-sync replicas: `2`

With three brokers and a minimum of two in-sync replicas, committed event writes can remain available when one broker fails, provided the remaining replicas stay healthy and the Kafka cluster can elect an available leader.

If the number of in-sync replicas falls below the configured minimum, writes requiring the configured acknowledgement level should fail rather than accepting a write with insufficient replica durability.

The repository's local single-broker environment does not provide a true broker-failure resilience test. Multi-broker failure behavior must be validated in an environment with multiple Kafka brokers.

## Health Check

The Kafka service uses `kafka-broker-api-versions.sh` against `localhost:9092` to verify broker connectivity.

The Kafka service uses `restart: unless-stopped`.

## Backend Connectivity

The existing `KafkaProducer` and `KafkaConsumerManager` read broker configuration from environment variables and default to `localhost:29092` for local development.

Kafka remains an infrastructure/event-streaming component and does not replace existing FieldOps domain or in-process agent communication behavior.

## Security and Configuration Rules

- Keep deployment-specific configuration environment-driven.
- Never commit Kafka credentials or other secrets.
- Use environment-specific advertised listener addresses.
- Keep the controller listener internal to the broker deployment unless explicitly required by the deployment architecture.

## Verification

Focused Kafka producer and consumer tests are maintained under `backend/tests/`.

Broker-level end-to-end verification requires a running Docker/Compose environment.

The configured topic partition counts are verified against the running Kafka broker during infrastructure validation.

Consumer group verification should confirm:

- Each configured FieldOps topic has its dedicated consumer group.
- Different processing domains use different group IDs.
- Multiple consumers in the same group can distribute partitions for that domain.
- Environment-specific consumer group variables resolve to the intended group IDs.

Replication configuration verification should confirm:

- Local configuration resolves to replication factor `1` and minimum in-sync replicas `1`.
- Multi-broker deployment configuration resolves to replication factor `3` and minimum in-sync replicas `2`.
- Producer configuration uses `acks=all`.
- Running multi-broker environments verify replica count, ISR membership, and broker-failure recovery.