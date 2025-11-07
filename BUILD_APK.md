# Инструкция по сборке APK

## Быстрая сборка через Android Studio

1. **Откройте проект в Android Studio**
   - File → Open → выберите папку `mobile_app/android/`
   - Дождитесь синхронизации Gradle

2. **Настройте API endpoint**
   - Откройте `mobile_app/android/app/src/main/java/com/lumi/beauty/di/AppModule.kt`
   - Измените `baseUrl` на ваш IP адрес:
     ```kotlin
     val baseUrl = "http://YOUR_IP:8000/" // Для реального устройства
     // или
     val baseUrl = "http://10.0.2.2:8000/" // Для эмулятора
     ```

3. **Соберите APK**
   - Build → Build Bundle(s) / APK(s) → Build APK(s)
   - Или через терминал: `./gradlew assembleDebug`

4. **APK будет в:**
   - `app/build/outputs/apk/debug/app-debug.apk`

## Сборка через командную строку (Windows)

```powershell
cd mobile_app\android
.\gradlew.bat assembleDebug
```

APK: `app\build\outputs\apk\debug\app-debug.apk`

## Сборка Release APK (для тестирования)

```powershell
cd android
.\gradlew.bat assembleRelease
```

APK: `app\build\outputs\apk\release\app-release.apk`

**Важно:** Для release нужен keystore. Для тестирования используйте debug версию.

## Требования

- Android Studio или Android SDK
- JDK 17+
- Интернет для загрузки зависимостей Gradle

## Альтернатива: Использовать готовый скрипт

Создайте файл `build_apk.bat` в корне проекта:

```batch
@echo off
echo Building Lumi Beauty APK...
cd android
call gradlew.bat assembleDebug
if %ERRORLEVEL% equ 0 (
    echo.
    echo APK успешно собран!
    echo Файл: android\app\build\outputs\apk\debug\app-debug.apk
) else (
    echo.
    echo Ошибка при сборке APK
)
pause
```

Запустите `build_apk.bat`

