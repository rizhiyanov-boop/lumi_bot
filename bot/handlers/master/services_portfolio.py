"""Управление портфолио услуги"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import ContextTypes, ConversationHandler
from bot.database.db import (
    get_session,
    get_master_by_telegram,
    get_portfolio_photos,
    get_portfolio_limit,
    add_portfolio_photo,
    delete_portfolio_photo,
    get_service_by_id,
)
from bot.utils.impersonation import get_master_telegram_id, get_impersonation_banner
from .common import WAITING_SERVICE_PORTFOLIO_PHOTO

logger = logging.getLogger(__name__)


async def service_portfolio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать портфолио услуги"""
    query = update.callback_query
    await query.answer()
    
    # Получаем ID услуги из callback_data: service_portfolio_123
    service_id = int(query.data.split('_')[2])
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        
        if not master:
            await query.message.edit_text("❌ Аккаунт не найден")
            return
        
        service = get_service_by_id(session, service_id)
        
        if not service or service.master_account_id != master.id:
            await query.message.edit_text("❌ Услуга не найдена")
            return
        
        portfolio_photos = get_portfolio_photos(session, service_id)
        current_count, max_photos = get_portfolio_limit(session, service_id)
        
        text = f"📸 <b>Портфолио услуги</b>\n\n"
        text += f"💼 <b>{service.title}</b>\n\n"
        text += f"Фото: {current_count}/{max_photos}\n\n"
        
        if portfolio_photos:
            text += f"У вас <b>{len(portfolio_photos)}</b> фото в портфолио этой услуги.\n\n"
            text += "Выберите действие:"
        else:
            text += "<i>Портфолио пусто. Добавьте фото для этой услуги!</i>"
        
        text += get_impersonation_banner(context)
        
        keyboard = []
        
        if portfolio_photos:
            keyboard.append([InlineKeyboardButton("👁 Просмотреть портфолио", callback_data=f"service_portfolio_view_{service_id}")])
        
        if current_count < max_photos:
            keyboard.append([InlineKeyboardButton("➕ Добавить фото", callback_data=f"service_portfolio_add_{service_id}")])
        
        if portfolio_photos:
            keyboard.append([InlineKeyboardButton("🗑 Удалить фото", callback_data=f"service_portfolio_delete_{service_id}")])
        
        keyboard.append([InlineKeyboardButton("« Назад", callback_data=f"edit_service_{service_id}")])
        
        await query.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def service_portfolio_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начать добавление фото в портфолио услуги"""
    query = update.callback_query
    await query.answer()
    
    # Получаем ID услуги из callback_data: service_portfolio_add_123
    service_id = int(query.data.split('_')[3])
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        
        if not master:
            await query.message.edit_text("❌ Аккаунт не найден")
            return
        
        service = get_service_by_id(session, service_id)
        
        if not service or service.master_account_id != master.id:
            await query.message.edit_text("❌ Услуга не найдена")
            return
        
        current_count, max_photos = get_portfolio_limit(session, service_id)
        
        if current_count >= max_photos:
            await query.message.edit_text(
                f"❌ Достигнут лимит портфолио ({max_photos} фото на услугу).\n\n"
                f"Вы можете добавить максимум {max_photos} фото для каждой услуги.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("« Назад", callback_data=f"service_portfolio_{service_id}")
                ]])
            )
            return
        
        text = f"📸 <b>Добавление фото в портфолио</b>\n\n"
        text += f"💼 Услуга: <b>{service.title}</b>\n\n"
        text += f"Отправьте фото для добавления в портфолио этой услуги.\n\n"
        text += f"Фото в портфолио: {current_count}/{max_photos}\n"
        text += f"Вы можете добавить еще {max_photos - current_count} фото."
        text += get_impersonation_banner(context)
        
        keyboard = [[InlineKeyboardButton("« Отмена", callback_data=f"service_portfolio_{service_id}")]]
        
        await query.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        context.user_data['uploading_photo_type'] = 'service_portfolio'
        context.user_data['service_portfolio_service_id'] = service_id


async def receive_service_portfolio_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить фото для портфолио услуги"""
    photo = update.message.photo[-1]
    file_id = photo.file_id
    
    service_id = context.user_data.get('service_portfolio_service_id')
    
    if not service_id:
        await update.message.reply_text("❌ Ошибка: не указана услуга")
        context.user_data.pop('uploading_photo_type', None)
        context.user_data.pop('service_portfolio_service_id', None)
        return ConversationHandler.END
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        
        if not master:
            await update.message.reply_text("❌ Аккаунт не найден")
            context.user_data.pop('uploading_photo_type', None)
            context.user_data.pop('service_portfolio_service_id', None)
            return ConversationHandler.END
        
        service = get_service_by_id(session, service_id)
        
        if not service or service.master_account_id != master.id:
            await update.message.reply_text("❌ Услуга не найдена")
            context.user_data.pop('uploading_photo_type', None)
            context.user_data.pop('service_portfolio_service_id', None)
            return ConversationHandler.END
        
        current_count, max_photos = get_portfolio_limit(session, service_id)
        
        if current_count >= max_photos:
            await update.message.reply_text(
                f"❌ Достигнут лимит портфолио ({max_photos} фото на услугу)."
            )
            context.user_data.pop('uploading_photo_type', None)
            context.user_data.pop('service_portfolio_service_id', None)
            return ConversationHandler.END
        
        # Получаем подпись к фото (если есть текст в сообщении)
        caption = update.message.caption if update.message.caption else None
        
        portfolio_photo = add_portfolio_photo(session, service_id, file_id, caption)
        
        if portfolio_photo:
            await update.message.reply_text(
                f"✅ Фото добавлено в портфолио услуги <b>{service.title}</b>!\n\n"
                f"Фото в портфолио: {current_count + 1}/{max_photos}",
                parse_mode='HTML'
            )
            
            # Возвращаемся к портфолио услуги
            class FakeCallbackQuery:
                def __init__(self, message):
                    self.message = message
                    self.data = f"service_portfolio_{service_id}"
                async def answer(self):
                    pass
            
            update.callback_query = FakeCallbackQuery(update.message)
            await service_portfolio(update, context)
        else:
            await update.message.reply_text("❌ Ошибка при добавлении фото в портфолио")
        
        context.user_data.pop('uploading_photo_type', None)
        context.user_data.pop('service_portfolio_service_id', None)
    
    return ConversationHandler.END


