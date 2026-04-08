"""
Incident scenario generator for the Incident Commander OpenEnv.

Each task (easy/medium/hard) defines a multi-phase incident scenario.
The agent progresses through phases by taking correct actions.

Each scenario returns:
  - phases: list of Observation data at each phase
  - ground_truth: the ideal actions and criteria for grading

Ground truth structure per phase:
  {
    "ideal_action": ActionType value,
    "ideal_target": target string or None,
    "acceptable_actions": list of (action_type, target) tuples that get partial credit,
    "communication_criteria": list of keywords expected in status updates,
    "phase_description": what's happening at this point
  }
"""

from __future__ import annotations

from app.models import Alert, IncidentContext, Observation, Severity, SystemMetrics


# ═══════════════════════════════════════════════════════════════════════════════
# TASK 1: EASY — Single service crash, clear cause
#
# Scenario: The web server crashed after a bad deploy. Logs clearly show an
# out-of-memory error caused by the latest deployment v2.3.1. Rolling back
# fixes everything.
#
# Phase 1: Alerts fire → agent should investigate
# Phase 2: Logs reveal the cause → agent should rollback
# Phase 3: Service recovering → agent should send status update
# Phase 4: Confirm resolution → agent should page on-call for post-mortem
# ═══════════════════════════════════════════════════════════════════════════════

