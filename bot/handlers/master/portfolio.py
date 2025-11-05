"""Управление портфолио мастера"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import ContextTypes
from bot.database.db import (
    get_session,
    get_master_by_telegram,
    get_portfolio_photos,
    get_portfolio_limit,
    add_portfolio_photo,
    delete_portfolio_photo,
)
from bot.utils.impersonation import get_master_telegram_id, get_impersonation_banner

logger = logging.getLogger(__name__)


async def master_portfolio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать портфолио мастера"""
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
        
        portfolio_photos = get_portfolio_photos(session, master.id)
        current_count, max_photos = get_portfolio_limit(session, master.id)
        
        text = f"📸 <b>Мое портфолио</b>\n\n"
        text += f"Фото: {current_count}/{max_photos}\n\n"
        
        if portfolio_photos:
            text += f"У вас <b>{len(portfolio_photos)}</b> фото в портфолио.\n\n"
            text += "Выберите действие:"
        else:
            text += "<i>Портфолио пусто. Добавьте свои работы!</i>"
        
        text += get_impersonation_banner(context)
        
        keyboard = []
        
        if portfolio_photos:
            keyboard.append([InlineKeyboardButton("👁 Просмотреть портфолио", callback_data="portfolio_view")])
        
        keyboard.append([InlineKeyboardButton("➕ Добавить фото", callback_data="portfolio_add")])
        
        if portfolio_photos:
            keyboard.append([InlineKeyboardButton("🗑 Удалить фото", callback_data="portfolio_delete")])
        
        keyboard.append([InlineKeyboardButton("« Назад", callback_data="master_profile")])
        
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


async def portfolio_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начать добавление фото в портфолио"""
    query = update.callback_query
    await query.answer()
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        
        if not master:
            await query.message.edit_text("❌ Аккаунт не найден")
            return
        
        current_count, max_photos = get_portfolio_limit(session, master.id)
        
        if current_count >= max_photos:
            await query.message.edit_text(
                f"❌ Достигнут лимит портфолио ({max_photos} фото).\n\n"
                f"Текущий тариф: {master.subscription_level}\n"
                f"Для увеличения лимита перейдите на более высокий тариф.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("« Назад", callback_data="master_portfolio")
                ]])
            )
            return
        
        text = f"📸 <b>Добавление фото в портфолио</b>\n\n"
        text += f"Отправьте фото для добавления в портфолио.\n\n"
        text += f"Фото в портфолио: {current_count}/{max_photos}\n"
        text += f"Вы можете добавить еще {max_photos - current_count} фото."
        text += get_impersonation_banner(context)
        
        keyboard = [[InlineKeyboardButton("« Отмена", callback_data="master_portfolio")]]
        
        await query.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        context.user_data['uploading_photo_type'] = 'portfolio'


async def receive_portfolio_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить фото для портфолио"""
    photo = update.message.photo[-1]
    file_id = photo.file_id
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        
        if not master:
            await update.message.reply_text("❌ Аккаунт не найден")
            return
        
        current_count, max_photos = get_portfolio_limit(session, master.id)
        
        if current_count >= max_photos:
            await update.message.reply_text(
                f"❌ Достигнут лимит портфолио ({max_photos} фото).\n\n"
                f"Текущий тариф: {master.subscription_level}\n"
                f"Для увеличения лимита перейдите на более высокий тариф."
            )
            context.user_data.pop('uploading_photo_type', None)
            return
        
        # Получаем подпись к фото (если есть текст в сообщении)
        caption = update.message.caption if update.message.caption else None
        
        portfolio_photo = add_portfolio_photo(session, master.id, file_id, caption)
        
        if portfolio_photo:
            await update.message.reply_text(
                f"✅ Фото добавлено в портфолио!\n\n"
                f"Фото в портфолио: {current_count + 1}/{max_photos}"
            )
            
            # Возвращаемся к портфолио
            class FakeCallbackQuery:
                def __init__(self, message):
                    self.message = message
                    self.data = "master_portfolio"
                async def answer(self):
                    pass
            
            update.callback_query = FakeCallbackQuery(update.message)
            await master_portfolio(update, context)
        else:
            await update.message.reply_text("❌ Ошибка при добавлении фото в портфолио")
        
        context.user_data.pop('uploading_photo_type', None)


