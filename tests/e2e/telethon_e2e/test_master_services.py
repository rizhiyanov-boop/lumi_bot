"""E2E тесты добавления услуг мастером с Telethon"""
import pytest
import asyncio
import logging
from tests.e2e.telethon_e2e.helpers import (
    send_message_and_wait,
    click_button,
    click_button_by_text,
    assert_message_contains,
    assert_has_buttons,
    get_buttons_text
)

logger = logging.getLogger(__name__)


@pytest.mark.asyncio
@pytest.mark.e2e_telethon
@pytest.mark.slow
async def test_add_service_full_flow(
    telethon_client,
    test_master_bot,
    registered_master  # Используем fixture для быстрой регистрации
):
    """
    Тест полного флоу добавления услуги:
    1. Мастер уже зарегистрирован (через fixture registered_master)
    2. Переход в услуги
    3. Добавление услуги: категория → шаблон → название → цена → длительность
    """
    
    # Проверяем, что мастер зарегистрирован
    assert registered_master is not None, "Мастер не зарегистрирован"
    logger.info(f"Используем зарегистрированного мастера: {registered_master}")
    
    # Шаг 1: Переход в услуги
    # Должно появиться главное меню или анбординг
    messages = await telethon_client.get_messages(test_master_bot, limit=5)
    logger.warning(f"\n[DEBUG] Last 5 messages:")
    for i, msg in enumerate(messages):
        text_preview = (msg.message[:100] if msg.message else '<no text>').encode('ascii', errors='ignore').decode('ascii')
        logger.warning(f"  [{i}] buttons: {len(msg.buttons) if msg.buttons else 0} | text: {text_preview}")
    
    # Ищем первое сообщение с кнопками (это ответ бота)
    menu_message = None
    for msg in messages:
        if msg.buttons and len(msg.buttons) > 0:
            menu_message = msg
            break
    
    if not menu_message:
        # Если не нашли сообщение с кнопками, берем первое
        menu_message = messages[0]
    
    text_preview = (menu_message.message[:200] if menu_message.message else '<no text>').encode('ascii', errors='ignore').decode('ascii')
    logger.warning(f"\n[DEBUG] Menu message text: {text_preview}")
    
    # Ищем кнопку "Услуги" или "Добавить услугу"
    services_button_text = None
    buttons_text = await get_buttons_text(menu_message)
    
    logger.warning(f"[DEBUG] Menu buttons: {buttons_text}")
    
    for row in buttons_text:
        for button_text in row:
            if "услуг" in button_text.lower() or "добавить" in button_text.lower():
                services_button_text = button_text
                break
        if services_button_text:
            break
    
    if services_button_text:
        logger.warning(f"[DEBUG] Found services button: {services_button_text}")
        await click_button_by_text(telethon_client, menu_message, services_button_text)
        await asyncio.sleep(2)
    else:
        # Если не нашли кнопку, пробуем первую кнопку
        logger.warning(f"[DEBUG] Services button not found, clicking first button")
        await click_button(telethon_client, menu_message, 0, 0)
        await asyncio.sleep(2)
    
    # Шаг 3: Добавление услуги
    messages = await telethon_client.get_messages(test_master_bot, limit=1)
    services_message = messages[0]
    
    text_preview = (services_message.message[:200] if services_message.message else '<no text>').encode('ascii', errors='ignore').decode('ascii')
    logger.warning(f"\n[DEBUG] Services message text: {text_preview}")
    buttons_text = await get_buttons_text(services_message)
    logger.warning(f"[DEBUG] Services buttons: {buttons_text}")
    
    # Ищем кнопку "Добавить услугу"
    add_service_button = await click_button_by_text(
        telethon_client,
        services_message,
        "Добавить"
    )
    
    if not add_service_button:
        # Пробуем найти любую кнопку с "добавить" или "+"
        buttons_text = await get_buttons_text(services_message)
        for row_idx, row in enumerate(buttons_text):
            for col_idx, button_text in enumerate(row):
                if "добавить" in button_text.lower() or "+" in button_text:
                    logger.warning(f"[DEBUG] Found add button at [{row_idx}][{col_idx}]: {button_text}")
                    add_service_button = await click_button(
                        telethon_client,
                        services_message,
                        row_idx,
                        col_idx
                    )
                    break
            if add_service_button:
                break
    
    await asyncio.sleep(2)
    
    # Шаг 4: Выбор категории
    messages = await telethon_client.get_messages(test_master_bot, limit=1)
    category_message = messages[0]
    
    text_preview = (category_message.message[:200] if category_message.message else '<no text>').encode('ascii', errors='ignore').decode('ascii')
    logger.warning(f"\n[DEBUG] Category message text: {text_preview}")
    buttons_text = await get_buttons_text(category_message)
    logger.warning(f"[DEBUG] Category buttons: {buttons_text}")
    
    # Выбираем первую доступную категорию
    assert_has_buttons(category_message, min_buttons=1)
    await click_button(telethon_client, category_message, 0, 0)
    await asyncio.sleep(2)
    
    # Шаг 5: Выбор шаблона или создание с нуля
    messages = await telethon_client.get_messages(test_master_bot, limit=1)
    template_message = messages[0]
    
    text_preview = (template_message.message[:200] if template_message.message else '<no text>').encode('ascii', errors='ignore').decode('ascii')
    logger.warning(f"\n[DEBUG] Template message text: {text_preview}")
    buttons_text = await get_buttons_text(template_message)
    logger.warning(f"[DEBUG] Template buttons: {buttons_text}")
    
    # Выбираем "Создать с нуля" или первый шаблон
    create_from_scratch_button = await click_button_by_text(
        telethon_client,
        template_message,
        "Создать"
    )
    
    if not create_from_scratch_button:
        logger.warning(f"[DEBUG] 'Создать' button not found, clicking first button")
        # Пробуем первую кнопку
        await click_button(telethon_client, template_message, 0, 0)
        await asyncio.sleep(2)
    else:
        await asyncio.sleep(2)
    
    # Шаг 6: Ввод названия услуги
    messages = await telethon_client.get_messages(test_master_bot, limit=1)
    name_message = messages[0]
    
    test_service_name = "Тестовая услуга E2E"
    await send_message_and_wait(telethon_client, test_master_bot, test_service_name)
    await asyncio.sleep(2)
    
    # Шаг 7: Ввод цены
    messages = await telethon_client.get_messages(test_master_bot, limit=1)
    price_message = messages[0]
    
    test_price = "1500"
    await send_message_and_wait(telethon_client, test_master_bot, test_price)
    await asyncio.sleep(2)
    
    # Шаг 8: Выбор длительности
    messages = await telethon_client.get_messages(test_master_bot, limit=1)
    duration_message = messages[0]
    
    # Выбираем длительность (например, 60 минут)
    duration_button = await click_button_by_text(
        telethon_client,
        duration_message,
        "60"
    )
    
    if not duration_button:
        # Пробуем первую кнопку с длительностью
        assert_has_buttons(duration_message, min_buttons=1)
        await click_button(telethon_client, duration_message, 0, 0)
        await asyncio.sleep(2)
    else:
        await asyncio.sleep(2)
    
    # Проверяем, что услуга создана в БД
    me = await telethon_client.get_me()
    telegram_id = me.id
    
    from bot.database.db import get_session, get_master_by_telegram, get_services_by_master
    
    with get_session() as session:
        master = get_master_by_telegram(session, telegram_id)
        assert master is not None, "Мастер не найден"
        
        services = get_services_by_master(session, master.id, active_only=False)
        assert len(services) > 0, "Услуга не создана"
        
        # Проверяем данные услуги
        service = services[0]
        assert service.title == test_service_name, \
            f"Название услуги не совпадает. Ожидалось: {test_service_name}, получено: {service.title}"
        assert service.price == float(test_price), \
            f"Цена услуги не совпадает. Ожидалось: {test_price}, получено: {service.price}"

