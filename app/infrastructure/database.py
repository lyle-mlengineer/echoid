from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def build_database(database_url: str="postgresql+psycopg://postgres:lyle@db:5432/echoid"):
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, connect_args=connect_args, pool_pre_ping=True)
    return engine, sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def add_missing_columns(engine, table: str, columns: dict[str, str]) -> None:
    # create_all() only brings new tables forward, so columns added to an
    # already-populated table have to be widened in place.
    inspector = inspect(engine)
    if table not in inspector.get_table_names():
        return
    present = {column["name"] for column in inspector.get_columns(table)}
    for name, definition in columns.items():
        if name in present:
            continue
        with engine.begin() as connection:
            connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {definition}"))

