# 📱 Mobile App - Android приложение Lumi Beauty

Эта папка содержит весь код для мобильного Android приложения и REST API.

## 📂 Структура

```
mobile_app/
├── api/              # REST API (FastAPI)
│   ├── main.py      # Основной файл API
│   └── requirements.txt
├── android/         # Android приложение (Kotlin + Jetpack Compose)
│   ├── app/         # Исходный код приложения
│   └── build.gradle.kts
└── README.md        # Этот файл
```

## 🚀 Быстрый старт

### 1. Запуск REST API

```bash
cd mobile_app/api
pip install -r requirements.txt
python run_api.py
```

API будет доступен на `http://localhost:8000`

### 2. Сборка Android APK

1. Установите Android Studio: https://developer.android.com/studio
2. Откройте проект: `File → Open → папка mobile_app/android/`
3. Соберите APK: `Build → Build Bundle(s) / APK(s) → Build APK(s)`

Подробные инструкции: `android/HOW_TO_BUILD_APK.md`

## 📝 Документация

- **API**: См. `api/main.py` - все эндпоинты документированы
- **Android**: См. `android/README.md` и `android/HOW_TO_BUILD_APK.md`

## ⚙️ Настройка

### API Endpoint

Перед сборкой APK настройте endpoint в:
`android/app/src/main/java/com/lumi/beauty/di/AppModule.kt`

- Для эмулятора: `http://10.0.2.2:8000/`
- Для устройства: `http://ВАШ_IP:8000/`

## ✅ Готово к использованию!

Все файлы на месте, можно собирать APK и тестировать приложение.

