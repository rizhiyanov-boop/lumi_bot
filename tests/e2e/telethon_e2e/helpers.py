"""Вспомогательные функции для E2E-тестирования с Telethon"""
import asyncio
from typing import List, Optional, TYPE_CHECKING
from telethon import TelegramClient
from telethon.errors import MessageNotModifiedError, FloodWaitError
import logging

if TYPE_CHECKING:
    from telethon.tl.types import User, Channel

logger = logging.getLogger(__name__)

# Максимальное время ожидания при FloodWait (в секундах)
MAX_FLOOD_WAIT_TIME = 600  # 10 минут


async def _send_message_with_retry(
    client: TelegramClient,
    entity,
    message: str,
    max_retries: int = 3
):
    """
    Отправляет сообщение с автоматической обработкой FloodWait
    
    Args:
        client: Telethon клиент
        entity: Entity получателя
        message: Текст сообщения
        max_retries: Максимальное количество попыток
    
    Returns:
        Отправленное сообщение
    
    Raises:
        FloodWaitError: Если время ожидания превышает MAX_FLOOD_WAIT_TIME
    """
    for attempt in range(max_retries):
        try:
            return await client.send_message(entity, message)
        except FloodWaitError as e:
            wait_seconds = e.seconds
            
            if wait_seconds > MAX_FLOOD_WAIT_TIME:
                logger.error(
                    f"FloodWait слишком долгий: {wait_seconds}с (макс: {MAX_FLOOD_WAIT_TIME}с). "
                    f"Рекомендуется подождать или использовать другой аккаунт."
                )
                raise
            
            if attempt < max_retries - 1:
                logger.warning(
                    f"FloodWait: требуется подождать {wait_seconds}с. "
                    f"Автоматически ожидаем... (попытка {attempt + 1}/{max_retries})"
                )
                await asyncio.sleep(wait_seconds + 1)  # +1 для надежности
            else:
                logger.error(f"FloodWait: исчерпаны все попытки ({max_retries})")
                raise
    
    raise RuntimeError("Не удалось отправить сообщение после всех попыток")


async def _click_button_with_retry(
    client: TelegramClient,
    message,
    *args,
    max_retries: int = 3,
    **kwargs
):
    """
    Нажимает кнопку с автоматической обработкой FloodWait
    
    Args:
        client: Telethon клиент
        message: Сообщение с кнопками
        max_retries: Максимальное количество попыток
        *args, **kwargs: Аргументы для message.click()
    
    Returns:
        Результат нажатия кнопки
    
    Raises:
        FloodWaitError: Если время ожидания превышает MAX_FLOOD_WAIT_TIME
    """
    for attempt in range(max_retries):
        try:
            return await message.click(*args, **kwargs)
        except FloodWaitError as e:
            wait_seconds = e.seconds
            
            if wait_seconds > MAX_FLOOD_WAIT_TIME:
                logger.error(
                    f"FloodWait слишком долгий: {wait_seconds}с (макс: {MAX_FLOOD_WAIT_TIME}с)"
                )
                raise
            
            if attempt < max_retries - 1:
                logger.warning(
                    f"FloodWait при нажатии кнопки: ожидаем {wait_seconds}с... "
                    f"(попытка {attempt + 1}/{max_retries})"
                )
                await asyncio.sleep(wait_seconds + 1)
            else:
                logger.error(f"FloodWait: исчерпаны все попытки ({max_retries})")
                raise
    
    raise RuntimeError("Не удалось нажать кнопку после всех попыток")


