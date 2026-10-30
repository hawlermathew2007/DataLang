from fastapi import APIRouter, Request

cdc_router = APIRouter(prefix="/api/v1/cdc", tags=["connector"])


@cdc_router.post("/register")
def register_connector(request: Request):
    pass


@cdc_router.post("/register")
def connect_kafka_db(request: Request):
    pass
# delete
