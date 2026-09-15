# Kafka Broker Configuration

## Purpose

This document defines the Kafka broker configuration used by the FieldOps event-streaming infrastructure for local and deployment environments.

## Broker Configuration

The Kafka broker runs as a single-node KRaft broker/controller in the repository Compose configuration.

- Node ID: `1`
- Process roles: `broker,controller`
- Controller quorum: `1@kafka:9093`
- Kafka listener: `PLAINTEXT://:9092`
- Controller listener: `CONTROLLER://:9093`
- Topic auto-creation: disabled
- Default partitions: `3`
- Default replication factor: `1` for the local single-broker setup

## Environment-Driven Settings

| Variable | Default | Purpose |
|---|---|---|
| `KAFKA_PORT` | `9092` | Host port exposed for Kafka clients |
| `KAFKA_LISTENERS` | `PLAINTEXT://:9092,CONTROLLER://:9093` | Broker and controller listener bindings |
| `KAFKA_ADVERTISED_LISTENERS` | `PLAINTEXT://localhost:${KAFKA_PORT:-9092}` | Address advertised to Kafka clients |
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` | Backend producer/consumer bootstrap address |
| `KAFKA_TOPIC` | `agent.message` | Topic created by Kafka initialization |
| `KAFKA_CONSUMER_GROUP` | `fieldops` | Consumer group used by the backend consumer |

Deployment environments should set `KAFKA_ADVERTISED_LISTENERS` and `KAFKA_BOOTSTRAP_SERVERS` to addresses reachable by the corresponding clients.

Do not commit credentials, passwords, API keys, or other secrets.

## Topic Initialization

The `kafka-init` Compose service waits for the Kafka broker healthcheck and creates `KAFKA_TOPIC` if it does not already exist.

The local topic uses:

- Partitions: `3`
- Replication factor: `1`
- Auto-create topics: disabled

## Health Check

The Kafka service uses `kafka-broker-api-versions.sh` against `localhost:9092` to verify broker connectivity.

The Kafka service uses `restart: unless-stopped`.

## Backend Connectivity

The existing `KafkaProducer` and `KafkaConsumerManager` read broker configuration from environment variables and default to `localhost:9092` for local development.

Kafka remains an infrastructure/event-streaming component and does not replace existing FieldOps domain or in-process agent communication behavior.

## Security and Configuration Rules

- Keep deployment-specific configuration environment-driven.
- Never commit Kafka credentials or other secrets.
- Use environment-specific advertised listener addresses.
- Keep the controller listener internal to the broker deployment unless explicitly required by the deployment architecture.

## Verification

Focused Kafka producer and consumer tests are maintained under `backend/tests/`.

Broker-level end-to-end verification requires a running Docker/Compose environment.
