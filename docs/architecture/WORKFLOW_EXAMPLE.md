# 📝 Пример использования Workflow

## Базовый пример: Добавление услуги

### До (старый подход)

```python
# Жестко закодированные состояния
WAITING_CATEGORY = 3
WAITING_SERVICE_NAME = 5
WAITING_SERVICE_PRICE = 6

# ConversationHandler с жестко заданным порядком
add_service_conversation = ConversationHandler(
    entry_points=[CallbackQueryHandler(add_service_start, pattern='^add_service$')],
    states={
        WAITING_CATEGORY: [
            CallbackQueryHandler(service_category_selected, pattern=r'^service_category_.*$')
        ],
        WAITING_SERVICE_NAME: [
            MessageHandler(filters.TEXT, receive_service_name)
        ],
        WAITING_SERVICE_PRICE: [
            MessageHandler(filters.TEXT, receive_service_price)
        ]
    }
)
```

**Проблемы:**
- Чтобы изменить порядок шагов, нужно менять код в нескольких местах
- Чтобы добавить шаг, нужно менять состояния, обработчики и связи
- Сложно тестировать отдельные шаги

### После (новый подход)

```python
# Декларативное описание в одном месте
workflow = Workflow(
    name="add_service",
    entry_point="category",
    steps={
        "category": Step(
            id="category",
            type=StepType.CALLBACK,
            message="Выберите категорию:",
            next_step="name",  # Легко изменить порядок!
            data_key="category_id"
        ),
        "name": Step(
            id="name",
            type=StepType.INPUT,
            message="Введите название:",
            validator=lambda text, ctx: True if text else "Ошибка",
            next_step="price",  # Легко изменить порядок!
            data_key="name"
        ),
        "price": Step(
            id="price",
            type=StepType.INPUT,
            message="Введите цену:",
            validator=validate_price,
            next_step=None  # Конец
        )
    }
)
```

**Преимущества:**
- ✅ Изменить порядок - просто поменять `next_step`
- ✅ Добавить шаг - добавить новый Step в словарь
- ✅ Удалить шаг - удалить из словаря
- ✅ Все описано в одном месте

## Пример: Изменение порядка шагов

### Было: category → name → price
### Стало: name → category → price

**Старый подход:**
```python
# Нужно изменить:
# 1. Порядок в ConversationHandler
# 2. Функции обработчики
# 3. Связи между состояниями
# 4. Entry point
```

**Новый подход:**
```python
# Просто меняем next_step:
steps={
    "name": Step(..., next_step="category"),  # Было: "price"
    "category": Step(..., next_step="price"),  # Было: "name"
    "price": Step(..., next_step=None)
}
entry_point="name"  # Было: "category"
```

## Пример: Добавление нового шага

### Нужно добавить шаг "описание" между name и price

**Старый подход:**
```python
# 1. Добавить новое состояние
WAITING_SERVICE_DESCRIPTION = 10

# 2. Добавить обработчик
async def receive_service_description(update, context):
    ...

# 3. Изменить ConversationHandler
states={
    WAITING_SERVICE_DESCRIPTION: [
        MessageHandler(filters.TEXT, receive_service_description)
    ],
    ...
}

# 4. Изменить предыдущий шаг
async def receive_service_name(update, context):
    ...
    return WAITING_SERVICE_DESCRIPTION  # Было: WAITING_SERVICE_PRICE
```

**Новый подход:**
```python
# Просто добавляем шаг и обновляем связи:
steps={
    "name": Step(..., next_step="description"),  # Было: "price"
    "description": Step(  # Новый шаг!
        id="description",
        type=StepType.INPUT,
        message="Введите описание:",
        next_step="price",
        data_key="description"
    ),
    "price": Step(...)
}
```

## Пример: Условные переходы

```python
steps={
    "category": Step(
        id="category",
        type=StepType.CALLBACK,
        next_step="check_template"  # Проверяем шаблоны
    ),
    "check_template": Step(
        id="check_template",
        type=StepType.CONDITIONAL,
        condition=lambda u, c: (
            "template" if has_templates(c.user_data['category']) 
            else "name"
        )
    ),
    "template": Step(..., next_step="price"),
    "name": Step(..., next_step="price")
}
```

## Пример: Пропуск шагов

```python
steps={
    "cooling": Step(
        id="cooling",
        type=StepType.INPUT,
        message="Время охлаждения:",
        skip_if=lambda u, c: c.user_data.get('skip_cooling', False),
        next_step=None
    )
}
```

## Регистрация и использование

```python
# 1. Регистрация workflow
from bot.workflows.add_service_workflow import create_add_service_workflow
workflow = create_add_service_workflow()
workflow_manager.register_workflow(workflow)

# 2. Запуск из обработчика
async def add_service_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await workflow_manager.start_workflow(update, context, "add_service")

# 3. Обработка ввода
async def handle_workflow_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await workflow_manager.handle_input(update, context)

# 4. Обработка callback
async def handle_workflow_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    return await workflow_manager.handle_callback(update, context, query.data)
```

