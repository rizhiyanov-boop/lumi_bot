# Установка Android Studio для сборки APK

## Шаг 1: Скачайте Android Studio

1. Перейдите на https://developer.android.com/studio
2. Скачайте Android Studio для Windows
3. Установите (включите опцию "Android SDK" и "Android SDK Platform")

## Шаг 2: Откройте проект

1. Запустите Android Studio
2. **File → Open** → выберите папку `android/`
3. Дождитесь синхронизации Gradle (может занять 5-10 минут при первом запуске)

## Шаг 3: Настройте SDK

1. **File → Settings** (или **File → Project Structure**)
2. Убедитесь, что установлены:
   - Android SDK Platform 34
   - Android SDK Build-Tools
   - Android Emulator (опционально)

## Шаг 4: Соберите APK

1. **Build → Build Bundle(s) / APK(s) → Build APK(s)**
2. Дождитесь завершения сборки
3. Нажмите **locate** в уведомлении или найдите файл:
   ```
   android/app/build/outputs/apk/debug/app-debug.apk
   ```

## Альтернатива: Используйте готовый скрипт

После открытия проекта в Android Studio хотя бы раз, можно использовать:

```powershell
cd android
.\gradlew.bat assembleDebug
```

## Быстрая проверка

После установки Android Studio и открытия проекта, проверьте:

```powershell
cd android
.\gradlew.bat --version
```

Если команда работает - можно собирать APK!

