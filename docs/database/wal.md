## Core WAL & CDC Settings

• wal_level = logical
	• What it does: Increases WAL information to include the data necessary to reconstruct row-level inserts, updates, and deletes. (Default is replica). Requires a database restart.
• max_wal_size and min_wal_size
	• What it does: Controls the lower and upper bounds for the size of the WAL on disk before automatic checkpoints trigger recycling or removal. Set max_wal_size high enough (e.g., 10GB or higher) to prevent running out of space during high-throughput spikes.
• wal_keep_size
	• What it does: Minimum size of past WAL files kept in the pg_wal directory for standbys or slow-moving readers (e.g., 1GB to 4GB).
• max_slot_wal_keep_size
	• What it does: Critical for CDC. Limits the maximum size of WAL files that logical replication slots are allowed to retain. If a CDC consumer lags beyond this limit, Postgres will drop the WAL data to prevent disk exhaustion, invalidating the slot rather than crashing the disk.

## Replication Slots & Wenders

• max_replication_slots
	• What it does: Sets the maximum number of replication slots (physical or logical) that can be supported at the same time. Must be greater than or equal to the number of active CDC/logical subscriptions plus a safety buffer. (Default is 10).
• max_wal_senders
	• What it does: Defines the maximum number of concurrent WAL sender processes (replicas and logical decoders combined). Must be set higher than max_replication_slots + the number of physical standbys. (Default is 10).
• wal_sender_timeout
	• What it does: Timeout to kill inactive replication connections (default is 60s). Increase this if your CDC client experiences network hiccups or long batch windows.
• idle_replication_slot_timeout
	• What it does: Automatically drops or flags idle logical slots if they sit inactive past a set duration (Postgres 17+).

## Checkpoint & Performance Tuning

• checkpoint_completion_target
	• What it does: Spreads out checkpoint I/O over a larger fraction of the checkpoint interval (recommended: 0.9 to smooth out I/O spikes during CDC ingestion).
• wal_buffers
	• What it does: Amount of shared memory used for WAL data that has not yet been written to disk (default -1 auto-tunes based on shared_buffers). Raising this prevents write stalls under heavy CDC loads.
• track_commit_timestamp = on
	• What it does: Records the commit time of transactions. Enable this if your downstream CDC tool (such as Debezium) requires precise transaction commit timestamps.
