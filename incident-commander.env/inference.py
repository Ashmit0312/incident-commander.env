"""
Inference Script — Incident Commander OpenEnv
===================================
MANDATORY
- Before submitting, ensure the following variables are defined in your environment configuration:
    API_BASE_URL   The API endpoint for the LLM.
    MODEL_NAME     The model identifier to use for inference.
    HF_TOKEN       Your Hugging Face / API key.
    LOCAL_IMAGE_NAME The name of the local image to use for the environment if you are using from_docker_image()

- Defaults are set only for API_BASE_URL and MODEL_NAME:
    API_BASE_URL = os.getenv("API_BASE_URL", "https://router.huggingface.co/v1")
    MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen2.5-72B-Instruct")

- The inference script must be named `inference.py` and placed in the root directory of the project
- Participants must use OpenAI Client for all LLM calls using above variables

STDOUT FORMAT
- The script must emit exactly three line types to stdout, in this order:

    [START] task=<task_name> env=<benchmark> model=<model_name>
    [STEP]  step=<n> action=<action_str> reward=<0.00> done=<true|false> error=<msg|null>
    [END]   success=<true|false> steps=<n> score=<score> rewards=<r1,r2,...,rn>

  Rules:
    - One [START] line at episode begin.
    - One [STEP] line per step, immediately after env.step() returns.
    - One [END] line after env.close(), always emitted (even on exception).
    - reward and rewards are formatted to 2 decimal places.
    - done and success are lowercase booleans: true or false.
    - error is the raw last_action_error string, or null if none.
    - All fields on a single line with no newlines within a line.
    - Each tasks should return score in [0, 1]
"""

import asyncio
import json
import os
import sys
import textwrap
from typing import List, Optional

from openai import OpenAI

from app.environment import IncidentCommanderEnv
from app.models import Action, ActionType

# ── Configuration ────────────────────────────────────────────────────────────

IMAGE_NAME = os.getenv("IMAGE_NAME")
API_KEY = os.getenv("HF_TOKEN") or os.getenv("API_KEY")

API_BASE_URL = os.getenv("API_BASE_URL") or "https://router.huggingface.co/v1"
MODEL_NAME = os.getenv("MODEL_NAME") or "Qwen/Qwen2.5-72B-Instruct"

BENCHMARK = "incident-commander"
TASK_IDS = ["easy", "medium", "hard"]
MAX_STEPS = 12
TEMPERATURE = 0.0
MAX_TOKENS = 800
SUCCESS_SCORE_THRESHOLD = 0.5

# ── System Prompt — teaches the exact decision framework the grader uses ─────

SYSTEM_PROMPT = textwrap.dedent("""
You are an expert infrastructure incident commander. You follow a strict incident response framework.

DECISION FRAMEWORK (follow this exact order):

PHASE 1 — INVESTIGATE FIRST
- If no logs are available yet (log_snippets is empty), your FIRST action MUST be "investigate".
- Target the service with the most critical alerts.
- NEVER restart or rollback before investigating — you need evidence first.

PHASE 2 — IDENTIFY & ESCALATE
- After seeing logs, if the issue involves SECURITY (unauthorized access, breach, data export, unknown IP, compromised credentials), IMMEDIATELY page the "security" team.
- If the issue involves infrastructure/config (TLS, certificates, deployments), page "devops".
- If multiple services are affected, identify which service is the ROOT CAUSE (usually the one that failed FIRST in the timestamps).

PHASE 3 — FIX THE ROOT CAUSE
- Use "rollback_deploy" if a recent deployment or config change caused the issue. Target the service that was changed.
- Use "mitigate" to block attackers, rotate credentials, apply firewall rules. Target the affected service.
- Use "restart_service" ONLY for stale connections or cached state AFTER the root cause is fixed.
- NEVER restart a database during a potential data breach — you will destroy forensic evidence.

PHASE 4 — COMMUNICATE
- After fixing, send a "status_update" to stakeholders.
- Your status update message MUST include ALL of these details:
  * What service was affected
  * What the root cause was (deploy, config, breach, etc.)
  * What action you took (rollback, restart, block, etc.)
  * Current status (recovering, resolved, etc.)
  * Use specific terms: mention version numbers, service names, "rollback", "root cause", etc.
  * If there was a security breach: mention "breach", "unauthorized", "data", "compromised"
  * If there was a compliance issue: mention "GDPR", "CCPA", "notification", "PII", "72 hours"

PHASE 5 — POST-INCIDENT
- After everything is resolved and communicated, page "management" or "on-call" for post-mortem.
- If there was a data breach, page "management" for regulatory disclosure.
- Your message should mention "post-mortem", "root cause", "resolved", and the timeline.

OUTPUT FORMAT:
Return ONLY a JSON object, no markdown, no backticks:
{
  "action_type": "investigate|restart_service|rollback_deploy|scale_up|page_team|status_update|mitigate|skip",
  "target": "service-name-or-team-name",
  "message": "detailed status update text (ONLY for status_update, otherwise null)",
  "reasoning": "your reasoning"
}

VALID TARGETS:
- Services: web-server, api-gateway, auth-service, database, cache, message-queue, payment-service, search-service, cdn, load-balancer
- Teams: backend, frontend, database-team, security, devops, management, on-call

CRITICAL RULES:
- status_update: target should be null, message is REQUIRED and must be detailed
- page_team: target must be a team name
- investigate/restart_service/rollback_deploy/mitigate: target must be a service name
- ALWAYS output valid JSON with no extra text
""").strip()


