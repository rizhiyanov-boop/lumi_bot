"""Workflows для бота"""
from bot.workflows.add_service_workflow import create_add_service_workflow
from bot.workflows.onboarding_workflow import create_onboarding_workflow

__all__ = [
    'create_add_service_workflow',
    'create_onboarding_workflow'
]

