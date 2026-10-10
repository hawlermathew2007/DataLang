"""Set up DB: Create a new table for data auth"""
import psycopg2
from psycopg2.extras import RealDictCursor

from backend.core.config import DB_INFO


def get_db_connection():
    return psycopg2.connect(
        host=DB_INFO["host"],
        port=DB_INFO["port"],
        dbname=DB_INFO["dbName"],
        user=DB_INFO["dbUser"],
        password=DB_INFO["dbPassword"],
        cursor_factory=RealDictCursor,
    )
