"""
CartoGraph Celery application

Priority queues per agent type — higher number = higher priority.
Workers are started with: celery -A app.celery_app worker -Q <queue>
"""

from __future__ import annotations

from celery import Celery

from app.config.variables import cg_settings

celery_app = Celery(
    "cartograph",
    broker=cg_settings.CELERY_BROKER_URL,
    backend=cg_settings.CELERY_RESULT_BACKEND,
    include=[
        "app.agents.agent1_keyword_miner",
        "app.agents.agent2_serp_discovery",
        "app.agents.agent3_domain_classifier",
        "app.agents.agent4_seo_metrics",
        "app.agents.agent5_tech_stack",
        "app.agents.agent6_intent_scoring",
        "app.agents.agent7_change_detection",
        "app.webhook_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # One queue per agent type — allows independent scaling
    task_routes={
        "app.agents.agent1_keyword_miner.*": {"queue": "agent1_keyword_miner"},
        "app.agents.agent2_serp_discovery.*": {"queue": "agent2_serp_discovery"},
        "app.agents.agent3_domain_classifier.*": {"queue": "agent3_domain_classifier"},
        "app.agents.agent4_seo_metrics.*": {"queue": "agent4_seo_metrics"},
        "app.agents.agent5_tech_stack.*": {"queue": "agent5_tech_stack"},
        "app.agents.agent6_intent_scoring.*": {"queue": "agent6_intent_scoring"},
        "app.agents.agent7_change_detection.*": {"queue": "agent7_change_detection"},
        "app.webhook_tasks.*": {"queue": "webhook_delivery"},
    },
    # Retry policy
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # Dead letter queue — tasks that exhaust retries land here
    task_annotations={
        "*": {
            "max_retries": 5,
            "default_retry_delay": 60,  # seconds; agent code may override
        }
    },
)
