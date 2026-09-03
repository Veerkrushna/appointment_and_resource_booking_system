from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

# The engine manages the actual connection pool to PostgreSQL.
# It does NOT open a connection immediately — connections are
# created lazily, on first use, and reused from the pool.
engine = create_engine(settings.database_url)

# SessionLocal is a *factory* for creating new Session objects.
# We configure it once here; later code calls SessionLocal() to
# get an actual session to work with.
#
# autocommit=False and autoflush=False are the conventional FastAPI
# defaults: we want to control exactly when writes are flushed/committed,
# not have SQLAlchemy do it implicitly mid-query.
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


# Base is the declarative base class. Every ORM model (Service,
# Resource, Booking, etc.) will inherit from this class. SQLAlchemy
# uses it to collect metadata about all our tables in one place,
# which is what Alembic (migrations) will later read from.
class Base(DeclarativeBase):
    pass


def get_db():
    """
    FastAPI dependency that provides a database session for a single
    request, and guarantees it's closed afterward — even if the
    request raises an exception.

    This will be used in routes like:

        @app.get("/services")
        def list_services(db: Session = Depends(get_db)):
            ...

    The 'yield' pattern is what lets FastAPI run cleanup (db.close())
    after the route function finishes, instead of us remembering to
    close it manually every time.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()