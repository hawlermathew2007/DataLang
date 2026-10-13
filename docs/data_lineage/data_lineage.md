## Architecture

CDC from PostgreSQL -> Debezium Connector -> Kafka Connect -> Python backend -> DataHub -> Frontend

A publication in a database is a collection of tables or database objects grouped together for logical replication or data synchronization.

PostgreSQL Write-Ahead Logging (WAL) is a core architectural feature that records all database modifications to a sequential log on disk before applying them to the actual table and index files

1. Enable logical replication and create a publication in YugabyteDB/PostgreSQL Also create a dedicated user for Debezium.
2. Start Kafka and Kraft
3. Start Kafka Connect with Debezium connector plugins
4. Register connector through POST /connectors router 
