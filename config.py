import os
from typing import List
import json

class Config:
    def __init__(self):
        # Get from Replit Secrets (Tools -> Secrets)
        self.BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
        self.ADMIN_IDS = self._parse_admin_ids(os.environ.get("ADMIN_IDS", ""))
        self.REPLIT_DB_URL = os.environ.get("REPLIT_DB_URL", "")
        
        # Bot settings
        self.MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
        self.CONCURRENT_DOWNLOADS = 3
        self.REQUEST_TIMEOUT = 30
        self.TEMP_DIR = "/tmp/snap_downloads"
        
        # Snapchat settings
        self.USER_AGENTS = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15",
            "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36",
        ]
        
        # Rate limiting
        self.REQUESTS_PER_MINUTE = 20
        self.BURST_SIZE = 5
        
        # Create temp directory
        os.makedirs(self.TEMP_DIR, exist_ok=True)
    
    def _parse_admin_ids(self, ids_str: str) -> List[int]:
        """Parse admin IDs from comma-separated string."""
        if not ids_str:
            return []
        return [int(id.strip()) for id in ids_str.split(",") if id.strip().isdigit()]
    
    def validate(self) -> bool:
        """Validate configuration."""
        if not self.BOT_TOKEN:
            print("ERROR: BOT_TOKEN not set in Replit Secrets!")
            return False
        if not self.ADMIN_IDS:
            print("WARNING: No ADMIN_IDS set. Bot will accept commands from anyone.")
        return True
    
    def get_replit_db(self):
        """Get Replit Database connection."""
        try:
            from replit import db
            return db
        except ImportError:
            return None

config = Config()