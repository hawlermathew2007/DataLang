## Database Education
### CDC

Change Data Capture (CDC) in databases is a software design pattern that tracks and captures row-level modifications—specifically inserts, updates, and deletes—in a source database and delivers them to downstream systems in near real time.

### WAL

PostgreSQL Write-Ahead Logging (WAL) is a core architectural feature that records all database modifications to a sequential log on diPostgreSQL Write-Ahead Logging (WAL) is a core architectural feature that records all database modifications to a sequential log on disk before applying them to the actual table and index filessk before applying them to the actual table and index files

### Logical Replication

Logical replication is a method of replicating database data at the object/row level—rather than a byte-for-byte disk copy—using a publish-and-subscribe model. It streams data changes in commit order, allowing selective replication of specific tables, rows, or columns across different database versions or platforms

- Publisher Node: Hosts the source database where changes are captured from the Write-Ahead Log (WAL) and grouped into publications.
- Subscriber Node: Connects to the publisher, performs an initial table snapshot copy, and then continuously streams and applies incoming row-level changes (INSERT, UPDATE, DELETE).
- Replication Slots: Track the progress of each subscriber to ensure WAL segments are retained until processed.

![logical replication](https://www.postgresql.fastware.com/blog/inside-logical-replication-in-postgresql)

![logical repli workflow](https://www.postgresql.fastware.com/blog/logical-replication-of-tables-in-schema-in-postgresql-15)

**Why enable logical replication?**

Debezium needs a way to decode committed changes from that log into row-level events. By default, the WAL contains low-level binary data about how disk blocks change. Setting wal_level = logical forces PostgreSQL to inject the metadata necessary for logical decoding. This extra metadata allows a decoding plug-in (like pgoutput) to extract explicit row modifications—such as INSERT, UPDATE, and DELETE payloads—along with "before" and "after" values.

Debezium relies on logical replication slots. A replication slot acts like a persistent bookmark on the database server.

- It tracks Debezium's current position via a Log Sequence Number (LSN).
- It tells PostgreSQL not to delete or overwrite WAL segments until Debezium has successfully read and acknowledged them. This ensures zero data loss even if the Debezium connector goes offline for a period of time.

Setting & Why it matters
wal_level = logical     :	Makes the WAL contain information needed for logical decoding.
max_replication_slots   :	Allows persistent positions for CDC consumers to be maintained.
max_wal_senders         :	Allows replication connections to stream WAL data.

Without wal_level = logical, PostgreSQL only records the minimum binary data needed for crash recovery or physical cluster backups.

### Publication

A PostgreSQL publication defines which tables and operations are exposed through logical replication.

**Why create a publication?**

Debezium's PostgreSQL connector uses the pgoutput plugin to consume changes from a publication. The publication acts as the table-selection boundary; it is separate from the replication slot, which maintains the stream's position.