def generate_easy() -> tuple[list[dict], list[dict]]:
    """Single service crash with obvious root cause."""

    context = IncidentContext(
        incident_id="INC-2024-0042",
        started_at="2024-03-15T03:12:00Z",
        affected_users=1200,
        revenue_impact_per_minute=50.0,
        recent_deploys=["v2.3.1 (web-server, 2h ago)", "v1.8.0 (search-service, 12h ago)"],
        on_call_engineer="Alex Chen",
    )

    # Phase 1: Alerts are firing, agent should investigate
    phase1_obs = {
        "alerts": [
            Alert(
                source="Datadog", service="web-server",
                message="HTTP 500 error rate exceeded 25% threshold — currently at 48%",
                severity=Severity.SEV2, timestamp="2024-03-15T03:12:00Z",
            ).model_dump(),
            Alert(
                source="PagerDuty", service="web-server",
                message="Service web-server health check failing on 3/5 instances",
                severity=Severity.SEV2, timestamp="2024-03-15T03:12:30Z",
            ).model_dump(),
        ],
        "metrics": SystemMetrics(
            error_rate_pct=48.0, latency_p99_ms=12500, cpu_usage_pct=92,
            memory_usage_pct=97, active_connections=340, requests_per_second=120,
        ).model_dump(),
        "context": context.model_dump(),
        "log_snippets": [],
        "actions_taken": [],
        "minutes_elapsed": 0,
        "task_description": (
            "You are the incident commander. The web server is throwing errors. "
            "Investigate the root cause, fix the issue, and communicate status to stakeholders. "
            "Available actions: investigate, restart_service, rollback_deploy, scale_up, "
            "page_team, status_update, mitigate, skip."
        ),
    }

    # Phase 2: After investigation, logs reveal OOM from bad deploy
    phase2_obs = {
        **phase1_obs,
        "log_snippets": [
            "[ERROR] 03:11:45 web-server-03: java.lang.OutOfMemoryError: Java heap space",
            "[ERROR] 03:11:46 web-server-01: Container killed by OOM killer (limit: 2Gi, used: 2.1Gi)",
            "[WARN]  03:11:40 web-server-03: Memory usage 98% — new image v2.3.1 loaded 340MB model into heap",
            "[INFO]  03:10:00 deploy-bot: Deployed v2.3.1 to web-server (all instances)",
            "[ERROR] 03:12:01 web-server-02: Connection pool exhausted — cannot serve requests",
        ],
        "actions_taken": ["Investigated web-server logs"],
        "minutes_elapsed": 3,
    }

    # Phase 3: After rollback, service recovering
    phase3_obs = {
        **phase1_obs,
        "alerts": [
            Alert(
                source="Datadog", service="web-server",
                message="HTTP 500 error rate dropping — currently at 8%",
                severity=Severity.SEV3, timestamp="2024-03-15T03:18:00Z",
            ).model_dump(),
        ],
        "metrics": SystemMetrics(
            error_rate_pct=8.0, latency_p99_ms=850, cpu_usage_pct=45,
            memory_usage_pct=62, active_connections=890, requests_per_second=450,
        ).model_dump(),
        "log_snippets": [
            "[INFO] 03:16:00 deploy-bot: Rolled back web-server to v2.3.0",
            "[INFO] 03:16:30 web-server-01: Health check passing",
            "[INFO] 03:17:00 web-server-02: Health check passing",
            "[INFO] 03:17:30 web-server-03: Health check passing",
        ],
        "actions_taken": ["Investigated web-server logs", "Rolled back to v2.3.0"],
        "minutes_elapsed": 6,
    }

    # Phase 4: Resolved, need post-mortem
    phase4_obs = {
        **phase1_obs,
        "alerts": [],
        "metrics": SystemMetrics(
            error_rate_pct=0.3, latency_p99_ms=220, cpu_usage_pct=35,
            memory_usage_pct=58, active_connections=1100, requests_per_second=520,
        ).model_dump(),
        "log_snippets": [
            "[INFO] 03:20:00 All web-server instances healthy",
            "[INFO] 03:20:00 Error rate back to baseline",
        ],
        "actions_taken": [
            "Investigated web-server logs",
            "Rolled back to v2.3.0",
            "Sent status update to stakeholders",
        ],
        "minutes_elapsed": 10,
    }

    phases = [phase1_obs, phase2_obs, phase3_obs, phase4_obs]

    ground_truth = [
        {
            "ideal_action": "investigate",
            "ideal_target": "web-server",
            "acceptable_actions": [
                ("investigate", "web-server"),
                ("investigate", None),
            ],
            "communication_criteria": [],
            "phase_description": "Alerts firing — should investigate before acting",
        },
        {
            "ideal_action": "rollback_deploy",
            "ideal_target": "web-server",
            "acceptable_actions": [
                ("rollback_deploy", "web-server"),
                ("rollback_deploy", "v2.3.1"),
                ("restart_service", "web-server"),  # partial credit — treats symptom not cause
            ],
            "communication_criteria": [],
            "phase_description": "Logs show OOM from v2.3.1 — should rollback",
        },
        {
            "ideal_action": "status_update",
            "ideal_target": None,
            "acceptable_actions": [
                ("status_update", None),
            ],
            "communication_criteria": [
                "rollback", "recovering", "web-server", "deploy", "memory",
                "investigating", "resolved", "fix", "v2.3.1",
            ],
            "phase_description": "Service recovering — should communicate to stakeholders",
        },
        {
            "ideal_action": "page_team",
            "ideal_target": "on-call",
            "acceptable_actions": [
                ("page_team", "on-call"),
                ("page_team", "backend"),
                ("page_team", "devops"),
                ("status_update", None),  # acceptable to send final update
            ],
            "communication_criteria": [
                "resolved", "post-mortem", "root cause", "memory", "deploy",
            ],
            "phase_description": "Resolved — should page for post-mortem",
        },
    ]

    return phases, ground_truth


# ═══════════════════════════════════════════════════════════════════════════════
# TASK 2: MEDIUM — Cascading failure from bad config change
#
# Scenario: A config change to the API gateway caused auth service to fail,
# which cascaded to payment service. Agent must trace the chain, fix root cause
# (not just symptoms), coordinate multiple teams.
#
# 6 phases of increasing complexity.
# ═══════════════════════════════════════════════════════════════════════════════

