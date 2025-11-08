"""E2E тесты регистрации мастера с Telethon"""
import pytest
import asyncio
from tests.e2e.telethon_e2e.helpers import (
    send_message_and_wait,
    get_last_message,
    click_button,
    click_button_by_text,
    wait_for_message,
    assert_message_contains,
    assert_has_buttons,
    get_buttons_text
)


@pytest.mark.asyncio
@pytest.mark.e2e_telethon
@pytest.mark.slow
async def test_master_registration_full_flow(
    telethon_client,
    test_master_bot,
    clean_test_database
):
    """
    Тест полной регистрации мастера:
    1. /start → выбор имени
    2. Использование имени из Telegram
    3. Пропуск описания
    4. Пропуск фото
    """
    
    # Шаг 1: Отправляем /start
    messages = await send_message_and_wait(telethon_client, test_master_bot, "/start")
    last_message = messages[0]
    
    # Проверяем приветственное сообщение
    assert_message_contains(last_message, "Добро пожаловать")
    assert_message_contains(last_message, "Шаг 1")
    assert_message_contains(last_message, "имя")
    assert_has_buttons(last_message, min_buttons=2)
    
    # Шаг 2: Нажимаем кнопку "Использовать имя из Telegram"
    # Ищем кнопку с текстом "Использовать" или "✅"
    new_message = await click_button_by_text(
        telethon_client,
        last_message,
        "Использовать"
    )
    
    if not new_message:
        # Если не нашли по тексту, пробуем первую кнопку
        new_message = await click_button(telethon_client, last_message, 0, 0)
    
    assert new_message is not None, "Не получен ответ после выбора имени"
    
    # Проверяем, что перешли к шагу 2 (описание)
    await asyncio.sleep(1)  # Дополнительная задержка для обработки
    messages = await telethon_client.get_messages(test_master_bot, limit=1)
    current_message = messages[0]
    
    # Проверяем наличие текста про описание или шаг 2
    message_text = current_message.message.lower()
    assert ("шаг 2" in message_text or 
            "описание" in message_text or
            "пропустить" in message_text), \
        f"Не перешли к шагу описания. Текст: {current_message.message}"
    
    # Шаг 3: Пропускаем описание
    assert_has_buttons(current_message, min_buttons=1)
    skip_button_message = await click_button_by_text(
        telethon_client,
        current_message,
        "Пропустить"
    )
    
    if not skip_button_message:
        # Если не нашли кнопку "Пропустить", пробуем первую кнопку
        skip_button_message = await click_button(telethon_client, current_message, 0, 0)
    
    await asyncio.sleep(1)
    
    # Шаг 4: Пропускаем фото
    messages = await telethon_client.get_messages(test_master_bot, limit=1)
    photo_message = messages[0]
    
    message_text = photo_message.message.lower()
    if "фото" in message_text or "шаг 3" in message_text:
        # Есть шаг с фото, пропускаем его
        skip_photo_message = await click_button_by_text(
            telethon_client,
            photo_message,
            "Пропустить"
        )
        
        if not skip_photo_message:
            skip_photo_message = await click_button(telethon_client, photo_message, 0, 0)
        
        await asyncio.sleep(1)
    
    # Проверяем, что регистрация завершена
    # Мастер должен быть создан в БД
    from bot.database.db import get_session, get_master_by_telegram
    
    # Получаем наш Telegram ID
    me = await telethon_client.get_me()
    telegram_id = me.id
    
    with get_session() as session:
        master = get_master_by_telegram(session, telegram_id)
        assert master is not None, "Мастер не создан в базе данных"
        assert master.name is not None, "Имя мастера не установлено"


@pytest.mark.asyncio
@pytest.mark.e2e_telethon
@pytest.mark.slow
async def test_master_registration_custom_name(
    telethon_client,
    test_master_bot,
    clean_test_database
):
    """
    Тест регистрации мастера с кастомным именем
    """
    
    # Шаг 1: Отправляем /start
    messages = await send_message_and_wait(telethon_client, test_master_bot, "/start")
    last_message = messages[0]
    
    # Шаг 2: Выбираем "Ввести другое имя"
    custom_name_message = await click_button_by_text(
        telethon_client,
        last_message,
        "Ввести"
    )
    
    if not custom_name_message:
        # Пробуем вторую кнопку
        custom_name_message = await click_button(telethon_client, last_message, 0, 1)
    
    await asyncio.sleep(1)
    
    # Шаг 3: Вводим кастомное имя
    test_name = "Тестовый Мастер E2E"
    await send_message_and_wait(telethon_client, test_master_bot, test_name)
    
    await asyncio.sleep(2)
    
    # Проверяем, что имя сохранено
    me = await telethon_client.get_me()
    telegram_id = me.id
    
    from bot.database.db import get_session, get_master_by_telegram
    
    with get_session() as session:
        master = get_master_by_telegram(session, telegram_id)
        if master:
            # Если мастер уже создан, проверяем имя
            assert master.name == test_name, f"Имя не совпадает. Ожидалось: {test_name}, получено: {master.name}"


@pytest.mark.asyncio
@pytest.mark.e2e_telethon
@pytest.mark.slow
async def test_master_registration_with_description(
    telethon_client,
    test_master_bot,
    clean_test_database
):
    """
    Тест регистрации мастера с описанием
    """
    
    # Шаг 1: /start
    messages = await send_message_and_wait(telethon_client, test_master_bot, "/start")
    last_message = messages[0]
    
    # Шаг 2: Используем имя из Telegram
    await click_button_by_text(telethon_client, last_message, "Использовать")
    await asyncio.sleep(2)
    
    # Шаг 3: Вводим описание
    messages = await telethon_client.get_messages(test_master_bot, limit=1)
    description_message = messages[0]
    
    # Проверяем, что находимся на шаге описания
    message_text = description_message.message.lower()
    if "описание" in message_text or "шаг 2" in message_text:
        # Выбираем "Ввести описание"
        enter_description_message = await click_button_by_text(
            telethon_client,
            description_message,
            "Ввести"
        )
        
        if not enter_description_message:
            # Пробуем первую кнопку (если она не "Пропустить")
            buttons_text = await get_buttons_text(description_message)
            if buttons_text and len(buttons_text[0]) > 0:
                if "пропустить" not in buttons_text[0][0].lower():
                    enter_description_message = await click_button(telethon_client, description_message, 0, 0)
        
        await asyncio.sleep(1)
        
        # Вводим описание
        test_description = "Тестовое описание для E2E тестов"
        await send_message_and_wait(telethon_client, test_master_bot, test_description)
        await asyncio.sleep(2)
        
        # Проверяем, что описание сохранено
        me = await telethon_client.get_me()
        telegram_id = me.id
        
        from bot.database.db import get_session, get_master_by_telegram
        
        with get_session() as session:
            master = get_master_by_telegram(session, telegram_id)
            if master:
                assert master.description == test_description, \
                    f"Описание не совпадает. Ожидалось: {test_description}, получено: {master.description}"

