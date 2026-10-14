import json
import logging

from confluent_kafka import Consumer, KafkaException

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

consumer = Consumer({
    "bootstrap.servers": "localhost:9092",
    "group.id": "python-cdc-backend",
    "auto.offset.reset": "earliest",
    "enable.auto.commit": False,
})

TOPICS = [
    "yb_test.public.orders",
]


def process_event(event: dict) -> None:
    payload = event.get("payload", event)

    # Debezium uses:
    # c = insert, u = update, d = delete, r = snapshot read
    operation = payload.get("op")
    before = payload.get("before")
    after = payload.get("after")
    source = payload.get("source", {})

    logger.info(
        "CDC event: operation=%s database=%s table=%s",
        operation,
        source.get("db"),
        source.get("table"),
    )

    if operation == "c":
        logger.info("Inserted row: %s", after)
    elif operation == "u":
        logger.info("Updated row: %s -> %s", before, after)
    elif operation == "d":
        logger.info("Deleted row: %s", before)
    elif operation == "r":
        logger.info("Snapshot row: %s", after)

    # TODO: update your metadata catalog, lineage store,
    # or downstream application database here.


def main() -> None:
    consumer.subscribe(TOPICS)

    try:
        while True:
            message = consumer.poll(1.0)

            if message is None:
                continue

            if message.error():
                raise KafkaException(message.error())

            raw_value = message.value()

            if raw_value is None:
                logger.warning("Received a null message value")
                consumer.commit(message=message, asynchronous=False)
                continue

            event = json.loads(raw_value.decode("utf-8"))
            process_event(event)

            # Commit only after successful processing.
            consumer.commit(message=message, asynchronous=False)

    except KeyboardInterrupt:
        logger.info("Stopping CDC consumer")
    finally:
        consumer.close()


if __name__ == "__main__":
    main()
