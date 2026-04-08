---
title: Incident Commander OpenEnv
emoji: 🚨
colorFrom: red
colorTo: orange
sdk: docker
pinned: false
tags:
  - openenv
---

# 🚨 Incident Commander OpenEnv

An OpenEnv-compliant environment for training and evaluating AI agents on **real-world infrastructure incident response** — the high-stakes work of diagnosing production outages, coordinating teams, applying fixes, and communicating under pressure.

## Why Incident Response?

Every tech company experiences production incidents. When systems go down at 3am, an incident commander must rapidly: read alerts, check logs, identify root causes, decide what to fix (and in what order), page the right teams, and keep stakeholders informed — all while the clock ticks and revenue bleeds.

This environment simulates that workflow with realistic multi-service architectures, cascading failures, security breaches, and compliance implications. Getting it wrong has real consequences: restarting a database during a breach destroys forensic evidence; treating symptoms instead of root causes leads to repeat failures.

---

## Environment Overview

The agent receives **monitoring alerts, system metrics, and log snippets** at each step and must choose an incident response action.

| Component | Description |
|-----------|-------------|
| **Observation** | Active alerts, system metrics (error rate, latency, CPU, memory), incident context, log snippets, actions taken so far |
| **Action** | Action type (investigate/restart/rollback/page/communicate/mitigate) + target service/team + optional message |
| **Reward** | Weighted: 40% correct action + 30% correct target + 30% communication quality + speed bonus − penalties |

### Action Space

| Field | Type | Values |
|-------|------|--------|
| `action_type` | enum | `investigate`, `restart_service`, `rollback_deploy`, `scale_up`, `page_team`, `status_update`, `mitigate`, `skip` |
| `target` | string | Service name (`web-server`, `database`, etc.) or team name (`security`, `devops`, etc.) |
| `message` | string | Status update text (for `status_update` actions) |
| `reasoning` | string | Agent's explanation (optional) |

### Observation Space

| Field | Type | Description |
|-------|------|-------------|
| `alerts` | list[Alert] | Active monitoring alerts (source, service, message, severity) |
| `metrics` | SystemMetrics | Error rate %, p99 latency, CPU %, memory %, connections, RPS |
| `context` | IncidentContext | Incident ID, start time, affected users, $/min impact, recent deploys |
| `log_snippets` | list[str] | Log lines (populated after investigate actions) |
| `actions_taken` | list[str] | What the agent has done so far |
| `minutes_elapsed` | int | Time pressure indicator |
| `task_description` | str | What the agent should accomplish |

---

## Tasks

### Task 1: Easy — Single Service Crash (4 phases)
A web server crashes after a bad deployment. Logs clearly show an out-of-memory error from v2.3.1. The agent must investigate → rollback → communicate → schedule post-mortem.

**Expected score:** 0.65–0.90 for capable models.

### Task 2: Medium — Cascading Failure (6 phases)
A TLS certificate config change on the API gateway breaks authentication, which cascades to payment processing. The agent must trace the failure chain to the root cause (not just treat symptoms), coordinate with devops, rollback the config, restart stale services, and communicate.

**Expected score:** 0.50–0.75 for capable models.

### Task 3: Hard — Database Corruption + Data Breach (8 phases)
A database migration corrupted indexes AND a compromised service account was used to exfiltrate 85K user records. The agent must handle both the technical fix AND the security/compliance implications — page security, block the attacker, preserve evidence, rollback the migration, notify management for regulatory disclosure (GDPR/CCPA), and provide comprehensive status updates. Wrong actions (like restarting the DB) destroy evidence and incur penalties.

**Expected score:** 0.35–0.60 for frontier models.

---

## Reward Design

Per-step rewards with partial credit and penalties:

- **Action type (40%):** Exact match = 1.0, acceptable alternative = 0.6, related action = 0.2–0.4
- **Target (30%):** Exact match = 1.0, related target = 0.3–0.7, missing target = 0.3
- **Communication (30%):** For status updates, scored by keyword criteria coverage
- **Speed bonus:** +0.05 for correct actions within 5 minutes, +0.02 within 10 minutes
- **Penalties:** -0.15 for skipping, -0.2 for restarting when should investigate, -0.3 for dangerous actions during breach

---

## Setup & Usage

### Run locally

```bash
pip install -r requirements.txt
uvicorn app.server:app --host 0.0.0.0 --port 8000

# In another terminal
export API_BASE_URL="https://router.huggingface.co/v1"
export MODEL_NAME="Qwen/Qwen2.5-72B-Instruct"
export HF_TOKEN="your-api-key"
python inference.py
```

### Run with Docker

```bash
docker build -t incident-commander .
docker run -p 7860:7860 incident-commander
```

### API Usage

```bash
# Reset (empty body defaults to easy task)
curl -X POST http://localhost:7860/reset -H "Content-Type: application/json" -d '{}'

# Step
curl -X POST http://localhost:7860/step -H "Content-Type: application/json" -d '{
  "action_type": "investigate",
  "target": "web-server",
  "reasoning": "Need to check logs before acting"
}'

# State / Grade
curl http://localhost:7860/state
curl http://localhost:7860/grade
```

---

## Project Structure

```
incident-commander/
├── app/
│   ├── __init__.py
│   ├── models.py          # Pydantic models (Observation, Action, Reward, State)
│   ├── incidents.py        # Incident scenarios with ground truth
│   ├── grader.py           # Deterministic grading with partial credit
│   ├── environment.py      # Core OpenEnv (reset/step/state/close)
│   └── server.py           # FastAPI HTTP server
├── inference.py            # Baseline LLM agent (hackathon format)
├── openenv.yaml            # OpenEnv metadata spec
├── requirements.txt
├── Dockerfile
└── README.md
```

---

## OpenEnv Spec Compliance

- ✅ Typed Pydantic models for Observation, Action, Reward, State
- ✅ `step(action)` → (observation, reward, done, info)
- ✅ `reset(task_id)` → initial observation (defaults to "easy" with empty body)
- ✅ `state()` → full internal state
- ✅ `close()` → cleanup
- ✅ `openenv.yaml` with metadata
- ✅ 3 tasks with programmatic graders (0.0–1.0)
- ✅ Meaningful per-step reward with partial credit
- ✅ Baseline inference script with OpenAI client + hackathon stdout format
- ✅ Dockerfile builds and runs on port 7860
- ✅ POST /reset with {} returns 200

## License

MIT
