"""Utility modules for the arbitrage bot."""

from backend.utils.ssl_patch import apply_ssl_patch, get_ssl_context

__all__ = ['apply_ssl_patch', 'get_ssl_context']