async def send_message_and_wait(
    client: TelegramClient,
    entity,  # User | Channel
    message: str,
    wait_time: float = 10.0
) -> List:
    """
    Отправляет сообщение боту и ждет ответа
    
    Args:
        client: Telethon клиент
        entity: Entity бота (User или Channel)
        message: Текст сообщения для отправки
        wait_time: Время ожидания ответа в секундах
    
    Returns:
        Список последних сообщений от бота (только сообщения от бота, не наши)
    """
    # Получаем нашу информацию
    me = await client.get_me()
    our_id = me.id
    logger.info(f"Our Telegram ID: {our_id}, username: @{me.username}")
    
    # Получаем информацию о боте
    bot_info = await client.get_entity(entity)
    logger.info(f"Bot entity: ID={bot_info.id}, username=@{getattr(bot_info, 'username', 'N/A')}, first_name={getattr(bot_info, 'first_name', 'N/A')}")
    
    # Получаем последние сообщения ДО отправки, чтобы знать, какие были до
    messages_before = await client.get_messages(entity, limit=10)
    last_message_id_before = messages_before[0].id if messages_before else 0
    logger.info(f"Last message ID before: {last_message_id_before}, total messages before: {len(messages_before)}")
    
    # Отправляем сообщение с обработкой FloodWait
    logger.info(f"Sending message to bot: '{message}'")
    sent_msg = await _send_message_with_retry(client, entity, message)
    logger.info(f"Message sent successfully, message ID: {sent_msg.id}, waiting {wait_time} seconds for response...")
    
    # Ждем ответа с периодической проверкой новых сообщений
    start_time = asyncio.get_event_loop().time()
    messages = []
    check_count = 0
    while (asyncio.get_event_loop().time() - start_time) < wait_time:
        await asyncio.sleep(2)  # Проверяем каждые 2 секунды
        check_count += 1
        elapsed = asyncio.get_event_loop().time() - start_time
        logger.info(f"Check #{check_count} ({elapsed:.1f}s elapsed): Getting messages from bot...")
        
        # Получаем новые сообщения
        new_messages = await client.get_messages(entity, limit=20)
        logger.info(f"Retrieved {len(new_messages)} messages from chat")
        
        # Фильтруем только новые сообщения от бота
        logger.info(f"Analyzing {len(new_messages)} messages, looking for messages with ID > {last_message_id_before}")
        for msg in new_messages:
            msg_sender_id = getattr(msg, 'sender_id', None)
            msg_out = getattr(msg, 'out', False)
            msg_from_id = getattr(msg, 'from_id', None)
            msg_peer_id = getattr(msg, 'peer_id', None)
            
            # Логируем все сообщения для диагностики
            logger.info(f"Message ID={msg.id}, sender_id={msg_sender_id}, from_id={msg_from_id}, out={msg_out}, peer_id={msg_peer_id}, text={msg.message[:50] if msg.message else 'None'}")
            
            # Проверяем, является ли это сообщением от бота
            is_from_bot = False
            if hasattr(bot_info, 'id'):
                bot_id = bot_info.id
                if msg_sender_id == bot_id:
                    is_from_bot = True
                elif hasattr(msg_from_id, 'user_id') and msg_from_id.user_id == bot_id:
                    is_from_bot = True
                elif hasattr(msg_from_id, 'channel_id') and msg_from_id.channel_id == bot_id:
                    is_from_bot = True
            
            logger.info(f"  -> is_from_bot={is_from_bot}, ID > last? {msg.id > last_message_id_before}")
            
            # Пропускаем наши собственные сообщения
            if msg_out:
                logger.debug(f"Skipping our outgoing message: {msg.id}")
                continue
            if msg_sender_id == our_id:
                logger.debug(f"Skipping our message by sender_id: {msg.id}")
                continue
            
            # Проверяем, новое ли это сообщение
            if msg.id > last_message_id_before:
                if msg not in messages:
                    messages.append(msg)
                    logger.info(f"✓ Found new bot message: ID={msg.id}, sender_id={msg_sender_id}, text={msg.message[:50] if msg.message else 'None'}")
        
        # Если нашли новые сообщения, можно выйти раньше
        if messages:
            logger.info(f"Found {len(messages)} new bot message(s), stopping wait")
            break
        
        logger.debug(f"No new bot messages found in check #{check_count}")
    
    # Если не нашли через ожидание, получаем все сообщения
    if not messages:
        logger.warning("No new messages found during wait, getting all messages...")
        messages = await client.get_messages(entity, limit=20)
    
    # Фильтруем: оставляем только сообщения от бота (не от нас) и новые
    bot_messages = []
    for msg in messages:
        # Логируем для отладки
        logger.debug(f"Message ID: {msg.id}, Sender ID: {msg.sender_id}, Our ID: {our_id}, Text: {msg.message[:50] if msg.message else 'None'}")
        
        # Пропускаем наше собственное сообщение (проверяем по sender_id или out)
        if hasattr(msg, 'out') and msg.out:
            logger.debug(f"Skipping our own message: {msg.id}")
            continue
        if hasattr(msg, 'sender_id') and msg.sender_id == our_id:
            logger.debug(f"Skipping our own message by sender_id: {msg.id}")
            continue
        
        # Пропускаем старые сообщения
        if msg.id <= last_message_id_before:
            logger.debug(f"Skipping old message: {msg.id} <= {last_message_id_before}")
            continue
        
        # Добавляем сообщения от бота
        logger.debug(f"Adding bot message: {msg.id}, text: {msg.message[:50] if msg.message else 'None'}")
        bot_messages.append(msg)
    
    # Если не нашли новых сообщений от бота, возвращаем последние сообщения от бота
    if not bot_messages:
        logger.warning("No new bot messages found, looking for any bot messages...")
        for msg in messages:
            # Пропускаем наши сообщения
            if hasattr(msg, 'out') and msg.out:
                continue
            if hasattr(msg, 'sender_id') and msg.sender_id == our_id:
                continue
            logger.debug(f"Adding any bot message: {msg.id}, text: {msg.message[:50] if msg.message else 'None'}")
            bot_messages.append(msg)
    
    # Сортируем по ID (новые первыми)
    bot_messages.sort(key=lambda x: x.id, reverse=True)
    
    if bot_messages:
        logger.info(f"Returning {len(bot_messages)} bot messages, first: {bot_messages[0].message[:50] if bot_messages[0].message else 'None'}")
    else:
        logger.warning("No bot messages found at all!")
    
    return bot_messages if bot_messages else messages[:1]


