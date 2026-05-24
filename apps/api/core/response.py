"""
Standard API response envelope as defined in PRD section 9.1.
"""
from datetime import datetime, timezone
from typing import Any, Optional
from pydantic import BaseModel
import uuid


class ApiResponse(BaseModel):
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    meta: dict = {}

    @classmethod
    def ok(cls, data: Any = None, **kwargs) -> "ApiResponse":
        return cls(
            success=True,
            data=data,
            meta={
                "request_id": str(uuid.uuid4()),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                **kwargs,
            },
        )

    @classmethod
    def fail(cls, error: str, **kwargs) -> "ApiResponse":
        return cls(
            success=False,
            error=error,
            meta={
                "request_id": str(uuid.uuid4()),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                **kwargs,
            },
        )
