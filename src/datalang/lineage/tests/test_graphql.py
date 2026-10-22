import json
import datahub_reader as dh
from datahub_emitter import DataHubPublisher as P


print(json.dumps(dh.get_dataset(P.topic_urn('yb_test.public.orders')), indent=2)
