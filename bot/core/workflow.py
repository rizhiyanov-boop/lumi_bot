"""Модуль для декларативного управления workflow и шагами в боте"""
from typing import Dict, List, Callable, Optional, Any
from enum import Enum
from dataclasses import dataclass, field
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import logging

logger = logging.getLogger(__name__)


class StepType(Enum):
    """Типы шагов"""
    MESSAGE = "message"  # Просто показать сообщение
    INPUT = "input"  # Запросить ввод текста
    CALLBACK = "callback"  # Показать кнопки с callback
    CONDITIONAL = "conditional"  # Условный переход
    ACTION = "action"  # Выполнить действие


@dataclass
class Step:
    """Описание одного шага в workflow"""
    id: str  # Уникальный идентификатор шага
    type: StepType  # Тип шага
    title: str  # Заголовок шага
    message: str  # Сообщение для пользователя
    handler: Optional[Callable] = None  # Функция-обработчик
    validator: Optional[Callable] = None  # Функция валидации
    next_step: Optional[str] = None  # ID следующего шага
    condition: Optional[Callable] = None  # Условие для перехода (для CONDITIONAL)
    keyboard: Optional[List[List[Dict[str, str]]]] = None  # Кнопки (для CALLBACK)
    data_key: Optional[str] = None  # Ключ в context.user_data для сохранения данных
    default_value: Any = None  # Значение по умолчанию
    skip_if: Optional[Callable] = None  # Условие для пропуска шага


@dataclass
class Workflow:
    """Описание workflow (последовательности шагов)"""
    name: str  # Имя workflow
    entry_point: str  # ID первого шага
    steps: Dict[str, Step] = field(default_factory=dict)  # Словарь шагов по ID
    fallbacks: List[str] = field(default_factory=list)  # ID шагов для отмены
    context_keys: List[str] = field(default_factory=list)  # Ключи для очистки в context.user_data


