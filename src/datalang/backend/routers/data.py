from fastapi import APIRouter

data_router = APIRouter(
    prefix="/data",
    tags=["Data"],
)


@data_router.get("/")
def get_data():
    pass
