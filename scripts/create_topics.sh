#!/usr/bin/env bash
set -euo pipefail
BOOTSTRAP=${KAFKA_BOOTSTRAP:-kafka:29092}
 
create () {
  docker compose exec -T kafka kafka-topics --bootstrap-server "$BOOTSTRAP" \
    --create --if-not-exists --topic "$1" --partitions "$2" --replication-factor 1
}
 
create txn.raw 6
create txn.scored 6
create txn.alerted 3
create txn.dlq 1
 
echo "topics ready:"
docker compose exec -T kafka kafka-topics --bootstrap-server "$BOOTSTRAP" --list