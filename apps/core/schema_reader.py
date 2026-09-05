import threading
from sqlalchemy import create_engine, MetaData, inspect
from pathlib import Path

class SchemaReader:
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(SchemaReader, cls).__new__(cls)
        return cls._instance
        
    def __init__(self, db_uri=None):
        if not hasattr(self, 'initialized'):
            if db_uri is None:
                # Default to the local sample.db relative to this file
                db_path = Path(__file__).parent.parent / "data" / "sample.db"
                db_uri = f"sqlite:///{db_path}"
                
            self.db_uri = db_uri
            self.engine = create_engine(self.db_uri)
            self.metadata = MetaData()
            self._schema_snapshot = None
            self.initialized = True
            
    def refresh_schema(self) -> str:
        """Reads the database and generates a text representation of the schema."""
        self.metadata.clear()
        self.metadata.reflect(bind=self.engine)
        inspector = inspect(self.engine)
        
        lines = []
        for table_name in inspector.get_table_names():
            columns = inspector.get_columns(table_name)
            col_strs = [f"{col['name']} ({col['type']})" for col in columns]
            
            lines.append(f"Table: {table_name}")
            lines.append(f"Columns: {', '.join(col_strs)}")
            
            fks = inspector.get_foreign_keys(table_name)
            fk_strs = []
            for fk in fks:
                for constrained, referred in zip(fk['constrained_columns'], fk['referred_columns']):
                    fk_strs.append(f"{constrained} -> {fk['referred_table']}.{referred}")
            if fk_strs:
                lines.append(f"Foreign Keys: {', '.join(fk_strs)}")
            
            lines.append("")
            
        self._schema_snapshot = "\n".join(lines).strip()
        return self._schema_snapshot
        
    def get_schema(self) -> str:
        """Returns the in-memory schema snapshot, fetching it if not yet loaded."""
        if self._schema_snapshot is None:
            return self.refresh_schema()
        return self._schema_snapshot
