#Configuration management for QueueCTL

from .database import Database


class Config:    
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_BACKOFF_BASE = 2
    
    def __init__(self, db: Database):
        self.db = db
    
    def get_max_retries(self) -> int:
        value = self.db.get_config("max_retries")
        if value:
            try:
                return int(value)
            except ValueError:
                pass
        return self.DEFAULT_MAX_RETRIES
    
    def set_max_retries(self, value: int) -> bool:
        return self.db.set_config("max_retries", str(value))
    
    def get_backoff_base(self) -> int:
        value = self.db.get_config("backoff_base")
        if value:
            try:
                return int(value)
            except ValueError:
                pass
        return self.DEFAULT_BACKOFF_BASE
    
    def set_backoff_base(self, value: int) -> bool:
        return self.db.set_config("backoff_base", str(value))
    
    def get_all(self) -> dict:
        return {
            "max_retries": self.get_max_retries(),
            "backoff_base": self.get_backoff_base()
        }