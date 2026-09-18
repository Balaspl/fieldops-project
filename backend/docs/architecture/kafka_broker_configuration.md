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
- Default replication factor: `1` for the local single-broker setup

## Environment-Driven Settings

| Variable | Default | Purpose |
|---|---|---|
| `KAFKA_PORT` | `29092` | Host port exposed for Kafka clients |
| `KAFKA_LISTENERS` | `INTERNAL://:9092,EXTERNAL://:29092,CONTROLLER://:9093` | Broker and controller listener bindings |
| `KAFKA_ADVERTISED_LISTENERS` | `INTERNAL://kafka:9092,EXTERNAL://localhost:29092` | Addresses advertised to Kafka clients |
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:29092` | Backend producer/consumer bootstrap address |
| `KAFKA_TOPICS` | `fieldops.job.events,fieldops.gps.events,fieldops.sla.events,fieldops.notification.events,fieldops.billing.events,fieldops.payment.events,fieldops.audit.events` | Comma-separated FieldOps Kafka topics initialized by `kafka-init` |
| `KAFKA_CONSUMER_GROUP` | `fieldops` | Consumer group used by the backend consumer |

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