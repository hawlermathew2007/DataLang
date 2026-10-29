DataHub’s metadata model. Every entity is identified by a URN, and you attach aspects to it (schema, properties, lineage) using MetadataChangeProposalWrapper and an emitter.

DataHub lineage. Dataset-to-dataset lineage is stored in the UpstreamLineage aspect on the downstream dataset [3]. The target datasets must already exist in DataHub before you add lineage [2].

Reading data back. DataHub’s GraphQL API at /api/graphql supports search, entity reads and lineage traversal [6]. The official React app uses queries of the form lineage(input: {direction: UPSTREAM, ...}) [7].

An emitter in Acryl DataHub is a client-side library or component used to push metadata events (such as Metadata Change Proposals or MCE/MCP) programmatically to the DataHub Generalized Metadata Service (GMS) or message bus.

Main Types of Emitters

• REST Emitter: A blocking or non-blocking HTTP wrapper (requests in Python or Apache HttpClient in Java) that sends metadata directly to the DataHub GMS REST API over port 8080. It provides immediate persistence acknowledgement.
• Kafka Emitter: A non-blocking wrapper (confluent-kafka) that serializes metadata events using Avro and pushes them to a Kafka message bus. It decouples your metadata producer from the uptime of the DataHub server, which is useful for high-throughput or unreliable network conditions.

The Generalized Metadata Service (GMS) is the core microservice layer in Apache DataHub that manages, serves, and mutates metadata for entities onboarded to the Generalized Metadata Architecture (GMA).

The Generalized Metadata Architecture (GMA) is the backend foundation of Acryl DataHub (originally created at LinkedIn) that standardizes how metadata is modeled, stored, served, and synced across distributed systems.

 DataHub uses metadata to build a searchable library across scattered databases, data lakes, and business intelligence (BI) tools so users can find the right datasets instead of guessing.

To Map Relationships (The Metadata Graph)

• Lineage & Dependencies: DataHub stores metadata as a graph (with entities as nodes and relationships as edges).
• Impact Analysis: It needs metadata to track upstream and downstream dependencies—showing which pipeline feeds a table, which dashboard relies on that table, and what will break if an engineer changes a schema.

A DataHub publisher refers to a role, tool, or component responsible for uploading, sharing, or streaming data into a data hub platform.