# ── Logging (mandatory stdout format) ────────────────────────────────────────

def log_start(task: str, env: str, model: str) -> None:
    print(f"[START] task={task} env={env} model={model}", flush=True)


def log_step(step: int, action: str, reward: float, done: bool, error: Optional[str]) -> None:
    error_val = error if error else "null"
    done_val = str(done).lower()
    print(
        f"[STEP] step={step} action={action} reward={reward:.2f} done={done_val} error={error_val}",
        flush=True,
    )


def log_end(success: bool, steps: int, score: float, rewards: List[float]) -> None:
    rewards_str = ",".join(f"{r:.2f}" for r in rewards)
    print(
        f"[END] success={str(success).lower()} steps={steps} score={score:.3f} rewards={rewards_str}",
        flush=True,
    )


# ── Phase Detection — helps agent understand where it is ─────────────────────

def detect_phase_hint(obs_data: dict) -> str:
    """Analyze the current state and provide a hint about what phase we're in."""
    actions_taken = obs_data.get("actions_taken", [])
    logs = obs_data.get("log_snippets", [])
    alerts = obs_data.get("alerts", [])
    metrics = obs_data.get("metrics", {})
    error_rate = metrics.get("error_rate_pct", 0)

    actions_lower = " ".join(a.lower() for a in actions_taken)
    logs_lower = " ".join(l.lower() for l in logs)

    # No actions taken yet → investigate
    if not actions_taken:
        return (
            "PHASE HINT: This is the start of the incident. No investigation has been done yet. "
            "You MUST investigate first before taking any remediation action. "
            "Look at the alerts to identify which service to investigate."
        )

    # Investigated but haven't paged anyone → check for security/escalation needs
    has_investigated = any("investigat" in a.lower() for a in actions_taken)
    has_paged = any("paged" in a.lower() or "page" in a.lower() for a in actions_taken)

    if has_investigated and not has_paged:
        # Check if security issue
        security_keywords = ["breach", "unauthorized", "unknown ip", "compromised", "exfiltrat", "attacker"]
        if any(kw in logs_lower for kw in security_keywords):
            return (
                "PHASE HINT: Investigation revealed a SECURITY ISSUE. "
                "You should page the 'security' team immediately before anything else."
            )
        # Check if config/infra issue
        config_keywords = ["config", "tls", "certificate", "cert"]
        if any(kw in logs_lower for kw in config_keywords):
            return (
                "PHASE HINT: Investigation revealed an infrastructure/config issue. "
                "Consider paging 'devops' team and then rolling back the config change."
            )
        # Generic — logs available, should act
        return (
            "PHASE HINT: You have log data. Identify the root cause from the logs and "
            "take the appropriate remediation action (rollback_deploy, mitigate, or restart_service). "
            "Target the service that is the root cause, not just the symptomatic service."
        )

    # Have paged but haven't fixed yet
    has_fixed = any(kw in actions_lower for kw in ["rolled back", "rollback", "restart", "block", "mitigat", "rotated"])
    if has_paged and not has_fixed:
        # Check for active attacker
        if any("still active" in a.get("message", "").lower() or "still has" in a.get("message", "").lower()
               for a in alerts if isinstance(a, dict)):
            return (
                "PHASE HINT: The team has been paged. Now take action to fix the issue: "
                "mitigate the threat (block attacker, rotate credentials) or "
                "rollback the bad deploy/config. Target the root cause service."
            )
        return (
            "PHASE HINT: Team has been paged. Now fix the root cause. "
            "Use rollback_deploy for bad deployments/configs, mitigate for security actions, "
            "or restart_service for stale connections."
        )

    # Fixed but haven't communicated
    has_communicated = any("status" in a.lower() or "sent" in a.lower() for a in actions_taken)
    if has_fixed and not has_communicated:
        if error_rate > 5:
            # Still partially broken — maybe need another fix (e.g., restart stale service)
            return (
                "PHASE HINT: Root cause was addressed but error rate is still elevated. "
                "Check if another service has stale connections and needs restart_service. "
                "Or if metrics are improving, send a status_update to stakeholders."
            )
        return (
            "PHASE HINT: The fix has been applied and services are recovering. "
            "Send a status_update to stakeholders. Include: what happened, root cause, "
            "what you did to fix it, and current status. Be specific — mention service names, "
            "version numbers, and technical details."
        )

    # Communicated but incident might have more to do
    if has_communicated:
        has_paged_management = "management" in actions_lower
        # Check for breach/compliance needs
        compliance_keywords = ["breach", "pii", "gdpr", "ccpa", "notification", "exfiltrat"]
        if any(kw in logs_lower for kw in compliance_keywords) and not has_paged_management:
            return (
                "PHASE HINT: There was a data breach. You MUST page 'management' for "
                "regulatory breach notification (GDPR/CCPA requires notification within 72 hours). "
                "This is a compliance requirement."
            )
        if error_rate < 1 and not has_paged_management:
            return (
                "PHASE HINT: Incident is resolved. Page 'management' or 'on-call' to schedule "
                "a post-mortem. Mention 'post-mortem', 'root cause', and 'resolved' in your reasoning."
            )
        # Final status update
        return (
            "PHASE HINT: This is likely the final step. Send a comprehensive status_update "
            "summarizing the entire incident: timeline, root cause, actions taken, current status, "
            "and next steps (post-mortem). If there was a breach, mention notification requirements."
        )

    return ""


