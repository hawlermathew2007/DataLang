from datahub.ingestion.graph.client import DatahubGraph, DataHubGraphConfig

from lineage.schemas import datahub
from lineage.core.config import settings


def fetch_all_urns(datahub_client):
    print("Fetching all URNs from DataHub...")
    urns = list(datahub.client.search.get_urns(query="*"))
    print(f"Total URNs returned: {len(urns)}")
    for urn in urns:
        print(urn)


def print_metadata_format(urn):
    # Initialize the graph client (adjust gms/server URL as needed)
    graph = DatahubGraph(DataHubGraphConfig(server=settings.datahub_gms))

    # Fetch a specific aspect for a given URN
    aspect_name = "datasetProperties"

    aspect_data = graph.get_aspect_v2(
        entity_urn=urn,
        aspect=aspect_name,
    )

    print(aspect_data)


if __name__ == "__main__":
    urn = "urn:li:dataset:(urn:li:dataset:datahub,northwind.public.orders,PROD)"
    print_metadata_format(urn)
