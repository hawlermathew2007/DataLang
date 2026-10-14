## Education

### CDC

Change Data Capture (CDC) in databases is a software design pattern that tracks and captures row-level modifications—specifically inserts, updates, and deletes—in a source database and delivers them to downstream systems in near real time.

### WAL

PostgreSQL Write-Ahead Logging (WAL) is a core architectural feature that records all database modifications to a sequential log on diPostgreSQL Write-Ahead Logging (WAL) is a core architectural feature that records all database modifications to a sequential log on disk before applying them to the actual table and index filessk before applying them to the actual table and index files

### Logical Replication

**Why enable logical replication?**

PostgreSQL normally writes changes to its write-ahead log (WAL) foPostgreSQL normally writes changes to its write-ahead log (WAL) for durability and recovery. Debezium needs a way to decode committed changes from that log into row-level events.r durability and recovery. Debezium needs a way to decode committed changes from that log into row-level events.

PostgreSQL calls this logical decoding. For Debezium's standard PostgreSQL connector, the server must use wal_level = logical, have available replication slots, and support WAL senders. The official documentation describes these prerequisites ePostgreSQL calls this logical decoding. For Debezium's standard PostgreSQL connector, the server must use wal_level = logical, have available replication slots, and support WAL senders. The official documentation describes these prerequisites explicitly. 

Setting & Why it matters
wal_level = logical     :	Makes the WAL contain information needed for logical decoding.
max_replication_slots   :	Allows persistent positions for CDC consumers to be maintained.
max_wal_senders         :	Allows replication connections to stream WAL data.

### Publication

A PostgreSQL publication defines which tables and operations are exposed through logical replication.

**Why create a publication?**

Debezium's PostgreSQL connector uses the pgoutput plugin to consume changes from a publication. The publication acts as the table-selection boundary; it is separate from the replication slot, which maintains the stream's position.

## About Debezium

A Debezium connector is a distributed, log-based Change Data Capture (CDC) component that taps into database transaction logs (such as MySQL binlogs, PostgreSQL Write-Ahead Logs, or Oracle LogMiner) to record row-level INSERT, UPDATE, and DELETE events in real time.

**Core Architecture & Deployment***

• Apache Kafka Connect: The standard deployment model, running connectors as plugins inside a Kafka Connect cluster to stream change events directly into Kafka topics.
• Debezium Server: A ready-to-use, standalone application that streams database changes directly to messaging or storage infrastructures like Amazon Kinesis, Google Cloud Pub/Sub, or Apache Pulsar without needing a full Kafka setup.
• Debezium Engine: An embedded Java library that allows custom applications to run CDC logic directly inside their own processes.
