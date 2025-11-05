"""Управление расписанием мастера"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from bot.database.db import (
    get_session,
    get_master_by_telegram,
    get_work_periods,
    get_work_periods_by_weekday,
    set_work_period,
    delete_work_period,
)
from bot.utils.schedule_utils import validate_schedule_period
from bot.utils.impersonation import get_master_telegram_id, get_impersonation_banner
from .common import (
    WAITING_SCHEDULE_START,
    WAITING_SCHEDULE_END,
    WAITING_SCHEDULE_START_MANUAL,
    WAITING_SCHEDULE_END_MANUAL,
)

logger = logging.getLogger(__name__)


async def master_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать расписание мастера"""
    query = update.callback_query
    if query:
        await query.answer()
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        
        if not master:
            text = "❌ Аккаунт не найден"
            if query:
                await query.message.edit_text(text)
            elif update.message:
                await update.message.reply_text(text)
            return
        
        work_periods = get_work_periods(session, master.id)
        
        # Группируем периоды по дням недели
        weekdays = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
        periods_by_day = {i: [] for i in range(7)}
        
        for period in work_periods:
            periods_by_day[period.weekday].append(period)
        
        text = "📅 <b>Ваше расписание</b>\n\n"
        
        has_schedule = False
        for weekday in range(7):
            periods = sorted(periods_by_day[weekday], key=lambda p: p.start_time)
            if periods:
                has_schedule = True
                text += f"<b>{weekdays[weekday]}:</b>\n"
                for period in periods:
                    text += f"  {period.start_time} - {period.end_time}\n"
                text += "\n"
        
        if not has_schedule:
            text += "<i>Расписание не настроено. Добавьте рабочие периоды!</i>\n"
        
        text += get_impersonation_banner(context)
        
        keyboard = []
        
        # Кнопки для редактирования каждого дня
        for weekday in range(7):
            weekday_name = weekdays[weekday]
            periods_count = len(periods_by_day[weekday])
            if periods_count > 0:
                keyboard.append([
                    InlineKeyboardButton(
                        f"✏️ {weekday_name} ({periods_count})",
                        callback_data=f"edit_day_{weekday}"
                    )
                ])
            else:
                keyboard.append([
                    InlineKeyboardButton(
                        f"➕ {weekday_name}",
                        callback_data=f"edit_day_{weekday}"
                    )
                ])
        
        keyboard.append([InlineKeyboardButton("📅 Редактировать всю неделю", callback_data="edit_week")])
        keyboard.append([InlineKeyboardButton("« Назад", callback_data="master_menu")])
        
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


