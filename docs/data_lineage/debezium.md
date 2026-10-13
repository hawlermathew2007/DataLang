Change Data Capture (CDC) in databases is a software design pattern that tracks and captures row-level modifications—specifically inserts, updates, and deletes—in a source database and delivers them to downstream systems in near real time.

A Debezium connector is a distributed, log-based Change Data Capture (CDC) component that taps into database transaction logs (such as MySQL binlogs, PostgreSQL Write-Ahead Logs, or Oracle LogMiner) to record row-level INSERT, UPDATE, and DELETE events in real time.

Core Architecture & Deployment

• Apache Kafka Connect: The standard deployment model, running connectors as plugins inside a Kafka Connect cluster to stream change events directly into Kafka topics.
• Debezium Server: A ready-to-use, standalone application that streams database changes directly to messaging or storage infrastructures like Amazon Kinesis, Google Cloud Pub/Sub, or Apache Pulsar without needing a full Kafka setup.
• Debezium Engine: An embedded Java library that allows custom applications to run CDC logic directly inside their own processes.
