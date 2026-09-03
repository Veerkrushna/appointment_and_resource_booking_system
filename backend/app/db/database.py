from sqlalchemy import create_engine, text

from app.core.config import settings


# The engine manages connections between our application and PostgreSQL.
engine = create_engine(settings.database_url)


# Temporary connection test.
with engine.connect() as connection:
    result = connection.execute(text("SELECT 1"))
    print(result.scalar())