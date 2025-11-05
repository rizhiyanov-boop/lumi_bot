"""
Модуль templates - шаблоны сообщений

Содержит все текстовые шаблоны для упрощения локализации
"""

from .messages import *

__all__ = [
    'RolePanels',
    'ClubManagement',
    # УДАЛЕНО: LocationManagement, FieldManagement, RefereeManagement - старый код для paintball проекта
    'Common',
    'Formatters',
]