def generate_medium() -> tuple[list[dict], list[dict]]:
    """Cascading failure across multiple services."""

    context = IncidentContext(
        incident_id="INC-2024-0089",
        started_at="2024-03-20T14:30:00Z",
        affected_users=15000,
        revenue_impact_per_minute=500.0,
        recent_deploys=[
            "api-gateway config update (45min ago)",
            "v3.1.0 (payment-service, 6h ago)",
            "v2.0.2 (auth-service, 2d ago)",
        ],
        on_call_engineer="Jordan Lee",
    )

    # Phase 1: Multiple alerts, confusing — should investigate
    phase1_obs = {
        "alerts": [
            Alert(
                source="Datadog", service="payment-service",
                message="Payment processing failures at 72% — transactions timing out",
                severity=Severity.SEV1, timestamp="2024-03-20T14:30:00Z",
            ).model_dump(),
            Alert(
                source="Datadog", service="auth-service",
                message="Auth token validation latency >5s — upstream timeout",
                severity=Severity.SEV1, timestamp="2024-03-20T14:29:00Z",
            ).model_dump(),
            Alert(
                source="CloudWatch", service="api-gateway",
                message="Connection pool utilization at 100% — new connections rejected",
                severity=Severity.SEV2, timestamp="2024-03-20T14:28:00Z",
            ).model_dump(),
            Alert(
                source="PagerDuty", service="payment-service",
                message="Customer-facing: checkout page returning 503",
                severity=Severity.SEV1, timestamp="2024-03-20T14:31:00Z",
            ).model_dump(),
        ],
        "metrics": SystemMetrics(
            error_rate_pct=72.0, latency_p99_ms=28000, cpu_usage_pct=88,
            memory_usage_pct=76, active_connections=50, requests_per_second=45,
        ).model_dump(),
        "context": context.model_dump(),
        "log_snippets": [],
        "actions_taken": [],
        "minutes_elapsed": 0,
        "task_description": (
            "CRITICAL INCIDENT: Multiple services are failing simultaneously. "
            "Payment processing is down, auth is slow, API gateway is saturated. "
            "You must find the root cause (not just treat symptoms), fix it, "
            "coordinate with the right teams, and keep stakeholders informed. "
            "Available actions: investigate, restart_service, rollback_deploy, "
            "scale_up, page_team, status_update, mitigate, skip."
        ),
    }

    # Phase 2: After investigating api-gateway, logs reveal config change broke connection routing
    phase2_obs = {
        **phase1_obs,
        "log_snippets": [
            "[ERROR] 14:28:15 api-gateway: TLS handshake failed to auth-service — certificate mismatch",
            "[WARN]  14:28:00 api-gateway: Config reload applied — new TLS cert bundle loaded",
            "[ERROR] 14:28:20 api-gateway: Falling back to retry loop for auth-service (attempt 3/3)",
            "[ERROR] 14:29:00 auth-service: Rejecting connections — invalid client certificate from api-gateway",
            "[INFO]  14:27:45 config-bot: Applied config change #4521 to api-gateway: updated TLS certificates",
        ],
        "actions_taken": ["Investigated api-gateway logs"],
        "minutes_elapsed": 4,
    }

    # Phase 3: Should rollback the config change
    phase3_obs = {
        **phase1_obs,
        "log_snippets": [
            "[ERROR] 14:28:15 api-gateway: TLS handshake failed to auth-service — certificate mismatch",
            "[INFO]  14:27:45 config-bot: Applied config change #4521 — new mutual TLS certs",
            "[ERROR] 14:29:00 auth-service: Rejecting connections — cert CN does not match expected value",
            "[INFO]  14:25:00 config-bot: Config #4521 description: 'Rotate mTLS certificates for api-gateway'",
        ],
        "actions_taken": [
            "Investigated api-gateway logs",
            "Paged devops team",
        ],
        "minutes_elapsed": 8,
    }

    # Phase 4: Config rolled back, but payment-service still has stale connections — need restart
    phase4_obs = {
        **phase1_obs,
        "alerts": [
            Alert(
                source="Datadog", service="payment-service",
                message="Payment failures dropping but still at 25%",
                severity=Severity.SEV2, timestamp="2024-03-20T14:40:00Z",
            ).model_dump(),
        ],
        "metrics": SystemMetrics(
            error_rate_pct=25.0, latency_p99_ms=4500, cpu_usage_pct=55,
            memory_usage_pct=68, active_connections=600, requests_per_second=280,
        ).model_dump(),
        "log_snippets": [
            "[INFO]  14:38:00 config-bot: Rolled back config #4521 on api-gateway",
            "[INFO]  14:38:30 api-gateway: TLS handshake successful to auth-service",
            "[WARN]  14:39:00 payment-service: Stale connection pool — cached auth tokens expired",
            "[ERROR] 14:39:30 payment-service: 25% of transactions using expired auth context",
        ],
        "actions_taken": [
            "Investigated api-gateway logs",
            "Paged devops team",
            "Rolled back config #4521",
        ],
        "minutes_elapsed": 12,
    }

    # Phase 5: After restarting payment-service, need status update
    phase5_obs = {
        **phase1_obs,
        "alerts": [
            Alert(
                source="Datadog", service="payment-service",
                message="Error rate back to baseline (0.5%)",
                severity=Severity.SEV4, timestamp="2024-03-20T14:45:00Z",
            ).model_dump(),
        ],
        "metrics": SystemMetrics(
            error_rate_pct=0.5, latency_p99_ms=320, cpu_usage_pct=40,
            memory_usage_pct=55, active_connections=1200, requests_per_second=520,
        ).model_dump(),
        "log_snippets": [
            "[INFO] 14:42:00 payment-service: Restarted — fresh connection pool",
            "[INFO] 14:43:00 All services healthy",
        ],
        "actions_taken": [
            "Investigated api-gateway logs",
            "Paged devops team",
            "Rolled back config #4521",
            "Restarted payment-service",
        ],
        "minutes_elapsed": 15,
    }

    # Phase 6: Resolved, need to communicate and page for post-mortem
    phase6_obs = {
        **phase1_obs,
        "alerts": [],
        "metrics": SystemMetrics(
            error_rate_pct=0.2, latency_p99_ms=180, cpu_usage_pct=35,
            memory_usage_pct=52, active_connections=1350, requests_per_second=550,
        ).model_dump(),
        "log_snippets": [],
        "actions_taken": [
            "Investigated api-gateway logs",
            "Paged devops team",
            "Rolled back config #4521",
            "Restarted payment-service",
            "Sent status update",
        ],
        "minutes_elapsed": 18,
    }

    phases = [phase1_obs, phase2_obs, phase3_obs, phase4_obs, phase5_obs, phase6_obs]

    ground_truth = [
        {
            "ideal_action": "investigate",
            "ideal_target": "api-gateway",
            "acceptable_actions": [
                ("investigate", "api-gateway"),
                ("investigate", "auth-service"),
                ("investigate", "payment-service"),
                ("investigate", None),
            ],
            "communication_criteria": [],
            "phase_description": "Multiple alerts — must investigate before acting",
        },
        {
            "ideal_action": "page_team",
            "ideal_target": "devops",
            "acceptable_actions": [
                ("page_team", "devops"),
                ("page_team", "backend"),
                ("page_team", "on-call"),
                ("status_update", None),
            ],
            "communication_criteria": [
                "tls", "certificate", "config", "api-gateway", "investigating",
            ],
            "phase_description": "Found TLS cert issue — page devops, coordinate",
        },
        {
            "ideal_action": "mitigate",
            "ideal_target": "api-gateway",
            "acceptable_actions": [
                ("mitigate", "api-gateway"),
                ("rollback_deploy", "api-gateway"),
                ("restart_service", "api-gateway"),
            ],
            "communication_criteria": [],
            "phase_description": "Root cause clear (config #4521) — rollback/mitigate",
        },
        {
            "ideal_action": "restart_service",
            "ideal_target": "payment-service",
            "acceptable_actions": [
                ("restart_service", "payment-service"),
                ("mitigate", "payment-service"),
                ("investigate", "payment-service"),
            ],
            "communication_criteria": [],
            "phase_description": "Config rolled back but payment-service has stale connections",
        },
        {
            "ideal_action": "status_update",
            "ideal_target": None,
            "acceptable_actions": [
                ("status_update", None),
            ],
            "communication_criteria": [
                "resolved", "payment", "config", "certificate",
                "rollback", "restart", "root cause",
            ],
            "phase_description": "Services recovering — update stakeholders",
        },
        {
            "ideal_action": "page_team",
            "ideal_target": "management",
            "acceptable_actions": [
                ("page_team", "management"),
                ("page_team", "on-call"),
                ("status_update", None),
            ],
            "communication_criteria": [
                "post-mortem", "resolved", "root cause", "config", "impact",
            ],
            "phase_description": "Resolved — schedule post-mortem",
        },
    ]

    return phases, ground_truth


