"""Workflow для онбординга - декларативное описание шагов"""
from bot.core.workflow import Workflow, Step, StepType
from bot.database.db import get_session, get_master_by_telegram, get_services_by_master, get_work_periods
from bot.handlers.master import get_master_telegram_id, get_onboarding_status


def create_onboarding_workflow() -> Workflow:
    """Создать workflow для онбординга"""
    
    workflow = Workflow(
        name="onboarding",
        entry_point="services",
        steps={
            "services": Step(
                id="services",
                type=StepType.ACTION,
                title="Добавление услуг",
                message="💼 <b>Шаг 1: Добавьте услуги</b>\n\nДобавьте хотя бы одну услугу, чтобы клиенты могли записаться к вам.",
                skip_if=lambda u, c: _check_has_services(u, c),
                next_step="schedule",
                keyboard=[[{
                    'text': '➕ Добавить первую услугу',
                    'callback_data': 'add_service'
                }]]
            ),
            "schedule": Step(
                id="schedule",
                type=StepType.ACTION,
                title="Настройка расписания",
                message="📅 <b>Шаг 2: Настройте расписание</b>\n\nУстановите рабочие часы для каждого дня недели.",
                skip_if=lambda u, c: _check_has_schedule(u, c),
                next_step=None,
                keyboard=[[{
                    'text': '📅 Настроить расписание',
                    'callback_data': 'master_schedule'
                }]]
            )
        },
        fallbacks=[],
        context_keys=[]
    )
    
    return workflow


def _check_has_services(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Проверить, есть ли услуги"""
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        if not master:
            return False
        services = get_services_by_master(session, master.id, active_only=True)
        return len(services) > 0


def _check_has_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Проверить, есть ли расписание"""
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        if not master:
            return False
        periods = get_work_periods(session, master.id)
        return len(periods) > 0