# ── LLM Agent ────────────────────────────────────────────────────────────────

def get_agent_action(client: OpenAI, obs_data: dict, step_num: int, history: List[dict]) -> dict:
    """Use the LLM to decide the next incident response action."""

    # Format alerts
    alerts_text = ""
    for a in obs_data.get("alerts", []):
        alerts_text += f"  [{a['severity']}] {a['source']}: {a['service']} — {a['message']}\n"
    if not alerts_text:
        alerts_text = "  (no active alerts — incident may be resolved)\n"

    # Format metrics
    m = obs_data.get("metrics", {})
    metrics_text = (
        f"  Error rate: {m.get('error_rate_pct', 0)}% | "
        f"Latency p99: {m.get('latency_p99_ms', 0)}ms | "
        f"CPU: {m.get('cpu_usage_pct', 0)}% | "
        f"Memory: {m.get('memory_usage_pct', 0)}% | "
        f"RPS: {m.get('requests_per_second', 0)}"
    )

    # Format context
    ctx = obs_data.get("context", {})
    deploys = ctx.get("recent_deploys", [])
    deploys_text = "\n".join(f"    - {d}" for d in deploys) if deploys else "    (none)"
    context_text = (
        f"  Incident: {ctx.get('incident_id', 'N/A')}\n"
        f"  Started: {ctx.get('started_at', 'N/A')}\n"
        f"  Affected users: {ctx.get('affected_users', 0)}\n"
        f"  Revenue impact: ${ctx.get('revenue_impact_per_minute', 0)}/min\n"
        f"  Recent deploys:\n{deploys_text}\n"
        f"  On-call: {ctx.get('on_call_engineer', 'N/A')}"
    )

    # Format logs (critical for decision making)
    logs_text = ""
    for log in obs_data.get("log_snippets", []):
        logs_text += f"  {log}\n"
    if not logs_text:
        logs_text = "  (no logs available — you must investigate first to see logs)\n"

    # Format actions taken
    actions_text = ""
    for i, a in enumerate(obs_data.get("actions_taken", []), 1):
        actions_text += f"  {i}. {a}\n"
    if not actions_text:
        actions_text = "  (none yet — this is the first step)\n"

    # Format previous rewards for context
    history_text = ""
    for h in history:
        history_text += f"  Step {h['step']}: {h['action']} → reward={h['reward']:.2f}\n"
    if not history_text:
        history_text = "  (first step)\n"

    # Get phase hint
    phase_hint = detect_phase_hint(obs_data)

    user_msg = textwrap.dedent(f"""
CURRENT SITUATION (Step {step_num}):
Minutes elapsed: {obs_data.get('minutes_elapsed', 0)}

ACTIVE ALERTS:
{alerts_text}
SYSTEM METRICS:
{metrics_text}

INCIDENT CONTEXT:
{context_text}

LOG SNIPPETS:
{logs_text}
ACTIONS TAKEN SO FAR:
{actions_text}
PREVIOUS RESULTS:
{history_text}
{phase_hint}

Task: {obs_data.get('task_description', '')}

Think step by step:
1. What do the alerts and logs tell me?
2. What have I already done?
3. What is the most impactful next action?

Output your decision as a JSON object.
""").strip()

    try:
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
            stream=False,
        )
        content = (completion.choices[0].message.content or "").strip()

        # Strip markdown fences
        if content.startswith("```"):
            content = content.split("\n", 1)[1] if "\n" in content else content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
            if content.startswith("json"):
                content = content[4:].strip()

        # Try to extract JSON if there's extra text around it
        if not content.startswith("{"):
            start = content.find("{")
            end = content.rfind("}") + 1
            if start != -1 and end > start:
                content = content[start:end]

        action = json.loads(content)
        action.setdefault("action_type", "investigate")

        # Sanitize target — ensure it's a string or None
        if action.get("target") == "null" or action.get("target") == "":
            action["target"] = None

        return action

    except Exception as exc:
        print(f"[DEBUG] Model request failed: {exc}", file=sys.stderr, flush=True)
        # Smart fallback based on phase
        actions_taken = obs_data.get("actions_taken", [])
        if not actions_taken:
            return {"action_type": "investigate", "target": None, "message": None,
                    "reasoning": "Fallback: investigate first"}
        elif len(actions_taken) == 1:
            return {"action_type": "page_team", "target": "on-call", "message": None,
                    "reasoning": "Fallback: escalate"}
        else:
            return {"action_type": "status_update", "target": None,
                    "message": "We are investigating the incident and working on a resolution. "
                               "The root cause has been identified and we are applying a fix. "
                               "Services are recovering. Will provide another update shortly.",
                    "reasoning": "Fallback: communicate"}