async def schedule_edit_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Редактирование расписания для конкретного дня недели"""
    query = update.callback_query
    await query.answer()
    
    weekday = int(query.data.split('_')[2])
    
    weekdays = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
    weekday_name = weekdays[weekday]
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        
        if not master:
            await query.message.edit_text("❌ Аккаунт не найден")
            return
        
        # Получаем существующие периоды для этого дня
        existing_periods = get_work_periods_by_weekday(session, master.id, weekday)
        existing_periods = sorted(existing_periods, key=lambda p: p.start_time)
        
        # Получаем временные периоды из контекста (если редактируем)
        temp_periods = context.user_data.get(f'schedule_temp_periods_{weekday}', [])
        
        text = f"📅 <b>Редактирование расписания</b>\n\n"
        text += f"День: <b>{weekday_name}</b>\n\n"
        
        if existing_periods or temp_periods:
            text += "<b>Текущие периоды:</b>\n"
            for i, period in enumerate(existing_periods):
                text += f"  {i+1}. {period.start_time} - {period.end_time}\n"
            for i, period in enumerate(temp_periods):
                text += f"  {len(existing_periods)+i+1}. {period['start']} - {period['end']} (новый)\n"
        else:
            text += "<i>Нет рабочих периодов для этого дня</i>\n"
        
        text += f"\n{get_impersonation_banner(context)}"
        
        keyboard = []
        
        # Кнопки для существующих периодов
        for period in existing_periods:
            keyboard.append([
                InlineKeyboardButton(
                    f"🗑 {period.start_time}-{period.end_time}",
                    callback_data=f"schedule_delete_period_{period.id}"
                )
            ])
        
        # Кнопки для временных периодов
        for i, period in enumerate(temp_periods):
            keyboard.append([
                InlineKeyboardButton(
                    f"🗑 {period['start']}-{period['end']} (удалить новый)",
                    callback_data=f"schedule_delete_temp_{weekday}_{i}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton("➕ Добавить период", callback_data=f"schedule_add_period_{weekday}")])
        keyboard.append([InlineKeyboardButton("💾 Сохранить изменения", callback_data=f"schedule_save_{weekday}")])
        keyboard.append([InlineKeyboardButton("❌ Отменить", callback_data=f"schedule_cancel_{weekday}")])
        keyboard.append([InlineKeyboardButton("« Назад", callback_data="master_schedule")])
        
        await query.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def schedule_add_period_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начать добавление рабочего периода"""
    query = update.callback_query
    await query.answer()
    
    weekday = int(query.data.split('_')[3])
    context.user_data['schedule_weekday'] = weekday
    
    # Генерируем кнопки для выбора времени начала
    text = "🕐 Выберите время начала работы:"
    
    keyboard = []
    # Часы с интервалом в 1 час
    for hour in range(8, 22):
        time_str = f"{hour:02d}:00"
        keyboard.append([
            InlineKeyboardButton(
                time_str,
                callback_data=f"schedule_start_{hour:02d}00"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("✏️ Ввести вручную", callback_data="schedule_start_manual")])
    keyboard.append([InlineKeyboardButton("« Отмена", callback_data=f"edit_day_{weekday}")])
    
    await query.message.edit_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return WAITING_SCHEDULE_START


async def schedule_start_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора времени начала"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    if data == "schedule_start_manual":
        text = "🕐 Введите время начала работы (формат ЧЧ:ММ, например 09:00):"
        keyboard = [[InlineKeyboardButton("« Отмена", callback_data=f"edit_day_{context.user_data.get('schedule_weekday', 0)}")]]
        await query.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return WAITING_SCHEDULE_START_MANUAL
    else:
        # Извлекаем время из callback_data: schedule_start_0900
        time_str = data.replace('schedule_start_', '')
        if len(time_str) == 4:
            hour = int(time_str[:2])
            minute = int(time_str[2:])
            start_time = f"{hour:02d}:{minute:02d}"
            context.user_data['schedule_start'] = start_time
            return await _show_end_time_selection(query, context)


async def schedule_start_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить время начала вручную"""
    time_str = update.message.text.strip()
    
    # Проверяем формат
    try:
        parts = time_str.split(':')
        if len(parts) != 2:
            raise ValueError
        hour = int(parts[0])
        minute = int(parts[1])
        
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            raise ValueError
        
        start_time = f"{hour:02d}:{minute:02d}"
        context.user_data['schedule_start'] = start_time
        
        # Показываем выбор времени окончания
        query = update.callback_query
        if not query:
            class FakeCallbackQuery:
                def __init__(self, message):
                    self.message = message
                    self.data = "schedule_start_received"
                async def answer(self):
                    pass
            update.callback_query = FakeCallbackQuery(update.message)
        
        return await _show_end_time_selection(update.callback_query, context)
        
    except ValueError:
        await update.message.reply_text("❌ Неверный формат времени. Используйте ЧЧ:ММ (например, 09:00). Попробуйте снова:")
        return WAITING_SCHEDULE_START_MANUAL


async def _show_end_time_selection(query, context):
    """Показать выбор времени окончания"""
    start_time = context.user_data.get('schedule_start')
    
    text = f"🕐 Выберите время окончания работы:\n\nНачало: <b>{start_time}</b>"
    
    keyboard = []
    
    # Парсим время начала
    start_hour, start_minute = map(int, start_time.split(':'))
    start_total_minutes = start_hour * 60 + start_minute
    
    # Генерируем варианты времени окончания (минимум через 1 час от начала)
    for hour in range(8, 23):
        end_total_minutes = hour * 60
        if end_total_minutes > start_total_minutes:
            time_str = f"{hour:02d}:00"
            keyboard.append([
                InlineKeyboardButton(
                    time_str,
                    callback_data=f"schedule_end_{hour:02d}00"
                )
            ])
    
    keyboard.append([InlineKeyboardButton("✏️ Ввести вручную", callback_data="schedule_end_manual")])
    keyboard.append([InlineKeyboardButton("« Отмена", callback_data=f"edit_day_{context.user_data.get('schedule_weekday', 0)}")])
    
    await query.message.edit_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return WAITING_SCHEDULE_END


async def schedule_end_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора времени окончания"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    if data == "schedule_end_manual":
        text = "🕐 Введите время окончания работы (формат ЧЧ:ММ, например 18:00):"
        keyboard = [[InlineKeyboardButton("« Отмена", callback_data=f"edit_day_{context.user_data.get('schedule_weekday', 0)}")]]
        await query.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return WAITING_SCHEDULE_END_MANUAL
    else:
        # Извлекаем время из callback_data: schedule_end_1800
        time_str = data.replace('schedule_end_', '')
        if len(time_str) == 4:
            hour = int(time_str[:2])
            minute = int(time_str[2:])
            end_time = f"{hour:02d}:{minute:02d}"
            context.user_data['schedule_end'] = end_time
            return await _save_period_to_context(query, context)


async def schedule_end_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить время окончания вручную"""
    time_str = update.message.text.strip()
    
    # Проверяем формат
    try:
        parts = time_str.split(':')
        if len(parts) != 2:
            raise ValueError
        hour = int(parts[0])
        minute = int(parts[1])
        
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            raise ValueError
        
        end_time = f"{hour:02d}:{minute:02d}"
        
        # Проверяем что окончание после начала
        start_time = context.user_data.get('schedule_start')
        start_hour, start_minute = map(int, start_time.split(':'))
        end_hour, end_minute = map(int, end_time.split(':'))
        
        if end_hour * 60 + end_minute <= start_hour * 60 + start_minute:
            await update.message.reply_text("❌ Время окончания должно быть позже времени начала. Попробуйте снова:")
            return WAITING_SCHEDULE_END_MANUAL
        
        context.user_data['schedule_end'] = end_time
        
        # Сохраняем период
        query = update.callback_query
        if not query:
            class FakeCallbackQuery:
                def __init__(self, message):
                    self.message = message
                    self.data = "schedule_end_received"
                async def answer(self):
                    pass
            update.callback_query = FakeCallbackQuery(update.message)
        
        return await _save_period_to_context(update.callback_query, context)
        
    except ValueError:
        await update.message.reply_text("❌ Неверный формат времени. Используйте ЧЧ:ММ (например, 18:00). Попробуйте снова:")
        return WAITING_SCHEDULE_END_MANUAL


async def _save_period_to_context(query, context):
    """Сохранить период в контекст (временный период)"""
    weekday = context.user_data.get('schedule_weekday')
    start_time = context.user_data.get('schedule_start')
    end_time = context.user_data.get('schedule_end')
    
    if not weekday or not start_time or not end_time:
        await query.message.edit_text("❌ Ошибка: не все данные заполнены")
        return ConversationHandler.END
    
    # Валидация периода
    with get_session() as session:
        # Создаем фиктивный update для получения telegram_id
        class FakeUpdate:
            def __init__(self, query):
                self.effective_user = query.from_user
                self.callback_query = query
        fake_update = FakeUpdate(query)
        master = get_master_by_telegram(session, get_master_telegram_id(fake_update, context))
        if master:
            existing_periods = get_work_periods_by_weekday(session, master.id, weekday)
            is_valid, error_msg = validate_schedule_period(existing_periods, start_time, end_time)
            
            if not is_valid:
                await query.message.edit_text(
                    error_msg + "\n\nПопробуйте снова:",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("« Отмена", callback_data=f"edit_day_{weekday}")
                    ]])
                )
                return ConversationHandler.END
    
    # Сохраняем временный период
    if f'schedule_temp_periods_{weekday}' not in context.user_data:
        context.user_data[f'schedule_temp_periods_{weekday}'] = []
    
    context.user_data[f'schedule_temp_periods_{weekday}'].append({
        'start': start_time,
        'end': end_time
    })
    
    # Очищаем временные данные
    context.user_data.pop('schedule_start', None)
    context.user_data.pop('schedule_end', None)
    
    # Возвращаемся к редактированию дня
    await schedule_edit_day(query, context)
    
    return ConversationHandler.END


