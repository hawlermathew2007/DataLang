from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.routers.register import register_router
from backend.routers.login import login_router
from backend.routers.users import user_router
from backend.routers.data import data_router

app = FastAPI()


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {
        "title": "Datalang",
        "message": "Yo ma data addicts."
    }


app.include_router(register_router)
app.include_router(login_router)
app.include_router(user_router)
app.include_router(data_router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000
    )
