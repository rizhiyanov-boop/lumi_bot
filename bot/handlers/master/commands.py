"""Команды-обертки для обработчиков"""
from telegram import Update
from telegram.ext import ContextTypes
from .profile import master_profile
from .services import master_services
from .schedule import master_schedule
from .qr import master_qr
from .bookings import master_bookings


async def master_profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /profile - показать профиль"""
    if update.message:
        # Создаем фиктивный callback_query для использования существующего обработчика
        class FakeCallbackQuery:
            def __init__(self, message):
                self.message = message
                self.data = "master_profile"
            async def answer(self):
                pass
        
        update.callback_query = FakeCallbackQuery(update.message)
        await master_profile(update, context)
    else:
        await master_profile(update, context)


async def master_services_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /services - показать услуги"""
    if update.message:
        class FakeCallbackQuery:
            def __init__(self, message):
                self.message = message
                self.data = "master_services"
            async def answer(self):
                pass
        
        update.callback_query = FakeCallbackQuery(update.message)
        await master_services(update, context)
    else:
        await master_services(update, context)


async def master_schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /schedule - показать расписание"""
    if update.message:
        class FakeCallbackQuery:
            def __init__(self, message):
                self.message = message
                self.data = "master_schedule"
            async def answer(self):
                pass
        
        update.callback_query = FakeCallbackQuery(update.message)
        await master_schedule(update, context)
    else:
        await master_schedule(update, context)


async def master_qr_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /qr - показать QR код"""
    if update.message:
        class FakeCallbackQuery:
            def __init__(self, message):
                self.message = message
                self.data = "master_qr"
            async def answer(self):
                pass
        
        update.callback_query = FakeCallbackQuery(update.message)
        await master_qr(update, context)
    else:
        await master_qr(update, context)


async def master_bookings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /bookings - показать записи"""
    if update.message:
        class FakeCallbackQuery:
            def __init__(self, message):
                self.message = message
                self.data = "master_bookings"
            async def answer(self):
                pass
        
        update.callback_query = FakeCallbackQuery(update.message)
        await master_bookings(update, context)
    else:
        await master_bookings(update, context)

