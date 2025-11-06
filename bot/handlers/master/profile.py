"""Управление профилем мастера"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from bot.database.db import get_session, get_master_by_telegram
from bot.utils.impersonation import get_master_telegram_id, get_impersonation_banner
from .common import WAITING_NAME, WAITING_DESCRIPTION

logger = logging.getLogger(__name__)


async def _send_profile_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, session, master):
    """Вспомогательная функция для отправки меню профиля"""
    # Проверяем прогресс анбординга
    from .onboarding import get_onboarding_progress, get_onboarding_header, get_next_step_button
    
    progress_info = get_onboarding_progress(session, master)
    onboarding_header = get_onboarding_header(session, master)
    next_button = get_next_step_button(progress_info)
    
    # Добавляем заголовок с прогрессом, если анбординг не завершен
    text = onboarding_header if onboarding_header else ""
    text += f"👤 <b>Профиль</b>\n\n"
    text += f"📌 Имя: <b>{master.name}</b>\n"
    if master.description:
        text += f"📝 Описание: {master.description}\n"
    text += f"🆔 ID: <code>{master.id}</code>\n\n"
    text += get_impersonation_banner(context)
    
    keyboard = [
        [InlineKeyboardButton("✏️ Изменить имя", callback_data="edit_name")],
        [InlineKeyboardButton("✏️ Изменить описание", callback_data="edit_description")],
        [InlineKeyboardButton("🖼 Загрузить фото", callback_data="upload_photo")],
        [InlineKeyboardButton("📸 Портфолио", callback_data="master_portfolio")]
    ]
    
    # Добавляем кнопку "Далее" или "Назад" в зависимости от статуса анбординга
    if next_button:
        keyboard.append([next_button])
    else:
        keyboard.append([InlineKeyboardButton("« Назад", callback_data="master_menu")])
    
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def master_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Профиль мастера"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user = update.effective_user
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        
        if not master:
            if query:
                await query.message.edit_text("❌ Аккаунт не найден")
            return
        
        # Проверяем прогресс анбординга
        from .onboarding import get_onboarding_progress, get_onboarding_header, get_next_step_button
        
        progress_info = get_onboarding_progress(session, master)
        onboarding_header = get_onboarding_header(session, master)
        next_button = get_next_step_button(progress_info)
        
        # Добавляем заголовок с прогрессом, если анбординг не завершен
        text = onboarding_header if onboarding_header else ""
        text += f"👤 <b>Профиль</b>\n\n"
        text += f"📌 Имя: <b>{master.name}</b>\n"
        if master.description:
            text += f"📝 Описание: {master.description}\n"
        text += f"🆔 ID: <code>{master.id}</code>\n\n"
        text += get_impersonation_banner(context)
        
        keyboard = [
            [InlineKeyboardButton("✏️ Изменить имя", callback_data="edit_name")],
            [InlineKeyboardButton("✏️ Изменить описание", callback_data="edit_description")],
            [InlineKeyboardButton("🖼 Загрузить фото", callback_data="upload_photo")],
            [InlineKeyboardButton("📸 Портфолио", callback_data="master_portfolio")]
        ]
        
        # Добавляем кнопку "Далее" или "Назад" в зависимости от статуса анбординга
        if next_button:
            keyboard.append([next_button])
        else:
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


async def edit_name_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начать редактирование имени"""
    query = update.callback_query
    await query.answer()
    
    text = "✏️ <b>Изменение имени</b>\n\nВведите новое имя:"
    keyboard = [[InlineKeyboardButton("« Отмена", callback_data="master_profile")]]
    
    await query.message.edit_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return WAITING_NAME


async def edit_description_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начать редактирование описания"""
    query = update.callback_query
    await query.answer()
    
    text = "✏️ <b>Изменение описания</b>\n\nВведите новое описание:"
    keyboard = [[InlineKeyboardButton("« Отмена", callback_data="master_profile")]]
    
    await query.message.edit_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return WAITING_DESCRIPTION


async def receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить новое имя"""
    text = update.message.text.strip()
    
    if len(text) < 2:
        await update.message.reply_text("❌ Имя слишком короткое. Минимум 2 символа.")
        return WAITING_NAME
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        if master:
            from bot.database.models import MasterAccount
            master = session.query(MasterAccount).filter_by(id=master.id).first()
            master.name = text
            session.commit()
            
            await update.message.reply_text(f"✅ Имя изменено на: <b>{text}</b>", parse_mode='HTML')
            
            # Всегда возвращаемся в меню профиля - отправляем новое сообщение
            await _send_profile_menu(update, context, session, master)
    
    return ConversationHandler.END


async def receive_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить новое описание"""
    text = update.message.text.strip()
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        if master:
            from bot.database.models import MasterAccount
            master = session.query(MasterAccount).filter_by(id=master.id).first()
            master.description = text
            session.commit()
            
            await update.message.reply_text("✅ Описание обновлено", parse_mode='HTML')
            
            # Всегда возвращаемся в меню профиля - отправляем новое сообщение
            await _send_profile_menu(update, context, session, master)
    
    return ConversationHandler.END


async def upload_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начать загрузку фото профиля"""
    query = update.callback_query
    await query.answer()
    
    text = "🖼 <b>Загрузка фото профиля</b>\n\nОтправьте фото, которое будет отображаться в вашем профиле."
    text += get_impersonation_banner(context)
    
    keyboard = [[InlineKeyboardButton("« Отмена", callback_data="master_profile")]]
    
    await query.message.edit_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    context.user_data['uploading_photo_type'] = 'avatar'


async def receive_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик получения фото (для профиля или портфолио)"""
    photo_type = context.user_data.get('uploading_photo_type')
    
    if not photo_type:
        return
    
    # Получаем самое большое фото
    photo = update.message.photo[-1]
    file_id = photo.file_id
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        
        if not master:
            await update.message.reply_text("❌ Аккаунт не найден")
            return
        
        if photo_type == 'avatar':
            # Сохраняем фото профиля
            from bot.database.models import MasterAccount
            master = session.query(MasterAccount).filter_by(id=master.id).first()
            master.avatar_url = file_id
            session.commit()
            
            await update.message.reply_text("✅ Фото профиля успешно загружено!")
            
            # Возвращаемся к профилю - отправляем новое сообщение
            await _send_profile_menu(update, context, session, master)
            
        elif photo_type == 'portfolio':
            # Добавляем фото в портфолио (обрабатывается в portfolio.py)
            from .portfolio import receive_portfolio_photo
            await receive_portfolio_photo(update, context)
        
        context.user_data.pop('uploading_photo_type', None)

