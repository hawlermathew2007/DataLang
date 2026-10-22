from lineage.core.datahub_emitter import DataHubPublisher

p = DataHubPublisher()   # fails here if GMS is unreachable
p.publish_db_table("orders", [("order_id", "smallint"), ("freight", "real")])
p.publish_topic("db_test.public.orders", "orders", {"order_id": 1, "freight": 3.5})
print("emitted")