# ═══════════════════════════════════════════════════════════════════════════════
# TASK 3: HARD — Database corruption + potential data breach
#
# Scenario: Database corruption detected, customer PII may have been exposed
# via an unauthorized query. Agent must fix the technical issue AND handle
# compliance/security implications. Wrong moves make it worse.
#
# 8 phases with traps and consequences.
# ═══════════════════════════════════════════════════════════════════════════════

def generate_hard() -> tuple[list[dict], list[dict]]:
    """Database corruption with potential data breach — technical + compliance."""

    context = IncidentContext(
        incident_id="INC-2024-0156",
        started_at="2024-04-02T02:15:00Z",
        affected_users=85000,
        revenue_impact_per_minute=2000.0,
        recent_deploys=[
            "v4.2.0 (database migration, 3h ago)",
            "v1.5.1 (auth-service, 1d ago)",
        ],
        on_call_engineer="Sam Rivera",
    )

    # Phase 1: Database alerts + suspicious query detected
    phase1_obs = {
        "alerts": [
            Alert(
                source="Datadog", service="database",
                message="Replication lag exceeding 30s — primary under heavy load",
                severity=Severity.SEV1, timestamp="2024-04-02T02:15:00Z",
            ).model_dump(),
            Alert(
                source="CloudWatch", service="database",
                message="Disk I/O at 100% on primary — write latency >10s",
                severity=Severity.SEV1, timestamp="2024-04-02T02:15:30Z",
            ).model_dump(),
            Alert(
                source="Security-SIEM", service="database",
                message="ANOMALY: Bulk SELECT on users table from unknown IP 203.0.113.42 — 85K rows returned",
                severity=Severity.SEV1, timestamp="2024-04-02T02:14:00Z",
            ).model_dump(),
            Alert(
                source="Datadog", service="api-gateway",
                message="Elevated 503 rate — database connection timeouts",
                severity=Severity.SEV2, timestamp="2024-04-02T02:16:00Z",
            ).model_dump(),
        ],
        "metrics": SystemMetrics(
            error_rate_pct=35.0, latency_p99_ms=15000, cpu_usage_pct=95,
            memory_usage_pct=88, active_connections=2000, requests_per_second=80,
        ).model_dump(),
        "context": context.model_dump(),
        "log_snippets": [],
        "actions_taken": [],
        "minutes_elapsed": 0,
        "task_description": (
            "CRITICAL: Database is under extreme load AND a security alert shows "
            "a bulk data export from an unknown IP. This may be both a technical "
            "incident AND a data breach. You must: (1) stabilize the database, "
            "(2) investigate the security anomaly, (3) handle compliance implications "
            "(potential PII exposure), (4) coordinate with security and management, "
            "(5) communicate appropriately. CAUTION: Some actions can make things worse. "
            "Do NOT restart the database without investigating first — you could lose "
            "forensic evidence. Available actions: investigate, restart_service, "
            "rollback_deploy, scale_up, page_team, status_update, mitigate, skip."
        ),
    }

    # Phase 2: After investigating, find breach + corrupted migration
    phase2_obs = {
        **phase1_obs,
        "log_snippets": [
            "[ALERT] 02:13:55 db-primary: Query from 203.0.113.42 — SELECT * FROM users (85,247 rows)",
            "[ALERT] 02:13:50 db-primary: Connection from 203.0.113.42 using service account 'migration-bot'",
            "[ERROR] 02:14:30 db-primary: Foreign key constraint violation in orders table — migration v4.2.0 corrupted index",
            "[ERROR] 02:15:00 db-primary: Table 'user_sessions' has 12,847 orphaned rows after migration",
            "[WARN]  02:12:00 auth-service: Service account 'migration-bot' credentials last rotated 180 days ago",
            "[INFO]  02:10:00 deploy-bot: Migration v4.2.0 started — ALTER TABLE users ADD COLUMN preferences JSONB",
        ],
        "actions_taken": ["Investigated database logs"],
        "minutes_elapsed": 5,
    }

    # Phase 3: Should page security team immediately
    phase3_obs = {
        **phase1_obs,
        "log_snippets": [
            "[ALERT] 02:13:55 db-primary: BREACH — 85K user records exported (email, name, hashed_password, phone)",
            "[ALERT] 02:13:50 db-primary: Unauthorized access via compromised service account 'migration-bot'",
            "[INFO]  FORENSIC: IP 203.0.113.42 geolocates to unknown VPN exit node",
            "[INFO]  FORENSIC: migration-bot credentials were exposed in a public GitHub repo 3 days ago",
        ],
        "actions_taken": [
            "Investigated database logs",
            "Paged security team",
        ],
        "minutes_elapsed": 8,
    }

    # Phase 4: Security paged, now must block the IP and rotate credentials
    phase4_obs = {
        **phase1_obs,
        "alerts": [
            Alert(
                source="Security-SIEM", service="database",
                message="Attacker IP 203.0.113.42 still has active session",
                severity=Severity.SEV1, timestamp="2024-04-02T02:23:00Z",
            ).model_dump(),
            Alert(
                source="Datadog", service="database",
                message="Replication lag stabilizing at 5s",
                severity=Severity.SEV3, timestamp="2024-04-02T02:23:00Z",
            ).model_dump(),
        ],
        "metrics": SystemMetrics(
            error_rate_pct=15.0, latency_p99_ms=5000, cpu_usage_pct=72,
            memory_usage_pct=80, active_connections=1200, requests_per_second=200,
        ).model_dump(),
        "log_snippets": [
            "[WARN] 02:23:00 db-primary: Session from 203.0.113.42 still active — running slow queries",
            "[INFO] 02:22:00 security-team: Acknowledged — beginning forensic investigation",
        ],
        "actions_taken": [
            "Investigated database logs",
            "Paged security team",
            "Identified compromised credentials for migration-bot",
        ],
        "minutes_elapsed": 12,
    }

    # Phase 5: After blocking attacker, fix the corrupted migration
    phase5_obs = {
        **phase1_obs,
        "alerts": [
            Alert(
                source="Datadog", service="database",
                message="Foreign key violations still occurring — migration rollback needed",
                severity=Severity.SEV2, timestamp="2024-04-02T02:30:00Z",
            ).model_dump(),
        ],
        "metrics": SystemMetrics(
            error_rate_pct=12.0, latency_p99_ms=3000, cpu_usage_pct=55,
            memory_usage_pct=65, active_connections=900, requests_per_second=350,
        ).model_dump(),
        "log_snippets": [
            "[INFO] 02:28:00 firewall: Blocked IP 203.0.113.42",
            "[INFO] 02:28:30 auth: Rotated credentials for migration-bot service account",
            "[INFO] 02:29:00 db-primary: Terminated session from 203.0.113.42",
            "[ERROR] 02:30:00 db-primary: Orders failing FK constraint — migration v4.2.0 must be rolled back",
        ],
        "actions_taken": [
            "Investigated database logs",
            "Paged security team",
            "Blocked attacker IP and rotated credentials",
        ],
        "minutes_elapsed": 18,
    }

    # Phase 6: After rollback, must send breach notification status update
    phase6_obs = {
        **phase1_obs,
        "alerts": [
            Alert(
                source="Datadog", service="database",
                message="All metrics returning to baseline",
                severity=Severity.SEV4, timestamp="2024-04-02T02:38:00Z",
            ).model_dump(),
        ],
        "metrics": SystemMetrics(
            error_rate_pct=1.2, latency_p99_ms=450, cpu_usage_pct=38,
            memory_usage_pct=55, active_connections=1100, requests_per_second=480,
        ).model_dump(),
        "log_snippets": [
            "[INFO] 02:35:00 deploy-bot: Migration v4.2.0 rolled back successfully",
            "[INFO] 02:36:00 db-primary: FK constraints restored — orphaned rows cleaned",
        ],
        "actions_taken": [
            "Investigated database logs",
            "Paged security team",
            "Blocked attacker IP and rotated credentials",
            "Rolled back migration v4.2.0",
        ],
        "minutes_elapsed": 25,
    }

    # Phase 7: Must page management for breach disclosure
    phase7_obs = {
        **phase1_obs,
        "alerts": [],
        "metrics": SystemMetrics(
            error_rate_pct=0.3, latency_p99_ms=200, cpu_usage_pct=32,
            memory_usage_pct=50, active_connections=1300, requests_per_second=520,
        ).model_dump(),
        "log_snippets": [
            "[INFO] 02:40:00 All services healthy — incident technically resolved",
            "[WARN] COMPLIANCE: 85K user records (PII) were exfiltrated — breach notification required",
            "[INFO] LEGAL: Under GDPR/CCPA, must notify affected users within 72 hours",
        ],
        "actions_taken": [
            "Investigated database logs",
            "Paged security team",
            "Blocked attacker IP and rotated credentials",
            "Rolled back migration v4.2.0",
            "Sent status update on service recovery",
        ],
        "minutes_elapsed": 30,
    }

    # Phase 8: Final — comprehensive status update about breach
    phase8_obs = {
        **phase1_obs,
        "alerts": [],
        "metrics": SystemMetrics(
            error_rate_pct=0.2, latency_p99_ms=180, cpu_usage_pct=30,
            memory_usage_pct=48, active_connections=1350, requests_per_second=540,
        ).model_dump(),
        "log_snippets": [],
        "actions_taken": [
            "Investigated database logs",
            "Paged security team",
            "Blocked attacker IP and rotated credentials",
            "Rolled back migration v4.2.0",
            "Sent status update on service recovery",
            "Paged management for breach disclosure",
        ],
        "minutes_elapsed": 35,
    }

    phases = [
        phase1_obs, phase2_obs, phase3_obs, phase4_obs,
        phase5_obs, phase6_obs, phase7_obs, phase8_obs,
    ]

    ground_truth = [
        {
            "ideal_action": "investigate",
            "ideal_target": "database",
            "acceptable_actions": [
                ("investigate", "database"),
                ("investigate", None),
            ],
            "communication_criteria": [],
            "phase_description": "Multiple alerts + security anomaly — investigate first, don't restart",
        },
        {
            "ideal_action": "page_team",
            "ideal_target": "security",
            "acceptable_actions": [
                ("page_team", "security"),
                ("page_team", "on-call"),
            ],
            "communication_criteria": [],
            "phase_description": "Breach detected — page security team immediately",
        },
        {
            "ideal_action": "status_update",
            "ideal_target": None,
            "acceptable_actions": [
                ("status_update", None),
                ("page_team", "management"),
            ],
            "communication_criteria": [
                "breach", "security", "unauthorized", "data", "investigating",
                "user", "compromised",
            ],
            "phase_description": "Breach confirmed — communicate the security situation",
        },
        {
            "ideal_action": "mitigate",
            "ideal_target": "database",
            "acceptable_actions": [
                ("mitigate", "database"),
                ("mitigate", None),
                ("restart_service", "database"),
            ],
            "communication_criteria": [],
            "phase_description": "Block attacker, rotate credentials — stop the breach",
        },
        {
            "ideal_action": "rollback_deploy",
            "ideal_target": "database",
            "acceptable_actions": [
                ("rollback_deploy", "database"),
                ("rollback_deploy", "v4.2.0"),
                ("mitigate", "database"),
            ],
            "communication_criteria": [],
            "phase_description": "Fix corrupted migration — rollback v4.2.0",
        },
        {
            "ideal_action": "status_update",
            "ideal_target": None,
            "acceptable_actions": [
                ("status_update", None),
            ],
            "communication_criteria": [
                "resolved", "service", "restored", "database",
                "migration", "rollback", "breach", "security",
            ],
            "phase_description": "Services restored — send comprehensive status update",
        },
        {
            "ideal_action": "page_team",
            "ideal_target": "management",
            "acceptable_actions": [
                ("page_team", "management"),
                ("page_team", "security"),
                ("status_update", None),
            ],
            "communication_criteria": [
                "breach", "notification", "gdpr", "ccpa", "pii",
                "user", "disclosure", "72 hours", "legal",
            ],
            "phase_description": "Must escalate breach to management for regulatory notification",
        },
        {
            "ideal_action": "status_update",
            "ideal_target": None,
            "acceptable_actions": [
                ("status_update", None),
                ("page_team", "management"),
            ],
            "communication_criteria": [
                "post-mortem", "breach", "credential", "rotation",
                "migration", "root cause", "timeline", "notification",
            ],
            "phase_description": "Final summary — comprehensive incident + breach report",
        },
    ]

    return phases, ground_truth
