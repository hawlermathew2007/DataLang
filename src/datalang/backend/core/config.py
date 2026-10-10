import os
from dotenv import load_dotenv

load_dotenv()

DB_INFO = {
    'host': '127.0.0.1',
    'port': '5433',
    'dbName': os.getenv("DB_NAME"),
    'dbUser': os.getenv("DB_USER"),
    'dbPassword': os.getenv("DB_PWD"),
    'sslMode': '',
    'sslRootCert': ''  # Validate needed
}

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")
ACCESS_TOKEN_EXPIRE_MINUTES = os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES")
