from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from governance.routes.database import database_router

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])
# allow_origins will be set to frontend url ofc

# Check if settings.db_database exists first


@app.get("/")
def root():
    return {
        "title": "Datalang",
        "message": "Yo ma data addicts. Governance time"
    }


app.include_router(database_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000
    )
