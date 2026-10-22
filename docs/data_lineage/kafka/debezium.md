## About Debezium

A Debezium connector is a distributed, log-based Change Data Capture (CDC) component that taps into database transaction logs (such as MySQL binlogs, PostgreSQL Write-Ahead Logs, or Oracle LogMiner) to record row-level INSERT, UPDATE, and DELETE events in real time.

### Core Architecture & Deployment

• Apache Kafka Connect: The standard deployment model, running connectors as plugins inside a Kafka Connect cluster to stream change events directly into Kafka topics.
• Debezium Server: A ready-to-use, standalone application that streams database changes directly to messaging or storage infrastructures like Amazon Kinesis, Google Cloud Pub/Sub, or Apache Pulsar without needing a full Kafka setup.
• Debezium Engine: An embedded Java library that allows custom applications to run CDC logic directly inside their own processes.

### Debezium message shape

Each Kafka message is a change event with before, after and op fields in its payload. It describes a row change, not lineage. Lineage has to be built from what the message tells you (which table and which topic) plus the database catalog.

https://docs.yugabyte.com/stable/additional-features/change-data-capture/using-logical-replication/transformers/
