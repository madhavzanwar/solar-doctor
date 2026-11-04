"""Every API router must be registered with an explicit access policy.

A router missing from `_ROUTER_POLICIES` is never mounted, and one mounted any
other way would get no role check and no project scoping in users mode. This
guard makes adding a router without deciding its policy fail CI instead of
silently shipping an unprotected endpoint.
"""
import pkgutil

import axalon.api.routers as routers_pkg
from axalon.api import app as app_module


def test_every_router_module_is_registered_with_a_policy():
    router_modules = {
        name for _, name, is_pkg in pkgutil.iter_modules(routers_pkg.__path__) if not is_pkg
    }
    registered = {module.__name__.rsplit(".", 1)[-1] for module, _ in app_module._ROUTER_POLICIES}

    assert router_modules - registered == set(), "router without an access policy"


def test_only_explicitly_public_routers_skip_the_policy():
    unguarded = {
        module.__name__.rsplit(".", 1)[-1]
        for module, policy in app_module._ROUTER_POLICIES
        if policy is None
    }

    # health is public; auth handles access per endpoint (login must be reachable).
    assert unguarded == {"health", "auth"}
