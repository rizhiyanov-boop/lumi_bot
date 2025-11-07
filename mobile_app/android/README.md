# Lumi Beauty Android App

Android приложение для клиентов Lumi Beauty.

## ⚠️ Для сборки APK нужен Android Studio

**Без Android Studio собрать APK невозможно**, так как нужен Android SDK.

## 🚀 Быстрый старт

### 1. Установите Android Studio
- https://developer.android.com/studio
- Установите с Android SDK

### 2. Откройте проект
```
File → Open → папка android/
```

### 3. Соберите APK
```
Build → Build Bundle(s) / APK(s) → Build APK(s)
```

### 4. Готово!
APK: `app/build/outputs/apk/debug/app-debug.apk`

## ⚙️ Настройка

Перед сборкой настройте API endpoint в:
`app/src/main/java/com/lumi/beauty/di/AppModule.kt`

И запустите REST API:
```bash
cd api
python run_api.py
```

## 📱 Установка

Скопируйте APK на телефон и установите!

---

**Подробные инструкции:** См. `HOW_TO_BUILD_APK.md` или `START_HERE.md`