async def get_last_message(
    client: TelegramClient,
    entity,  # User | Channel
    limit: int = 1
) -> Optional:
    """
    Получает последнее сообщение от бота
    
    Args:
        client: Telethon клиент
        entity: Entity бота
        limit: Количество сообщений для получения
    
    Returns:
        Последнее сообщение или None
    """
    messages = await client.get_messages(entity, limit=limit)
    if messages:
        return messages[0]
    return None


async def wait_for_message(
    client: TelegramClient,
    entity,  # User | Channel
    expected_text: str = None,
    timeout: float = 10.0,
    check_interval: float = 0.5
) -> Optional:
    """
    Ждет сообщения от бота с ожидаемым текстом
    
    Args:
        client: Telethon клиент
        entity: Entity бота
        expected_text: Ожидаемый текст в сообщении (опционально)
        timeout: Таймаут ожидания в секундах
        check_interval: Интервал проверки в секундах
    
    Returns:
        Найденное сообщение или None
    """
    start_time = asyncio.get_event_loop().time()
    
    while (asyncio.get_event_loop().time() - start_time) < timeout:
        messages = await client.get_messages(entity, limit=1)
        
        if messages:
            message = messages[0]
            
            if expected_text:
                if expected_text.lower() in message.message.lower():
                    return message
            else:
                return message
        
        await asyncio.sleep(check_interval)
    
    return None


async def click_button(
    client: TelegramClient,
    message,
    row: int = 0,
    col: int = 0,
    wait_time: float = 2.0
) -> Optional:
    """
    Нажимает inline-кнопку в сообщении
    
    Args:
        client: Telethon клиент
        message: Сообщение с кнопками
        row: Номер строки кнопки (начиная с 0)
        col: Номер столбца кнопки (начиная с 0)
        wait_time: Время ожидания ответа после нажатия
    
    Returns:
        Новое сообщение после нажатия кнопки или None
    """
    if not message.reply_markup:
        logger.warning("Сообщение не содержит кнопок")
        return None
    
    try:
        # Получаем кнопку по координатам
        buttons = message.reply_markup.rows
        if row >= len(buttons):
            logger.warning(f"Строка {row} не существует. Всего строк: {len(buttons)}")
            return None
        
        button_row = buttons[row]
        # Обрабатываем разные типы строк кнопок
        if hasattr(button_row, 'buttons'):
            button_list = button_row.buttons
        elif hasattr(button_row, '__iter__'):
            button_list = list(button_row)
        else:
            button_list = list(button_row)
        
        if col >= len(button_list):
            logger.warning(f"Столбец {col} не существует. Всего столбцов: {len(button_list)}")
            return None
        
        button = button_list[col]
        
        # Нажимаем кнопку (передаем индекс кнопки)
        # Проверяем, есть ли у кнопки data (inline кнопка)
        if hasattr(button, 'data') and button.data:
            await _click_button_with_retry(client, message, data=button.data)
        else:
            # Обычная кнопка - отправляем текст
            await _send_message_with_retry(client, message.peer_id, button.text)
        await asyncio.sleep(wait_time)
        
        # Получаем обновленное сообщение
        updated_messages = await client.get_messages(message.peer_id, limit=1)
        if updated_messages:
            return updated_messages[0]
        
        return None
        
    except MessageNotModifiedError:
        # Сообщение не изменилось после нажатия кнопки
        logger.debug("Сообщение не изменилось после нажатия кнопки")
        return message
    except Exception as e:
        logger.error(f"Ошибка при нажатии кнопки: {e}")
        return None


async def click_button_by_text(
    client: TelegramClient,
    message,
    button_text: str,
    wait_time: float = 2.0
) -> Optional:
    """
    Нажимает inline-кнопку по тексту
    
    Args:
        client: Telethon клиент
        message: Сообщение с кнопками
        button_text: Текст кнопки для поиска
        wait_time: Время ожидания ответа после нажатия
    
    Returns:
        Новое сообщение после нажатия кнопки или None
    """
    if not message.reply_markup:
        logger.warning("Сообщение не содержит кнопок")
        return None
    
    try:
        # Ищем кнопку по тексту
        buttons = message.reply_markup.rows
        for row_idx, button_row in enumerate(buttons):
            # Обрабатываем разные типы строк кнопок
            if hasattr(button_row, 'buttons'):
                button_list = button_row.buttons
            elif hasattr(button_row, '__iter__'):
                button_list = list(button_row)
            else:
                button_list = list(button_row)
            
            for col_idx, button in enumerate(button_list):
                if button_text.lower() in button.text.lower():
                    # Нажимаем найденную кнопку (передаем callback_data)
                    # Проверяем, есть ли у кнопки data (inline кнопка)
                    if hasattr(button, 'data') and button.data:
                        await _click_button_with_retry(client, message, data=button.data)
                    else:
                        # Обычная кнопка - отправляем текст
                        await _send_message_with_retry(client, message.peer_id, button.text)
                    await asyncio.sleep(wait_time)
                    
                    # Получаем обновленное сообщение
                    updated_messages = await client.get_messages(message.peer_id, limit=1)
                    if updated_messages:
                        return updated_messages[0]
                    
                    return None
        
        logger.warning(f"Кнопка с текстом '{button_text}' не найдена")
        return None
        
    except Exception as e:
        logger.error(f"Ошибка при поиске и нажатии кнопки: {e}")
        return None


async def get_buttons_text(message) -> List[List[str]]:
    """
    Получает тексты всех кнопок в сообщении
    
    Args:
        message: Сообщение с кнопками
    
    Returns:
        Двумерный список текстов кнопок (строки x столбцы)
    """
    if not message.reply_markup:
        return []
    
    buttons_text = []
    for button_row in message.reply_markup.rows:
        # Обрабатываем разные типы строк кнопок
        if hasattr(button_row, 'buttons'):
            row_texts = [button.text for button in button_row.buttons]
        elif hasattr(button_row, '__iter__'):
            row_texts = [button.text for button in button_row]
        else:
            row_texts = [button.text for button in list(button_row)]
        buttons_text.append(row_texts)
    
    return buttons_text


def assert_message_contains(message, text: str, case_sensitive: bool = False):
    """
    Проверяет, что сообщение содержит указанный текст
    
    Args:
        message: Сообщение для проверки
        text: Текст для поиска
        case_sensitive: Учитывать ли регистр
    
    Raises:
        AssertionError: Если текст не найден
    """
    if not message:
        raise AssertionError("Сообщение не найдено")
    
    message_text = message.message
    if not case_sensitive:
        message_text = message_text.lower()
        text = text.lower()
    
    assert text in message_text, f"Текст '{text}' не найден в сообщении: '{message.message}'"


def assert_has_buttons(message, min_buttons: int = 1):
    """
    Проверяет, что сообщение содержит кнопки
    
    Args:
        message: Сообщение для проверки
        min_buttons: Минимальное количество кнопок
    
    Raises:
        AssertionError: Если кнопок недостаточно
    """
    if not message:
        raise AssertionError("Сообщение не найдено")
    
    if not message.reply_markup:
        raise AssertionError("Сообщение не содержит кнопок")
    
    # Подсчитываем кнопки правильно для Telethon
    total_buttons = 0
    if hasattr(message.reply_markup, 'rows'):
        for row in message.reply_markup.rows:
            if hasattr(row, 'buttons'):
                total_buttons += len(row.buttons)
            elif hasattr(row, '__iter__'):
                total_buttons += sum(1 for _ in row)
            else:
                # Если это просто список
                total_buttons += len(list(row))
    
    assert total_buttons >= min_buttons, f"Ожидалось минимум {min_buttons} кнопок, найдено {total_buttons}"

