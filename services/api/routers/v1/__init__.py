"""The public, versioned API (``/api/v1``).

Every route here is reachable with an access key (``Authorization: Bearer
bgr_...``) as well as with a browser session, and must declare the scopes
it needs through ``routers.v1._deps.require_scope`` (or
``v1_project_access``). ``assert_v1_routes_scoped`` enforces that at
startup. Routes are added by the v1 API issue; this package currently only
holds the shared dependencies.
"""
