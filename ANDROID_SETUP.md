# Настройка Android приложения Lumi Beauty

## Предварительные требования

1. **Android Studio** (последняя версия)
2. **JDK 17** или выше
3. **Python 3.10+** для REST API
4. **Android SDK** (API 24+)

## Установка

### 1. REST API

```bash
# Установите зависимости
cd mobile_app/api
pip install -r requirements.txt

# Запустите API сервер
python run_api.py
```

API будет доступен по адресу: `http://localhost:8000`

### 2. Android приложение

1. Откройте Android Studio
2. Выберите "Open an Existing Project"
3. Укажите папку `mobile_app/android/`
4. Дождитесь синхронизации Gradle
5. Настройте API endpoint в `app/src/main/java/com/lumi/beauty/di/AppModule.kt`:
   ```kotlin
   val baseUrl = "http://YOUR_IP:8000/" // Замените на ваш IP адрес
   ```
   Для эмулятора используйте: `http://10.0.2.2:8000/`
   Для реального устройства используйте IP вашего компьютера в локальной сети

6. Запустите приложение на эмуляторе или реальном устройстве

## Сборка APK

```bash
cd android
./gradlew assembleRelease
```

APK будет в: `app/build/outputs/apk/release/app-release.apk`

## Аутентификация

В текущей версии используется упрощенная аутентификация через `user_id` в заголовке `Authorization: Bearer {user_id}`.

Для продакшена рекомендуется:
- Использовать JWT токены
- Реализовать OAuth 2.0
- Добавить безопасное хранение токенов

## Структура проекта

```
android/
├── app/
│   ├── src/main/
│   │   ├── java/com/lumi/beauty/
│   │   │   ├── data/          # API клиенты, репозитории
│   │   │   ├── domain/        # Модели, use cases
│   │   │   ├── ui/            # Compose UI
│   │   │   └── di/            # Dependency Injection
│   │   └── res/               # Ресурсы
│   └── build.gradle.kts
└── build.gradle.kts
```

## Основные функции

- ✅ Просмотр списка мастеров
- ✅ Детальная информация о мастере
- ✅ Просмотр услуг
- ✅ Бронирование
- ✅ Поиск мастеров по городам
- ✅ Просмотр записей

## Дальнейшая разработка

1. Добавить экраны бронирования
2. Реализовать поиск мастеров
3. Добавить уведомления
4. Реализовать офлайн режим (Room)
5. Добавить аутентификацию через Telegram

