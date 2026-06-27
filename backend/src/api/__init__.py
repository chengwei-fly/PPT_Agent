"""API router package — exports all routers for main.py to register.

Uses lazy imports to avoid circular dependency issues during testing.
"""


def __getattr__(name: str):
    """Lazy import routers to avoid circular dependencies."""
    router_map = {
        "assets_router": "src.api.assets",
        "credentials_router": "src.api.credentials",
        "data_lifecycle_router": "src.api.data_lifecycle",
        "drafts_router": "src.api.drafts",
        "generations_router": "src.api.generations",
        "ops_router": "src.api.ops",
        "preferences_router": "src.api.preferences",
        "samples_router": "src.api.samples",
        "security_router": "src.api.security",
        "traces_router": "src.api.traces",
        "ws_router": "src.api.ws",
    }
    if name in router_map:
        import importlib

        module = importlib.import_module(router_map[name])
        return module.router
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "assets_router",
    "credentials_router",
    "data_lifecycle_router",
    "drafts_router",
    "generations_router",
    "ops_router",
    "preferences_router",
    "samples_router",
    "security_router",
    "traces_router",
    "ws_router",
]
