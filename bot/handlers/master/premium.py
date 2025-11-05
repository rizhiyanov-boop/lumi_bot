"""Управление премиум подпиской"""
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from bot.database.db import (
    get_session,
    get_master_by_telegram,
    update_master_subscription,
    create_payment_record,
    update_payment_status,
)
from bot.utils.impersonation import get_master_telegram_id, get_impersonation_banner
from bot.utils.yookassa_api import create_premium_payment, get_payment_status
from bot.config import CLIENT_BOT_USERNAME, PREMIUM_PRICE, PREMIUM_DURATION_DAYS

logger = logging.getLogger(__name__)


async def master_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Премиум подписка"""
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
        
        # Проверяем текущую подписку
        now = datetime.utcnow()
        is_premium = master.subscription_level == 'premium'
        is_expired = master.subscription_expires_at and master.subscription_expires_at < now
        
        text = "💎 <b>Премиум подписка</b>\n\n"
        
        if is_premium and not is_expired:
            expires_str = master.subscription_expires_at.strftime("%d.%m.%Y %H:%M") if master.subscription_expires_at else "Не указано"
            text += f"✅ У вас активна премиум подписка\n"
            text += f"📅 Истекает: {expires_str}\n\n"
            text += "<b>Преимущества премиум:</b>\n"
            text += "• До 50 фото в портфолио\n"
            text += "• Приоритетная поддержка\n"
            text += "• Расширенные возможности\n"
        elif is_premium and is_expired:
            text += "❌ Ваша премиум подписка истекла\n\n"
            text += f"<b>Премиум подписка на {PREMIUM_DURATION_DAYS} дней</b>\n"
            text += f"💰 Цена: {PREMIUM_PRICE}₽\n\n"
            text += "<b>Включает:</b>\n"
            text += "• До 50 фото в портфолио\n"
            text += "• Приоритетная поддержка\n"
            text += "• Расширенные возможности\n"
        else:
            text += f"<b>Премиум подписка на {PREMIUM_DURATION_DAYS} дней</b>\n"
            text += f"💰 Цена: {PREMIUM_PRICE}₽\n\n"
            text += "<b>Включает:</b>\n"
            text += "• До 50 фото в портфолио\n"
            text += "• Приоритетная поддержка\n"
            text += "• Расширенные возможности\n"
        
        text += get_impersonation_banner(context)
        
        keyboard = []
        
        if not is_premium or is_expired:
            keyboard.append([InlineKeyboardButton("💳 Оплатить премиум", callback_data="premium_pay")])
        
        # Проверяем наличие активных платежей
        from bot.database.models import Payment
        active_payments = session.query(Payment).filter_by(
            master_account_id=master.id,
            status='pending'
        ).all()
        
        if active_payments:
            keyboard.append([InlineKeyboardButton("🔄 Проверить статус оплаты", callback_data="premium_check_status")])
        
        keyboard.append([InlineKeyboardButton("« Назад", callback_data="master_settings")])
        
        if query:
            await query.message.edit_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
        elif update.message:
            await update.message.reply_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def premium_pay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Оплата премиума"""
    query = update.callback_query
    await query.answer()
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        
        if not master:
            await query.message.edit_text("❌ Аккаунт не найден")
            return
        
        # Проверяем, не активна ли уже подписка
        now = datetime.utcnow()
        if master.subscription_level == 'premium' and master.subscription_expires_at and master.subscription_expires_at > now:
            await query.message.edit_text(
                "✅ У вас уже активна премиум подписка!",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("« Назад", callback_data="master_premium")
                ]])
            )
            return
        
        # Создаем платеж
        return_url = f"https://t.me/{CLIENT_BOT_USERNAME}"  # URL для возврата после оплаты
        payment_data = create_premium_payment(master.id, return_url)
        
        if not payment_data:
            await query.message.edit_text(
                "❌ Ошибка при создании платежа. Попробуйте позже.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("« Назад", callback_data="master_premium")
                ]])
            )
            return
        
        payment_id = payment_data.get('id')
        confirmation_url = payment_data.get('confirmation', {}).get('confirmation_url')
        
        if not confirmation_url:
            await query.message.edit_text(
                "❌ Ошибка получения ссылки на оплату. Попробуйте позже.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("« Назад", callback_data="master_premium")
                ]])
            )
            return
        
        # Сохраняем платеж в базе
        payment_record = create_payment_record(
            session,
            master.id,
            payment_id,
            PREMIUM_PRICE,
            'premium'
        )
        
        if payment_record:
            text = f"💳 <b>Оплата премиум подписки</b>\n\n"
            text += f"💰 Сумма: {PREMIUM_PRICE}₽\n"
            text += f"📅 Срок: {PREMIUM_DURATION_DAYS} дней\n\n"
            text += "Нажмите на кнопку ниже, чтобы перейти к оплате:\n\n"
            text += "После оплаты вернитесь и нажмите «Проверить статус оплаты»"
            
            keyboard = [
                [InlineKeyboardButton("💳 Оплатить", url=confirmation_url)],
                [InlineKeyboardButton("🔄 Проверить статус оплаты", callback_data="premium_check_status")],
                [InlineKeyboardButton("« Назад", callback_data="master_premium")]
            ]
            
            await query.message.edit_text(
                text,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await query.message.edit_text(
                "❌ Ошибка при сохранении платежа. Попробуйте позже.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("« Назад", callback_data="master_premium")
                ]])
            )