async def service_portfolio_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Просмотр портфолио услуги с навигацией"""
    query = update.callback_query
    await query.answer()
    
    # Получаем ID услуги из callback_data: service_portfolio_view_123
    service_id = int(query.data.split('_')[3])
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        
        if not master:
            await query.message.edit_text("❌ Аккаунт не найден")
            return
        
        service = get_service_by_id(session, service_id)
        
        if not service or service.master_account_id != master.id:
            await query.message.edit_text("❌ Услуга не найдена")
            return
        
        portfolio_photos = get_portfolio_photos(session, service_id)
        
        if not portfolio_photos:
            await query.message.edit_text(
                "📸 <b>Портфолио пусто</b>\n\nДобавьте фото в портфолио!",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("« Назад", callback_data=f"service_portfolio_{service_id}")
                ]])
            )
            return
        
        # Сохраняем данные для навигации
        context.user_data['service_portfolio_index'] = 0
        context.user_data['service_portfolio_photos'] = [p.id for p in portfolio_photos]
        context.user_data['service_portfolio_service_id'] = service_id
        
        # Отправляем первое фото
        first_photo = portfolio_photos[0]
        caption = f"📸 <b>Портфолио услуги</b>\n\n💼 <b>{service.title}</b>\n\n(1/{len(portfolio_photos)})"
        if first_photo.caption:
            caption += f"\n\n{first_photo.caption}"
        
        keyboard = []
        if len(portfolio_photos) > 1:
            keyboard.append([
                InlineKeyboardButton("▶️ Следующее", callback_data=f"service_portfolio_next_{service_id}")
            ])
        keyboard.append([
            InlineKeyboardButton("🗑 Удалить", callback_data=f"service_portfolio_delete_confirm_{first_photo.id}")
        ])
        keyboard.append([
            InlineKeyboardButton("« Назад", callback_data=f"service_portfolio_{service_id}")
        ])
        
        await query.message.delete()
        await query.message.chat.send_photo(
            photo=first_photo.file_id,
            caption=caption,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def service_portfolio_next(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Следующее фото в портфолио услуги"""
    query = update.callback_query
    await query.answer()
    
    # Получаем ID услуги из callback_data: service_portfolio_next_123
    service_id = int(query.data.split('_')[3])
    
    photo_ids = context.user_data.get('service_portfolio_photos', [])
    
    if not photo_ids:
        await query.message.edit_text("❌ Ошибка просмотра портфолио")
        return
    
    current_index = context.user_data.get('service_portfolio_index', 0)
    current_index = (current_index + 1) % len(photo_ids)
    context.user_data['service_portfolio_index'] = current_index
    
    with get_session() as session:
        from bot.database.models import Portfolio
        photo = session.query(Portfolio).filter_by(id=photo_ids[current_index]).first()
        service = get_service_by_id(session, service_id)
        
        if not photo or not service:
            await query.message.edit_text("❌ Фото не найдено")
            return
        
        caption = f"📸 <b>Портфолио услуги</b>\n\n💼 <b>{service.title}</b>\n\n({current_index + 1}/{len(photo_ids)})"
        if photo.caption:
            caption += f"\n\n{photo.caption}"
        
        keyboard = []
        if len(photo_ids) > 1:
            keyboard.append([
                InlineKeyboardButton("◀️ Предыдущее", callback_data=f"service_portfolio_prev_{service_id}"),
                InlineKeyboardButton("▶️ Следующее", callback_data=f"service_portfolio_next_{service_id}")
            ])
        keyboard.append([
            InlineKeyboardButton("🗑 Удалить", callback_data=f"service_portfolio_delete_confirm_{photo.id}")
        ])
        keyboard.append([
            InlineKeyboardButton("« Назад", callback_data=f"service_portfolio_{service_id}")
        ])
        
        await query.message.edit_media(
            media=InputMediaPhoto(media=photo.file_id, caption=caption, parse_mode='HTML'),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def service_portfolio_prev(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Предыдущее фото в портфолио услуги"""
    query = update.callback_query
    await query.answer()
    
    # Получаем ID услуги из callback_data: service_portfolio_prev_123
    service_id = int(query.data.split('_')[3])
    
    photo_ids = context.user_data.get('service_portfolio_photos', [])
    
    if not photo_ids:
        await query.message.edit_text("❌ Ошибка просмотра портфолио")
        return
    
    current_index = context.user_data.get('service_portfolio_index', 0)
    current_index = (current_index - 1) % len(photo_ids)
    context.user_data['service_portfolio_index'] = current_index
    
    with get_session() as session:
        from bot.database.models import Portfolio
        photo = session.query(Portfolio).filter_by(id=photo_ids[current_index]).first()
        service = get_service_by_id(session, service_id)
        
        if not photo or not service:
            await query.message.edit_text("❌ Фото не найдено")
            return
        
        caption = f"📸 <b>Портфолио услуги</b>\n\n💼 <b>{service.title}</b>\n\n({current_index + 1}/{len(photo_ids)})"
        if photo.caption:
            caption += f"\n\n{photo.caption}"
        
        keyboard = []
        if len(photo_ids) > 1:
            keyboard.append([
                InlineKeyboardButton("◀️ Предыдущее", callback_data=f"service_portfolio_prev_{service_id}"),
                InlineKeyboardButton("▶️ Следующее", callback_data=f"service_portfolio_next_{service_id}")
            ])
        keyboard.append([
            InlineKeyboardButton("🗑 Удалить", callback_data=f"service_portfolio_delete_confirm_{photo.id}")
        ])
        keyboard.append([
            InlineKeyboardButton("« Назад", callback_data=f"service_portfolio_{service_id}")
        ])
        
        await query.message.edit_media(
            media=InputMediaPhoto(media=photo.file_id, caption=caption, parse_mode='HTML'),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def service_portfolio_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начать удаление фото из портфолио услуги (показать список)"""
    query = update.callback_query
    await query.answer()
    
    # Получаем ID услуги из callback_data: service_portfolio_delete_123
    service_id = int(query.data.split('_')[3])
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        
        if not master:
            await query.message.edit_text("❌ Аккаунт не найден")
            return
        
        service = get_service_by_id(session, service_id)
        
        if not service or service.master_account_id != master.id:
            await query.message.edit_text("❌ Услуга не найдена")
            return
        
        portfolio_photos = get_portfolio_photos(session, service_id)
        
        if not portfolio_photos:
            await query.message.edit_text(
                "📸 <b>Портфолио пусто</b>",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("« Назад", callback_data=f"service_portfolio_{service_id}")
                ]])
            )
            return
        
        text = f"🗑 <b>Удаление фото</b>\n\n💼 Услуга: <b>{service.title}</b>\n\nВыберите фото для удаления:"
        
        keyboard = []
        for i, photo in enumerate(portfolio_photos):
            caption_text = photo.caption[:30] + "..." if photo.caption and len(photo.caption) > 30 else (photo.caption or f"Фото {i+1}")
            keyboard.append([
                InlineKeyboardButton(
                    f"🗑 {caption_text}",
                    callback_data=f"service_portfolio_delete_confirm_{photo.id}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton("« Назад", callback_data=f"service_portfolio_{service_id}")])
        
        await query.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def service_portfolio_delete_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение удаления фото из портфолио услуги"""
    query = update.callback_query
    await query.answer()
    
    photo_id = int(query.data.split('_')[4])
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        
        if not master:
            await query.message.edit_text("❌ Аккаунт не найден")
            return
        
        from bot.database.models import Portfolio
        photo = session.query(Portfolio).filter_by(id=photo_id).first()
        
        if not photo:
            await query.message.edit_text("❌ Фото не найдено")
            return
        
        service = get_service_by_id(session, photo.service_id)
        
        if not service or service.master_account_id != master.id:
            await query.message.edit_text("❌ Услуга не найдена")
            return
        
        # Удаляем фото
        if delete_portfolio_photo(session, photo_id):
            await query.message.edit_text("✅ Фото удалено из портфолио")
            
            # Возвращаемся к портфолио услуги
            query.data = f"service_portfolio_{photo.service_id}"
            await service_portfolio(update, context)
        else:
            await query.message.edit_text("❌ Ошибка при удалении фото")

