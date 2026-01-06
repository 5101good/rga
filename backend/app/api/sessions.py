"""Session management API routes."""

from datetime import datetime
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.api.auth import get_current_user
from app.core.config import settings
from app.core.logging import get_logger
from app.models import SessionCreate, SessionResponse, SessionStatus, UserInfo
from app.services.agentbay import get_agentbay_service, AgentBaySession
from app.services.database import get_database_service

logger = get_logger("sessions")

router = APIRouter()


def _dict_to_session_response(data: dict) -> SessionResponse:
    """Convert database dict to SessionResponse."""
    return SessionResponse(
        id=UUID(data["id"]),
        user_id=data["user_id"],
        agentbay_session_id=data.get("agentbay_session_id"),
        resource_url=data.get("resource_url"),
        device_id=data.get("device_id"),
        status=SessionStatus(data.get("status", "creating")),
        name=data.get("name"),
        agent_type=data.get("agent_type", "glm"),
        created_at=datetime.fromisoformat(data["created_at"].replace("Z", "+00:00")) if isinstance(data["created_at"], str) else data["created_at"],
        updated_at=datetime.fromisoformat(data["updated_at"].replace("Z", "+00:00")) if isinstance(data["updated_at"], str) else data["updated_at"],
    )


@router.post("", response_model=SessionResponse)
async def create_session(
    request: SessionCreate,

    current_user: UserInfo = Depends(get_current_user),
):
    """
    Create a new phone session with AgentBay cloud phone.

    This will:
    1. Check session limits (daily and active)
    2. Create a session record in database
    3. Create an AgentBay cloud phone session
    4. Connect via ADB
    5. Return session details including resource_url for phone display
    """
    db = get_database_service()

    # 1. Check daily session creation limit
    daily_count = await db.count_user_sessions_today(current_user.id)
    if daily_count >= settings.max_sessions_per_day:
        raise HTTPException(
            status_code=403,
            detail={
                "type": "daily_limit_exceeded",
                "message": f"您今天已创建 {daily_count} 个会话，已达到每日上限（{settings.max_sessions_per_day}个）",
                "current": daily_count,
                "limit": settings.max_sessions_per_day,
                "reset_time": "明天 00:00 重置"
            }
        )

    # 2. Check active sessions limit
    active_count = await db.count_active_sessions(current_user.id)
    if active_count >= settings.max_active_sessions:
        raise HTTPException(
            status_code=403,
            detail={
                "type": "active_limit_exceeded",
                "message": f"您当前有 {active_count} 个活跃会话，已达到上限（{settings.max_active_sessions}个）",
                "current": active_count,
                "limit": settings.max_active_sessions,
                "suggestion": "请先关闭一些不需要的会话"
            }
        )

    # Create session in database first
    session_data = await db.create_session(
        user_id=current_user.id,
        name=request.name,
        status="creating",
        agent_type=request.agent_type,
    )

    session_id = session_data["id"]

    try:
        # Create AgentBay session
        agentbay_service = get_agentbay_service()
        ab_session: AgentBaySession = await agentbay_service.create_session()

        # Update session with AgentBay details
        updated = await db.update_session(
            session_id=session_id,
            user_id=current_user.id,
            agentbay_session_id=ab_session.session_id,
            resource_url=ab_session.resource_url,
            device_id=ab_session.device_id,
            status="active",
        )

        if updated:
            return _dict_to_session_response(updated)

        # Fallback: re-fetch
        session_data = await db.get_session(session_id, current_user.id)
        if not session_data:
            raise HTTPException(status_code=500, detail="Failed to load created session")
        return _dict_to_session_response(session_data)

    except Exception as e:
        # Update status to error
        await db.update_session(
            session_id=session_id,
            user_id=current_user.id,
            status="error",
        )

        raise HTTPException(
            status_code=500,
            detail=f"Failed to create session: {str(e)}",
        )


@router.get("", response_model=List[SessionResponse])
async def list_sessions(
    current_user: UserInfo = Depends(get_current_user),
):
    """List all sessions for current user."""
    db = get_database_service()
    sessions = await db.list_sessions(current_user.id)
    return [_dict_to_session_response(s) for s in sessions]


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: UUID,
    current_user: UserInfo = Depends(get_current_user),
):
    """Get session by ID."""
    db = get_database_service()
    session = await db.get_session(str(session_id), current_user.id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return _dict_to_session_response(session)


@router.get("/{session_id}/conversations")
async def get_conversations(
    session_id: UUID,
    current_user: UserInfo = Depends(get_current_user),
):
    """Get conversation history for a session."""
    db = get_database_service()

    # Verify session belongs to user
    session = await db.get_session(str(session_id), current_user.id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Get conversations
    conversations = await db.list_conversations(str(session_id))

    return {"conversations": conversations}


@router.delete("/{session_id}")
async def delete_session(
    session_id: UUID,
    current_user: UserInfo = Depends(get_current_user),
):
    """Delete/close a session."""
    db = get_database_service()
    session = await db.get_session(str(session_id), current_user.id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Close AgentBay session
    if session.get("agentbay_session_id"):
        try:
            agentbay_service = get_agentbay_service()
            await agentbay_service.close_session(session["agentbay_session_id"])
        except Exception as e:
            logger.warning(f"Failed to close AgentBay session: {e}")

    # Update status to closed
    await db.delete_session(str(session_id), current_user.id)

    return {"status": "deleted", "session_id": str(session_id)}