async def premium_check_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверка статуса оплаты"""
    query = update.callback_query
    await query.answer()
    
    with get_session() as session:
        master = get_master_by_telegram(session, get_master_telegram_id(update, context))
        
        if not master:
            await query.message.edit_text("❌ Аккаунт не найден")
            return
        
        # Получаем последний платеж
        from bot.database.models import Payment
        payment = session.query(Payment).filter_by(
            master_account_id=master.id,
            status='pending'
        ).order_by(Payment.created_at.desc()).first()
        
        if not payment:
            await query.message.edit_text(
                "❌ Активных платежей не найдено",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("« Назад", callback_data="master_premium")
                ]])
            )
            return
        
        # Проверяем статус платежа в ЮKassa
        payment_status = get_payment_status(payment.payment_id)
        
        if not payment_status:
            await query.message.edit_text(
                "❌ Ошибка при проверке статуса платежа. Попробуйте позже.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔄 Проверить снова", callback_data="premium_check_status"),
                    InlineKeyboardButton("« Назад", callback_data="master_premium")
                ]])
            )
            return
        
        status = payment_status.get('status', 'unknown')
        
        if status == 'succeeded':
            # Платеж успешен - активируем подписку
            expires_at = datetime.utcnow() + timedelta(days=PREMIUM_DURATION_DAYS)
            
            # Обновляем статус платежа
            update_payment_status(session, payment.id, 'completed')
            
            # Обновляем подписку мастера
            update_master_subscription(
                session,
                master.id,
                'premium',
                expires_at
            )
            
            await query.message.edit_text(
                f"✅ <b>Платеж успешно обработан!</b>\n\n"
                f"💎 Премиум подписка активирована на {PREMIUM_DURATION_DAYS} дней.\n"
                f"📅 Истекает: {expires_at.strftime('%d.%m.%Y %H:%M')}\n\n"
                f"Теперь вам доступны все премиум возможности!",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("« Назад", callback_data="master_premium")
                ]])
            )
        elif status == 'pending':
            await query.message.edit_text(
                "⏳ <b>Оплата в обработке</b>\n\n"
                "Платеж еще не обработан. Подождите несколько минут и проверьте снова.",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔄 Проверить снова", callback_data="premium_check_status"),
                    InlineKeyboardButton("« Назад", callback_data="master_premium")
                ]])
            )
        elif status == 'canceled':
            update_payment_status(session, payment.id, 'cancelled')
            await query.message.edit_text(
                "❌ <b>Платеж отменен</b>\n\n"
                "Платеж был отменен. Вы можете создать новый платеж.",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("💳 Оплатить премиум", callback_data="premium_pay"),
                    InlineKeyboardButton("« Назад", callback_data="master_premium")
                ]])
            )
        else:
            await query.message.edit_text(
                f"❌ <b>Неизвестный статус платежа</b>\n\n"
                f"Статус: {status}\n\n"
                f"Попробуйте проверить снова позже.",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔄 Проверить снова", callback_data="premium_check_status"),
                    InlineKeyboardButton("« Назад", callback_data="master_premium")
                ]])
            )

