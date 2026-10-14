## Architecture

CDC from PostgreSQL -> Debezium Connector -> Kafka Connect -> Python backend -> DataHub -> Frontend

1. Enable logical replication and create a publication in YugabyteDB/PostgreSQL Also create a dedicated user for Debezium.
2. Start Kafka and Kraft
3. Start Kafka Connect with Debezium connector plugins
4. Register connector through POST /connectors router 
