"""FastAPI dependencies shared across routers."""

from __future__ import annotations

from fastapi import Request

from app.services.message_broker import MessageBroker


def get_message_broker(request: Request) -> MessageBroker:
    return request.app.state.message_broker
