"""WebSocket handlers for real-time statement status updates."""
import json
import asyncio
from typing import Dict, Set
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.database import get_db
from db.models import Statement

ws_router = APIRouter(prefix="/v1/ws", tags=["websocket"])


class ConnectionManager:
    """Manages WebSocket connections per statement."""

    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}

    async def connect(self, statement_id: str, websocket: WebSocket):
        """Accept connection and store it."""
        await websocket.accept()
        if statement_id not in self.active_connections:
            self.active_connections[statement_id] = set()
        self.active_connections[statement_id].add(websocket)

    def disconnect(self, statement_id: str, websocket: WebSocket):
        """Remove connection from tracking."""
        if statement_id in self.active_connections:
            self.active_connections[statement_id].discard(websocket)
            if not self.active_connections[statement_id]:
                del self.active_connections[statement_id]

    async def broadcast(self, statement_id: str, data: dict):
        """Broadcast message to all connections for a statement."""
        if statement_id not in self.active_connections:
            return
        
        disconnected = set()
        for connection in self.active_connections[statement_id]:
            try:
                await connection.send_json(data)
            except Exception:
                disconnected.add(connection)
        
        for connection in disconnected:
            self.disconnect(statement_id, connection)


manager = ConnectionManager()


@ws_router.websocket("/statements/{statement_id}")
async def statement_ws(statement_id: str, websocket: WebSocket, db: AsyncSession = Depends(get_db)):
    """WebSocket endpoint for real-time statement status updates."""
    await manager.connect(statement_id, websocket)
    
    try:
        # Send current status immediately
        stmt = await db.get(Statement, statement_id)
        if stmt:
            await websocket.send_json({
                "type": "status",
                "status": stmt.status,
                "statement_id": statement_id,
                "error": stmt.error_message,
            })
        
        # Listen for client messages with timeout
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_json(), timeout=30.0)
                
                if data.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
            except asyncio.TimeoutError:
                # Server-initiated ping
                await websocket.send_json({"type": "ping"})
            
    except WebSocketDisconnect:
        manager.disconnect(statement_id, websocket)
    except Exception as e:
        print(f"WebSocket error for statement {statement_id}: {e}")
        manager.disconnect(statement_id, websocket)


async def notify_status_change(statement_id: str, new_status: str):
    """Broadcast a status change to all watchers."""
    await manager.broadcast(statement_id, {
        "type": "status",
        "status": new_status,
        "statement_id": statement_id,
    })


async def notify_ocr_progress(
    statement_id: str,
    page_current: int,
    page_total: int,
    engine: str,
    confidence_so_far: float | None = None,
):
    """Broadcast OCR progress (page-by-page) to all watchers."""
    await manager.broadcast(statement_id, {
        "type": "ocr_progress",
        "statement_id": statement_id,
        "page_current": page_current,
        "page_total": page_total,
        "engine": engine,
        "confidence_so_far": confidence_so_far,
    })
