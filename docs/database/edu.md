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

### Transaction block
A database transaction block is a sequence of SQL operations grouped together using explicit boundary commands (such as BEGIN and COMMIT or ROLLBACK) so that they execute as a single, indivisible unit of work.

Key Characteristics

- ACID Compliance: Ensures Atomicity, Consistency, Isolation, and Durability. Either all operations inside the block succeed and are permanently saved (COMMIT), or any failure causes the entire set of changes to be undone (ROLLBACK).
- Implicit vs. Explicit Blocks: Many relational databases (like PostgreSQL or MySQL) wrap individual SQL statements in an implicit transaction if you do not explicitly open one. An explicit block starts with a command like BEGIN or BEGIN WORK and ends with COMMIT or ROLLBACK.

Transaction Blocking (Concurrency Conflicts)

"Blocking" occurs when one transaction holds a lock on a database resource (such as a row, page, or table) and a second transaction requests a conflicting lock.

- Shared Locks vs. Exclusive Locks: Read operations typically acquire shared locks, while write operations (INSERT, UPDATE, DELETE) acquire exclusive locks. An exclusive lock prevents other transactions from reading or modifying that data until the first transaction commits or rolls back.
- Performance Impact: Long-running transaction blocks extend the lifespan of locks, causing subsequent queries to queue or time out (and potentially leading to deadlocks if two transactions wait on each other).
--Best Practice: Keep transaction blocks as short as possible, confine them strictly to database operations, and avoid user interaction or external API calls inside an open transaction.

### DDL and DML

In database management systems, DDL (Data Definition Language) handles the blueprint and architecture of the database, while DML (Data Manipulation Language) handles the actual information stored inside that structure.

Think of DDL as building the house (rooms, walls, closets) and DML as managing the furniture inside it (adding, changing, or throwing things away).

**Key Differences**

| Feature                    | DDL (Data Definition Language)                                                                  | DML (Data Manipulation Language)                             |

| :------------------------- | :---------------------------------------------------------------------------------------------- | :----------------------------------------------------------- |

| **Primary Purpose**        | Defines, alters, and manages the database structure or schema.                                  | Manages and manipulates the data records within the tables.  |

| **Core Commands**          | `CREATE`, `ALTER`, `DROP`, `TRUNCATE`, `RENAME`                                                 | `SELECT`, `INSERT`, `UPDATE`, `DELETE`, `MERGE`              |

| **Target Scope**           | Entire database objects (tables, views, indexes, schemas).                                      | Individual rows or records inside a table.                   |

| **Transactional Rollback** | Cannot be rolled back in most systems because it auto-commits (PostgreSQL is a notable exception). | Can be rolled back using transaction controls like `ROLLBACK`.|

| **Filtering (`WHERE`)**    | No (acts globally on the structure).                                                           | Yes (used to isolate specific rows).                         |

| **Typical Users**          | Database Administrators (DBAs) and system architects.                                           | Software developers, data analysts, and end-user applications.|
