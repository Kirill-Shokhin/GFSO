"""SQLite StoragePort — stub."""
from gfso.core.types import StoragePort


class SqliteStorage(StoragePort):
    def __init__(self, db_path: str = "gfso.db"):
        raise NotImplementedError("SQLite storage not yet implemented")