async def schedule_delete_period(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удалить существующий период расписания"""
    query = update.callback_query
    await query.answer()
    
    period_id = int(query.data.split('_')[3])
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        
        if not master:
            await query.message.edit_text("❌ Аккаунт не найден")
            return
        
        # Получаем период для определения weekday
        from bot.database.models import WorkPeriod
        period = session.query(WorkPeriod).filter_by(id=period_id).first()
        
        if not period or period.master_account_id != master.id:
            await query.message.edit_text("❌ Период не найден")
            return
        
        weekday = period.weekday
        
        # Удаляем период
        if delete_work_period(session, period_id):
            await query.message.edit_text("✅ Период удален")
            # Обновляем отображение дня
            query.data = f"edit_day_{weekday}"
            await schedule_edit_day(update, context)
        else:
            await query.message.edit_text("❌ Ошибка при удалении периода")


async def schedule_delete_temp_period(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удалить временный период (еще не сохраненный)"""
    query = update.callback_query
    await query.answer()
    
    # Формат: schedule_delete_temp_{weekday}_{index}
    parts = query.data.split('_')
    weekday = int(parts[3])
    index = int(parts[4])
    
    temp_periods = context.user_data.get(f'schedule_temp_periods_{weekday}', [])
    if 0 <= index < len(temp_periods):
        temp_periods.pop(index)
        context.user_data[f'schedule_temp_periods_{weekday}'] = temp_periods
    
    await schedule_edit_day(update, context)


async def schedule_save_changes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохранить изменения расписания для дня"""
    query = update.callback_query
    await query.answer()
    
    weekday = int(query.data.split('_')[2])
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        
        if not master:
            await query.message.edit_text("❌ Аккаунт не найден")
            return
        
        # Получаем временные периоды
        temp_periods = context.user_data.get(f'schedule_temp_periods_{weekday}', [])
        
        # Сохраняем каждый временный период
        for period in temp_periods:
            set_work_period(
                session,
                master.id,
                weekday,
                period['start'],
                period['end']
            )
        
        # Очищаем временные данные
        context.user_data.pop(f'schedule_temp_periods_{weekday}', None)
        
        await query.message.edit_text(f"✅ Расписание для {['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье'][weekday]} сохранено!")
        
        # Возвращаемся к расписанию
        query.data = "master_schedule"
        await master_schedule(update, context)


async def schedule_cancel_changes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отменить изменения расписания для дня"""
    query = update.callback_query
    await query.answer()
    
    weekday = int(query.data.split('_')[2])
    
    # Очищаем временные данные
    context.user_data.pop(f'schedule_temp_periods_{weekday}', None)
    context.user_data.pop('schedule_weekday', None)
    context.user_data.pop('schedule_start', None)
    context.user_data.pop('schedule_end', None)
    
    await query.message.edit_text("❌ Изменения отменены")
    
    # Возвращаемся к расписанию
    query.data = "master_schedule"
    await master_schedule(update, context)


async def schedule_edit_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Редактирование расписания на всю неделю"""
    query = update.callback_query
    await query.answer()
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        
        if not master:
            await query.message.edit_text("❌ Аккаунт не найден")
            return
        
        work_periods = get_work_periods(session, master.id)
        
        # Группируем периоды по дням недели
        weekdays = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
        periods_by_day = {i: [] for i in range(7)}
        
        for period in work_periods:
            periods_by_day[period.weekday].append(period)
        
        text = "📅 <b>Редактирование расписания на неделю</b>\n\n"
        text += "Выберите день для редактирования:\n\n"
        
        # Показываем краткую информацию о каждом дне
        for weekday in range(7):
            periods = sorted(periods_by_day[weekday], key=lambda p: p.start_time)
            periods_count = len(periods)
            
            if periods_count > 0:
                periods_text = ", ".join([f"{p.start_time}-{p.end_time}" for p in periods[:2]])
                if periods_count > 2:
                    periods_text += f" (+{periods_count - 2})"
                text += f"{weekdays[weekday]}: {periods_text}\n"
            else:
                text += f"{weekdays[weekday]}: <i>нет периодов</i>\n"
        
        text += f"\n{get_impersonation_banner(context)}"
        
        keyboard = []
        
        # Кнопки для редактирования каждого дня
        for weekday in range(7):
            weekday_name = weekdays[weekday]
            periods_count = len(periods_by_day[weekday])
            if periods_count > 0:
                keyboard.append([
                    InlineKeyboardButton(
                        f"✏️ {weekday_name} ({periods_count})",
                        callback_data=f"edit_day_{weekday}"
                    )
                ])
            else:
                keyboard.append([
                    InlineKeyboardButton(
                        f"➕ {weekday_name}",
                        callback_data=f"edit_day_{weekday}"
                    )
                ])
        
        keyboard.append([InlineKeyboardButton("💾 Сохранить все изменения", callback_data="schedule_save_week")])
        keyboard.append([InlineKeyboardButton("❌ Отменить все", callback_data="schedule_cancel_week")])
        keyboard.append([InlineKeyboardButton("« Назад", callback_data="master_schedule")])
        
        await query.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def schedule_save_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохранить изменения расписания на всю неделю"""
    query = update.callback_query
    await query.answer()
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        
        if not master:
            await query.message.edit_text("❌ Аккаунт не найден")
            return
        
        # Сохраняем временные периоды для всех дней недели
        saved_count = 0
        for weekday in range(7):
            temp_periods = context.user_data.get(f'schedule_temp_periods_{weekday}', [])
            
            # Сохраняем каждый временный период
            for period in temp_periods:
                set_work_period(
                    session,
                    master.id,
                    weekday,
                    period['start'],
                    period['end']
                )
                saved_count += 1
            
            # Очищаем временные данные для этого дня
            context.user_data.pop(f'schedule_temp_periods_{weekday}', None)
        
        # Очищаем общие временные данные
        context.user_data.pop('schedule_weekday', None)
        context.user_data.pop('schedule_start', None)
        context.user_data.pop('schedule_end', None)
        
        if saved_count > 0:
            await query.message.edit_text(f"✅ Расписание сохранено! Добавлено {saved_count} период(ов).")
        else:
            await query.message.edit_text("✅ Расписание сохранено!")
        
        # Возвращаемся к расписанию
        query.data = "master_schedule"
        await master_schedule(update, context)


async def schedule_cancel_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отменить изменения расписания на всю неделю"""
    query = update.callback_query
    await query.answer()
    
    # Очищаем временные данные для всех дней недели
    for weekday in range(7):
        context.user_data.pop(f'schedule_temp_periods_{weekday}', None)
    
    # Очищаем общие временные данные
    context.user_data.pop('schedule_weekday', None)
    context.user_data.pop('schedule_start', None)
    context.user_data.pop('schedule_end', None)
    
    await query.message.edit_text("❌ Все изменения отменены")
    
    # Возвращаемся к расписанию
    query.data = "master_schedule"
    await master_schedule(update, context)

