import os


class Settings:
    kafka_bootstrap = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
    group_id = "datagov-lineage"
    topic_prefix = "db_test.public."
    tables = [
        "categories", "customers", "employee_territories", "employees",
        "order_details", "orders", "products", "region", "shippers",
        "suppliers", "territories", "us_states",
    ]
    datahub_gms = os.getenv("DATAHUB_GMS", "http://localhost:8080")
    datahub_token = os.getenv("DATAHUB_TOKEN")  # None for local quickstart
    db = dict(host="0.0.0.0", port=5432,
              dbname="northwind",
              user="debezium_user",
              password=os.getenv("DB_PASSWORD", "debezium")
              )
    db_platform = "postgres"
    env = "PROD"

    @property
    def topics(self):
        return [self.topic_prefix + t for t in self.tables]


settings = Settings()
