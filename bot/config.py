"""Конфигурация бота"""
import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Bot Tokens
BOT_TOKEN = os.getenv('BOT_TOKEN')  # Токен мастер-бота
CLIENT_BOT_TOKEN = os.getenv('CLIENT_BOT_TOKEN')  # Токен клиентского бота

# Telegram Bot Usernames (без @)
CLIENT_BOT_USERNAME = os.getenv('CLIENT_BOT_USERNAME', '')  # Username клиентского бота для диплинков

# Database
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///database.db')

# Super admins (comma-separated IDs) - могут быть мастерами + видят статистику
SUPER_ADMINS = [int(id.strip()) for id in os.getenv('SUPER_ADMINS', '').split(',') if id.strip()]

# YooKassa Payment Configuration
YOOKASSA_SHOP_ID = os.getenv('YOOKASSA_SHOP_ID', '1200992')  # Тестовый shop ID
YOOKASSA_SECRET_KEY = os.getenv('YOOKASSA_SECRET_KEY', '')  # Секретный ключ из личного кабинета
YOOKASSA_API_URL = 'https://api.yookassa.ru/v3/payments'
YOOKASSA_TEST_MODE = os.getenv('YOOKASSA_TEST_MODE', 'true').lower() == 'true'

# Premium subscription prices (в рублях)
PREMIUM_PRICE = float(os.getenv('PREMIUM_PRICE', '299.00'))  # Цена премиума
PREMIUM_DURATION_DAYS = int(os.getenv('PREMIUM_DURATION_DAYS', '30'))  # Длительность подписки в днях

