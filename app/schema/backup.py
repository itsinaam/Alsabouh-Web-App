from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class BackupHistoryItem(BaseModel):
    id: int
    filename: str
    table_count: int
    created_at: datetime
    download_url: Optional[str] = None
    created_by_user_id: Optional[int] = None
    created_by_name: Optional[str] = None


class BackupHistoryResponse(BaseModel):
    total: int
    skip: int
    limit: int
    items: List[BackupHistoryItem]