from __future__ import annotations


class CapabilityUnavailable(RuntimeError):
    code = "capability_unavailable"


class SnapshotMissing(RuntimeError):
    code = "snapshot_missing"


class UpstreamError(RuntimeError):
    code = "upstream_unavailable"
    status = 502


class UpstreamAuthFailed(UpstreamError):
    code = "upstream_auth_failed"


class UpstreamForbidden(UpstreamError):
    code = "upstream_forbidden"


class UpstreamRateLimited(UpstreamError):
    code = "upstream_rate_limited"
    status = 429


class UpstreamUnavailable(UpstreamError):
    code = "upstream_unavailable"


class PortalQuotaExceeded(RuntimeError):
    code = "portal_quota_exceeded"
