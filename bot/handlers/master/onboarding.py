"""Пошаговый анбординг для мастеров"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from bot.database.db import (
    get_session,
    get_master_by_telegram,
    get_services_by_master,
    get_work_periods
)
from bot.utils.impersonation import get_master_telegram_id, get_impersonation_banner
from bot.database.models import MasterAccount

logger = logging.getLogger(__name__)

# Шаги анбординга
ONBOARDING_STEPS = [
    {
        'id': 'profile',
        'title': 'Настройка профиля',
        'description': 'Укажите имя и описание для вашего профиля',
        'button_text': '👤 Настроить профиль',
        'callback_data': 'onboarding_profile',
        'check_complete': lambda session, master: _check_profile_complete(session, master)
    },
    {
        'id': 'services',
        'title': 'Добавление услуг',
        'description': 'Добавьте хотя бы одну услугу, чтобы клиенты могли записаться',
        'button_text': '💼 Добавить услугу',
        'callback_data': 'onboarding_services',
        'check_complete': lambda session, master: _check_services_complete(session, master)
    },
    {
        'id': 'schedule',
        'title': 'Настройка расписания',
        'description': 'Установите рабочие часы, чтобы клиенты видели доступное время',
        'button_text': '📅 Настроить расписание',
        'callback_data': 'onboarding_schedule',
        'check_complete': lambda session, master: _check_schedule_complete(session, master)
    }
]


def _check_profile_complete(session, master: MasterAccount) -> bool:
    """Проверить, завершен ли шаг профиля"""
    # Профиль считается завершенным, если есть имя (описание опционально)
    return bool(master.name and master.name.strip())


def _check_services_complete(session, master: MasterAccount) -> bool:
    """Проверить, завершен ли шаг услуг"""
    services = get_services_by_master(session, master.id, active_only=True)
    return len(services) > 0


def _check_schedule_complete(session, master: MasterAccount) -> bool:
    """Проверить, завершен ли шаг расписания"""
    work_periods = get_work_periods(session, master.id)
    return len(work_periods) > 0


def get_onboarding_progress(session, master: MasterAccount) -> dict:
    """Получить информацию о прогрессе анбординга"""
    completed_steps = []
    current_step_index = None
    
    # Проверяем завершенность каждого шага
    for index, step in enumerate(ONBOARDING_STEPS):
        if step['check_complete'](session, master):
            completed_steps.append(step['id'])
        elif current_step_index is None:
            # Первый незавершенный шаг становится текущим
            current_step_index = index
    
    # Если все шаги завершены
    if len(completed_steps) == len(ONBOARDING_STEPS):
        return {
            'is_complete': True,
            'completed_steps': completed_steps,
            'current_step': None,
            'current_step_index': None,
            'progress': 100,
            'step_number': len(ONBOARDING_STEPS),
            'total_steps': len(ONBOARDING_STEPS)
        }
    
    # Если current_step_index не определен, устанавливаем первый шаг
    if current_step_index is None:
        current_step_index = 0
    
    current_step = ONBOARDING_STEPS[current_step_index]
    progress = int((len(completed_steps) / len(ONBOARDING_STEPS)) * 100)
    
    return {
        'is_complete': False,
        'completed_steps': completed_steps,
        'current_step': current_step,
        'current_step_index': current_step_index,
        'progress': progress,
        'step_number': current_step_index + 1,
        'total_steps': len(ONBOARDING_STEPS)
    }


def get_onboarding_message(progress_info: dict, master_name: str) -> str:
    """Сформировать сообщение для анбординга"""
    text = f"👋 Добро пожаловать, <b>{master_name}</b>!\n\n"
    
    if progress_info['is_complete']:
        text += "✅ <b>Анбординг завершен!</b>\n\n"
        text += "🎉 Отлично! Вы настроили все необходимое.\n\n"
        text += "Теперь вы можете:\n"
        text += "• Приглашать клиентов через QR-код\n"
        text += "• Принимать записи\n"
        text += "• Управлять услугами и расписанием\n"
    else:
        current_step = progress_info['current_step']
        step_num = progress_info['step_number']
        total_steps = progress_info['total_steps']
        
        # Прогресс-бар
        progress_bar = _create_progress_bar(progress_info['progress'])
        
        text += f"📋 <b>Настройка профиля</b> ({step_num}/{total_steps})\n\n"
        text += f"{progress_bar} {progress_info['progress']}%\n\n"
        
        text += f"<b>Текущий шаг:</b> {current_step['title']}\n"
        text += f"{current_step['description']}\n\n"
        
        # Показываем завершенные шаги
        if progress_info['completed_steps']:
            text += "✅ <b>Завершено:</b>\n"
            for step in ONBOARDING_STEPS:
                if step['id'] in progress_info['completed_steps']:
                    text += f"  • {step['title']}\n"
            text += "\n"
    
    return text


def _create_progress_bar(progress: int, length: int = 10) -> str:
    """Создать визуальный прогресс-бар"""
    filled = int(progress / 100 * length)
    empty = length - filled
    return "█" * filled + "░" * empty


def get_onboarding_header(session, master: MasterAccount) -> str:
    """Получить заголовок с прогрессом анбординга для отображения в шапке"""
    progress_info = get_onboarding_progress(session, master)
    
    if progress_info['is_complete']:
        return ""
    
    step_num = progress_info['step_number']
    total_steps = progress_info['total_steps']
    progress_bar = _create_progress_bar(progress_info['progress'])
    
    header = f"📋 <b>Настройка профиля</b> ({step_num}/{total_steps})\n"
    header += f"{progress_bar} {progress_info['progress']}%\n\n"
    
    return header


def get_next_step_button(progress_info: dict) -> InlineKeyboardButton:
    """Получить кнопку для перехода к следующему шагу"""
    if progress_info['is_complete']:
        return None
    
    current_step = progress_info['current_step']
    if not current_step:
        return None
    
    current_step_id = current_step['id']
    
    # Если текущий шаг завершен, показываем кнопку перехода к следующему шагу
    if current_step_id in progress_info['completed_steps']:
        # Определяем следующий шаг
        if current_step_id == 'profile':
            next_callback = 'onboarding_next_services'
            button_text = "➕ Добавить услуги"
            return InlineKeyboardButton(button_text, callback_data=next_callback)
        elif current_step_id == 'services':
            next_callback = 'onboarding_next_schedule'
            button_text = "📅 Настроить расписание"
            return InlineKeyboardButton(button_text, callback_data=next_callback)
    
    # Текущий шаг не завершен, кнопка не показывается
    return None


def get_onboarding_keyboard(progress_info: dict) -> InlineKeyboardMarkup:
    """Создать клавиатуру для анбординга"""
    keyboard = []
    
    if not progress_info['is_complete']:
        # Только одна кнопка для текущего шага
        current_step = progress_info['current_step']
        keyboard.append([
            InlineKeyboardButton(
                current_step['button_text'],
                callback_data=current_step['callback_data']
            )
        ])
    else:
        # После завершения показываем основные функции
        keyboard.append([
            InlineKeyboardButton("👤➡️ Пригласить клиента", callback_data="master_qr")
        ])
        keyboard.append([
            InlineKeyboardButton("📋 Записи", callback_data="master_bookings")
        ])
        keyboard.append([
            InlineKeyboardButton("⚙️ Настройки", callback_data="master_settings")
        ])
    
    return InlineKeyboardMarkup(keyboard)


async def show_onboarding(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать экран анбординга"""
    user_id = get_master_telegram_id(update, context)
    
    with get_session() as session:
        master = get_master_by_telegram(session, user_id)
        
        if not master:
            logger.error(f"Master not found for user {user_id}")
            return
        
        progress_info = get_onboarding_progress(session, master)
        
        # Если текущий шаг - услуги и услуг нет, сразу переходим к выбору категории
        current_step = progress_info.get('current_step')
        if current_step and current_step['id'] == 'services':
            services = get_services_by_master(session, master.id, active_only=True)
            if len(services) == 0:
                # Пропускаем информационный экран, сразу переходим к добавлению услуги
                from bot.data.service_templates import get_predefined_categories_list
                from .services import get_categories_by_master
                
                # Очищаем данные предыдущего создания услуги
                service_keys = [k for k in list(context.user_data.keys()) if k.startswith('service_')]
                for key in service_keys:
                    del context.user_data[key]
                
                # Получаем предустановленные категории
                predefined_categories = get_predefined_categories_list()
                
                # Получаем пользовательские категории
                user_categories = get_categories_by_master(session, master.id)
                
                text = "💼 <b>Добавление услуги</b>\n\nВыберите категорию:"
                
                keyboard = []
                
                # Предустановленные категории (исключаем "other", так как добавим отдельную кнопку)
                for key, emoji, name in predefined_categories:
                    if key != "other":  # Исключаем категорию "Другое" из предустановленных
                        keyboard.append([
                            InlineKeyboardButton(
                                f"{emoji} {name}",
                                callback_data=f"service_category_predef_{key}"
                            )
                        ])
                
                # Пользовательские категории (исключаем предустановленные, чтобы избежать дублирования)
                # Сначала новые, потом старые
                user_only_categories = [cat for cat in user_categories if not cat.is_predefined]
                sorted_categories = sorted(user_only_categories, key=lambda x: x.id, reverse=True)
                for cat in sorted_categories:
                    emoji = cat.emoji if cat.emoji else "📁"
                    keyboard.append([
                        InlineKeyboardButton(
                            f"{emoji} {cat.title}",
                            callback_data=f"service_category_{cat.id}"
                        )
                    ])
                
                # Кнопка "Другое" (предпоследняя) и "Вернуться к настройкам профиля" (последняя)
                keyboard.append([InlineKeyboardButton("➕ Другое", callback_data="service_category_custom")])
                keyboard.append([InlineKeyboardButton("« Вернуться к настройкам профиля", callback_data="onboarding_profile")])
                
                # Отправляем сообщение с выбором категории
                if update.message:
                    await update.message.reply_text(
                        text,
                        parse_mode='HTML',
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                elif update.callback_query:
                    await update.callback_query.message.edit_text(
                        text,
                        parse_mode='HTML',
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                    await update.callback_query.answer()
                
                return
        
        text = get_onboarding_message(progress_info, master.name)
        
        # Добавляем баннер имперсонации
        text += get_impersonation_banner(context)
        
        keyboard = get_onboarding_keyboard(progress_info)
        
        if update.message:
            await update.message.reply_text(
                text,
                parse_mode='HTML',
                reply_markup=keyboard
            )
        elif update.callback_query:
            await update.callback_query.message.edit_text(
                text,
                parse_mode='HTML',
                reply_markup=keyboard
            )
            await update.callback_query.answer()


async def onboarding_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик шага профиля в анбординге"""
    query = update.callback_query
    if query:
        await query.answer()
    
    # Перенаправляем на профиль
    from .profile import master_profile
    await master_profile(update, context)
    
    # После возврата из профиля проверяем прогресс
    await check_onboarding_progress(update, context)


async def onboarding_services(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик шага услуг в анбординге"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = get_master_telegram_id(update, context)
    
    with get_session() as session:
        master = get_master_by_telegram(session, user_id)
        
        if not master:
            return
        
        # Проверяем, есть ли услуги
        services = get_services_by_master(session, master.id, active_only=True)
        
        if len(services) == 0:
            # Нет услуг - сразу переходим к выбору категории
            from bot.data.service_templates import get_predefined_categories_list
            from .services import get_categories_by_master
            
            # Очищаем данные предыдущего создания услуги
            service_keys = [k for k in list(context.user_data.keys()) if k.startswith('service_')]
            for key in service_keys:
                del context.user_data[key]
            
            # Получаем предустановленные категории
            predefined_categories = get_predefined_categories_list()
            
            # Получаем пользовательские категории
            user_categories = get_categories_by_master(session, master.id)
            
            text = "💼 <b>Добавление услуги</b>\n\nВыберите категорию:"
            
            keyboard = []
            
            # Предустановленные категории (исключаем "other", так как добавим отдельную кнопку)
            for key, emoji, name in predefined_categories:
                if key != "other":  # Исключаем категорию "Другое" из предустановленных
                    keyboard.append([
                        InlineKeyboardButton(
                            f"{emoji} {name}",
                            callback_data=f"service_category_predef_{key}"
                        )
                    ])
            
            # Пользовательские категории (исключаем предустановленные, чтобы избежать дублирования)
            # Сначала новые, потом старые
            user_only_categories = [cat for cat in user_categories if not cat.is_predefined]
            sorted_categories = sorted(user_only_categories, key=lambda x: x.id, reverse=True)
            for cat in sorted_categories:
                emoji = cat.emoji if cat.emoji else "📁"
                keyboard.append([
                    InlineKeyboardButton(
                        f"{emoji} {cat.title}",
                        callback_data=f"service_category_{cat.id}"
                    )
                ])
            
            # Кнопка "Другое" (предпоследняя) и "Вернуться к настройкам профиля" (последняя)
            keyboard.append([InlineKeyboardButton("➕ Другое", callback_data="service_category_custom")])
            keyboard.append([InlineKeyboardButton("« Вернуться к настройкам профиля", callback_data="onboarding_profile")])
            
            # Отправляем сообщение с выбором категории
            if query:
                await query.message.edit_text(
                    text,
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            elif update.message:
                await update.message.reply_text(
                    text,
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
        else:
            # Есть услуги - показываем обычный экран услуг
            from .services import master_services
            await master_services(update, context)
            
            # После возврата из услуг проверяем прогресс
            await check_onboarding_progress(update, context)


async def onboarding_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик шага расписания в анбординге"""
    query = update.callback_query
    if query:
        await query.answer()
    
    # Перенаправляем на расписание
    from .schedule import master_schedule
    await master_schedule(update, context)
    
    # После возврата из расписания проверяем прогресс
    await check_onboarding_progress(update, context)


async def check_onboarding_progress(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверить прогресс анбординга и обновить экран"""
    user_id = get_master_telegram_id(update, context)
    
    with get_session() as session:
        master = get_master_by_telegram(session, user_id)
        
        if not master:
            return
        
        progress_info = get_onboarding_progress(session, master)
        
        # Если анбординг завершен, показываем финальный экран
        if progress_info['is_complete']:
            await show_onboarding(update, context)
        # Иначе остаемся в текущем разделе, пользователь может вернуться через меню


async def onboarding_next_services(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Переход к следующему шагу - услуги"""
    query = update.callback_query
    if query:
        await query.answer()
    
    # Переходим к услугам (onboarding_services уже обрабатывает пропуск информационного экрана)
    await onboarding_services(update, context)


async def onboarding_next_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Переход к следующему шагу - расписание"""
    query = update.callback_query
    if query:
        await query.answer()
    
    # Переходим к расписанию
    await onboarding_schedule(update, context)