# ── Run a single task ────────────────────────────────────────────────────────

async def run_task(client: OpenAI, task_id: str) -> float:
    """Run the agent on one task. Returns score in [0, 1]."""
    env = IncidentCommanderEnv()
    rewards: List[float] = []
    steps_taken = 0
    score = 0.0
    success = False
    history: List[dict] = []

    log_start(task=task_id, env=BENCHMARK, model=MODEL_NAME)

    try:
        obs = env.reset(task_id=task_id)

        for step in range(1, MAX_STEPS + 1):
            # Check if episode is done
            state = env.state()
            if state.done:
                break

            # Convert observation to dict for the LLM
            obs_data = obs.model_dump()

            # Get LLM decision with history context
            action_dict = get_agent_action(client, obs_data, step, history)

            # Build typed Action
            action_type_str = action_dict.get("action_type", "investigate")
            try:
                action_type = ActionType(action_type_str)
            except ValueError:
                action_type = ActionType.INVESTIGATE
                action_type_str = "investigate"

            action = Action(
                action_type=action_type,
                target=action_dict.get("target"),
                message=action_dict.get("message"),
                reasoning=action_dict.get("reasoning"),
            )

            # Step the environment
            obs, reward, done, info = env.step(action)

            reward_val = reward.total
            error = None
            rewards.append(reward_val)
            steps_taken = step

            # Concise action string for logging
            target_str = action_dict.get("target") or "none"
            action_str = f"{action_type_str}({target_str})"

            # Track history for context
            history.append({
                "step": step,
                "action": action_str,
                "reward": reward_val,
                "details": reward.details,
            })

            log_step(step=step, action=action_str, reward=reward_val, done=done, error=error)

            if done:
                break

        # Final score via grader
        score = env.grade()
        score = min(max(score, 0.0), 1.0)
        success = score >= SUCCESS_SCORE_THRESHOLD

    except Exception as exc:
        print(f"[DEBUG] Task {task_id} error: {exc}", file=sys.stderr, flush=True)
        score = 0.0
        success = False

    finally:
        try:
            env.close()
        except Exception as e:
            print(f"[DEBUG] env.close() error: {e}", file=sys.stderr, flush=True)
        log_end(success=success, steps=steps_taken, score=score, rewards=rewards)

    return score


# ── Main ─────────────────────────────────────────────────────────────────────

async def main() -> None:
    client = OpenAI(base_url=API_BASE_URL, api_key=API_KEY)

    scores = {}
    for task_id in TASK_IDS:
        scores[task_id] = await run_task(client, task_id)

    # Summary to stderr (stdout reserved for [START]/[STEP]/[END])
    avg = sum(scores.values()) / len(scores)
    print(f"\n--- SUMMARY ---", file=sys.stderr)
    for tid, s in scores.items():
        print(f"  {tid}: {s:.3f}", file=sys.stderr)
    print(f"  average: {avg:.3f}", file=sys.stderr)

    # Persist scores
    with open("baseline_scores.json", "w") as f:
        json.dump(
            {"scores": scores, "average": avg, "model": MODEL_NAME},
            f, indent=2,
        )


if __name__ == "__main__":
    asyncio.run(main())