class WorkflowManager:
    """Менеджер для управления workflow"""
    
    def __init__(self):
        self.workflows: Dict[str, Workflow] = {}
        self.current_workflows: Dict[int, str] = {}  # user_id -> workflow_name
    
    def register_workflow(self, workflow: Workflow):
        """Зарегистрировать workflow"""
        self.workflows[workflow.name] = workflow
        logger.info(f"Workflow '{workflow.name}' registered with {len(workflow.steps)} steps")
    
    async def start_workflow(self, update: Update, context: ContextTypes.DEFAULT_TYPE, workflow_name: str):
        """Начать workflow"""
        workflow = self.workflows.get(workflow_name)
        if not workflow:
            logger.error(f"Workflow '{workflow_name}' not found")
            return None
        
        user_id = update.effective_user.id
        self.current_workflows[user_id] = workflow_name
        
        # Инициализируем контекст
        context.user_data['workflow_name'] = workflow_name
        context.user_data['workflow_step'] = workflow.entry_point
        context.user_data['workflow_data'] = {}
        
        # Переходим к первому шагу
        return await self.process_step(update, context, workflow.entry_point)
    
    async def process_step(self, update: Update, context: ContextTypes.DEFAULT_TYPE, step_id: str):
        """Обработать шаг"""
        workflow_name = context.user_data.get('workflow_name')
        if not workflow_name:
            logger.error("No active workflow")
            return None
        
        workflow = self.workflows.get(workflow_name)
        if not workflow:
            logger.error(f"Workflow '{workflow_name}' not found")
            return None
        
        step = workflow.steps.get(step_id)
        if not step:
            logger.error(f"Step '{step_id}' not found in workflow '{workflow_name}'")
            return None
        
        # Проверяем условие пропуска
        if step.skip_if:
            try:
                if step.skip_if(update, context):
                    logger.info(f"Skipping step '{step_id}' due to skip_if condition")
                    return await self._goto_next_step(update, context, step)
            except Exception as e:
                logger.error(f"Error in skip_if for step '{step_id}': {e}")
        
        # Выполняем обработчик шага, если он есть
        if step.handler:
            try:
                # Проверяем, является ли функция async
                import inspect
                if inspect.iscoroutinefunction(step.handler):
                    result = await step.handler(update, context)
                else:
                    result = step.handler(update, context)
                if result:
                    return result
            except Exception as e:
                logger.error(f"Error in handler for step '{step_id}': {e}")
                return None
        
        # Показываем сообщение и клавиатуру
        keyboard = self._build_keyboard(step, context)
        
        query = update.callback_query if hasattr(update, 'callback_query') and update.callback_query else None
        
        if query:
            await query.message.edit_text(
                step.message,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None
            )
        else:
            await update.message.reply_text(
                step.message,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None
            )
        
        # Возвращаем состояние для ConversationHandler
        return step_id
    
    def _build_keyboard(self, step: Step, context: ContextTypes.DEFAULT_TYPE) -> List[List[InlineKeyboardButton]]:
        """Построить клавиатуру для шага"""
        keyboard = []
        
        if step.keyboard:
            for row in step.keyboard:
                button_row = []
                for btn in row:
                    callback_data = btn.get('callback_data', '')
                    text = btn.get('text', '')
                    if callback_data and text:
                        button_row.append(InlineKeyboardButton(text, callback_data=callback_data))
                if button_row:
                    keyboard.append(button_row)
        
        return keyboard
    
    async def _goto_next_step(self, update: Update, context: ContextTypes.DEFAULT_TYPE, current_step: Step):
        """Перейти к следующему шагу"""
        if current_step.type == StepType.CONDITIONAL and current_step.condition:
            # Определяем следующий шаг по условию
            try:
                next_step_id = current_step.condition(update, context)
                if next_step_id:
                    context.user_data['workflow_step'] = next_step_id
                    return await self.process_step(update, context, next_step_id)
            except Exception as e:
                logger.error(f"Error in condition for step '{current_step.id}': {e}")
        
        if current_step.next_step:
            context.user_data['workflow_step'] = current_step.next_step
            return await self.process_step(update, context, current_step.next_step)
        
        # Workflow завершен
        return await self._finish_workflow(update, context)
    
    async def handle_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработать ввод пользователя"""
        workflow_name = context.user_data.get('workflow_name')
        step_id = context.user_data.get('workflow_step')
        
        if not workflow_name or not step_id:
            return None
        
        workflow = self.workflows.get(workflow_name)
        if not workflow:
            return None
        
        step = workflow.steps.get(step_id)
        
        if not step or step.type != StepType.INPUT:
            return None
        
        # Сохраняем данные
        user_input = update.message.text.strip()
        
        # Валидация
        if step.validator:
            try:
                validation_result = step.validator(user_input, context)
                if validation_result is not True:
                    # Ошибка валидации
                    await update.message.reply_text(
                        validation_result if isinstance(validation_result, str) else "❌ Неверный ввод. Попробуйте снова:"
                    )
                    return step_id
            except Exception as e:
                logger.error(f"Error in validator for step '{step_id}': {e}")
                await update.message.reply_text("❌ Ошибка валидации. Попробуйте снова:")
                return step_id
        
        # Сохраняем в context.user_data
        if step.data_key:
            context.user_data['workflow_data'][step.data_key] = user_input
        
        # Переходим к следующему шагу
        return await self._goto_next_step(update, context, step)
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE, callback_data: str):
        """Обработать callback"""
        workflow_name = context.user_data.get('workflow_name')
        step_id = context.user_data.get('workflow_step')
        
        if not workflow_name or not step_id:
            return None
        
        workflow = self.workflows.get(workflow_name)
        if not workflow:
            return None
        
        step = workflow.steps.get(step_id)
        
        if not step or step.type != StepType.CALLBACK:
            return None
        
        # Сохраняем выбор
        if step.data_key:
            context.user_data['workflow_data'][step.data_key] = callback_data
        
        # Переходим к следующему шагу
        return await self._goto_next_step(update, context, step)
    
    async def _finish_workflow(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Завершить workflow"""
        workflow_name = context.user_data.get('workflow_name')
        workflow = self.workflows.get(workflow_name)
        
        if workflow and hasattr(workflow, 'on_complete'):
            try:
                import inspect
                if inspect.iscoroutinefunction(workflow.on_complete):
                    await workflow.on_complete(update, context, context.user_data.get('workflow_data', {}))
                else:
                    workflow.on_complete(update, context, context.user_data.get('workflow_data', {}))
            except Exception as e:
                logger.error(f"Error in on_complete for workflow '{workflow_name}': {e}")
        
        # Очищаем контекст
        user_id = update.effective_user.id
        self.current_workflows.pop(user_id, None)
        
        for key in workflow.context_keys if workflow else []:
            context.user_data.pop(key, None)
        
        context.user_data.pop('workflow_name', None)
        context.user_data.pop('workflow_step', None)
        context.user_data.pop('workflow_data', None)
        
        return None  # ConversationHandler.END


# Глобальный экземпляр менеджера
workflow_manager = WorkflowManager()