async def portfolio_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Просмотр портфолио с навигацией"""
    query = update.callback_query
    await query.answer()
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        
        if not master:
            await query.message.edit_text("❌ Аккаунт не найден")
            return
        
        portfolio_photos = get_portfolio_photos(session, master.id)
        
        if not portfolio_photos:
            await query.message.edit_text(
                "📸 <b>Портфолио пусто</b>\n\nДобавьте фото в портфолио!",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("« Назад", callback_data="master_portfolio")
                ]])
            )
            return
        
        # Сохраняем данные для навигации
        context.user_data['portfolio_index'] = 0
        context.user_data['portfolio_photos'] = [p.id for p in portfolio_photos]
        
        # Отправляем первое фото
        first_photo = portfolio_photos[0]
        caption = f"📸 <b>Мое портфолио</b>\n\n(1/{len(portfolio_photos)})"
        if first_photo.caption:
            caption += f"\n\n{first_photo.caption}"
        
        keyboard = []
        if len(portfolio_photos) > 1:
            keyboard.append([
                InlineKeyboardButton("▶️ Следующее", callback_data="portfolio_next")
            ])
        keyboard.append([
            InlineKeyboardButton("🗑 Удалить", callback_data=f"portfolio_delete_confirm_{first_photo.id}")
        ])
        keyboard.append([
            InlineKeyboardButton("« Назад", callback_data="master_portfolio")
        ])
        
        await query.message.delete()
        await query.message.chat.send_photo(
            photo=first_photo.file_id,
            caption=caption,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def portfolio_next(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Следующее фото в портфолио"""
    query = update.callback_query
    await query.answer()
    
    photo_ids = context.user_data.get('portfolio_photos', [])
    
    if not photo_ids:
        await query.message.edit_text("❌ Ошибка просмотра портфолио")
        return
    
    current_index = context.user_data.get('portfolio_index', 0)
    current_index = (current_index + 1) % len(photo_ids)
    context.user_data['portfolio_index'] = current_index
    
    with get_session() as session:
        from bot.database.models import Portfolio
        photo = session.query(Portfolio).filter_by(id=photo_ids[current_index]).first()
        
        if not photo:
            await query.message.edit_text("❌ Фото не найдено")
            return
        
        caption = f"📸 <b>Мое портфолио</b>\n\n({current_index + 1}/{len(photo_ids)})"
        if photo.caption:
            caption += f"\n\n{photo.caption}"
        
        keyboard = []
        if len(photo_ids) > 1:
            keyboard.append([
                InlineKeyboardButton("◀️ Предыдущее", callback_data="portfolio_prev"),
                InlineKeyboardButton("▶️ Следующее", callback_data="portfolio_next")
            ])
        keyboard.append([
            InlineKeyboardButton("🗑 Удалить", callback_data=f"portfolio_delete_confirm_{photo.id}")
        ])
        keyboard.append([
            InlineKeyboardButton("« Назад", callback_data="master_portfolio")
        ])
        
        await query.message.edit_media(
            media=InputMediaPhoto(media=photo.file_id, caption=caption, parse_mode='HTML'),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def portfolio_prev(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Предыдущее фото в портфолио"""
    query = update.callback_query
    await query.answer()
    
    photo_ids = context.user_data.get('portfolio_photos', [])
    
    if not photo_ids:
        await query.message.edit_text("❌ Ошибка просмотра портфолио")
        return
    
    current_index = context.user_data.get('portfolio_index', 0)
    current_index = (current_index - 1) % len(photo_ids)
    context.user_data['portfolio_index'] = current_index
    
    with get_session() as session:
        from bot.database.models import Portfolio
        photo = session.query(Portfolio).filter_by(id=photo_ids[current_index]).first()
        
        if not photo:
            await query.message.edit_text("❌ Фото не найдено")
            return
        
        caption = f"📸 <b>Мое портфолио</b>\n\n({current_index + 1}/{len(photo_ids)})"
        if photo.caption:
            caption += f"\n\n{photo.caption}"
        
        keyboard = []
        if len(photo_ids) > 1:
            keyboard.append([
                InlineKeyboardButton("◀️ Предыдущее", callback_data="portfolio_prev"),
                InlineKeyboardButton("▶️ Следующее", callback_data="portfolio_next")
            ])
        keyboard.append([
            InlineKeyboardButton("🗑 Удалить", callback_data=f"portfolio_delete_confirm_{photo.id}")
        ])
        keyboard.append([
            InlineKeyboardButton("« Назад", callback_data="master_portfolio")
        ])
        
        await query.message.edit_media(
            media=InputMediaPhoto(media=photo.file_id, caption=caption, parse_mode='HTML'),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def portfolio_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начать удаление фото из портфолио (показать список)"""
    query = update.callback_query
    await query.answer()
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        
        if not master:
            await query.message.edit_text("❌ Аккаунт не найден")
            return
        
        portfolio_photos = get_portfolio_photos(session, master.id)
        
        if not portfolio_photos:
            await query.message.edit_text(
                "📸 <b>Портфолио пусто</b>",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("« Назад", callback_data="master_portfolio")
                ]])
            )
            return
        
        text = "🗑 <b>Удаление фото</b>\n\nВыберите фото для удаления:"
        
        keyboard = []
        for i, photo in enumerate(portfolio_photos):
            caption_text = photo.caption[:30] + "..." if photo.caption and len(photo.caption) > 30 else (photo.caption or f"Фото {i+1}")
            keyboard.append([
                InlineKeyboardButton(
                    f"🗑 {caption_text}",
                    callback_data=f"portfolio_delete_confirm_{photo.id}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton("« Назад", callback_data="master_portfolio")])
        
        await query.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def portfolio_delete_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение удаления фото из портфолио"""
    query = update.callback_query
    await query.answer()
    
    photo_id = int(query.data.split('_')[3])
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        
        if not master:
            await query.message.edit_text("❌ Аккаунт не найден")
            return
        
        from bot.database.models import Portfolio
        photo = session.query(Portfolio).filter_by(id=photo_id, master_account_id=master.id).first()
        
        if not photo:
            await query.message.edit_text("❌ Фото не найдено")
            return
        
        # Удаляем фото
        if delete_portfolio_photo(session, photo_id):
            await query.message.edit_text("✅ Фото удалено из портфолио")
            
            # Возвращаемся к портфолио
            query.data = "master_portfolio"
            await master_portfolio(update, context)
        else:
            await query.message.edit_text("❌ Ошибка при удалении фото")

