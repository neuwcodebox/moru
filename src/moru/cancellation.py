"""Cooperative cancellation shared by generation and external lookups."""

from threading import Event

from moru.errors import MoruError


def check_cancelled(cancelled: Event) -> None:
    if cancelled.is_set():
        raise MoruError("GENERATION_CANCELLED")
