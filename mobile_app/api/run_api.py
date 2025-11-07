#!/usr/bin/env python3
"""
Запуск REST API для Android приложения
"""
import uvicorn
from api.main import app

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )

