# Руководство по развертыванию ботов на сервере

Это руководство поможет вам развернуть Telegram-ботов Lumi на арендованном Linux-сервере.

> **💡 Для новичков**: Если вы никогда не работали с серверами, начните с файла **[DEPLOYMENT_FOR_BEGINNERS.md](DEPLOYMENT_FOR_BEGINNERS.md)** - там все расписано пошагово с подробными объяснениями.

## Содержание

1. [Требования к серверу](#требования-к-серверу)
2. [Подготовка сервера](#подготовка-сервера)
3. [Установка зависимостей](#установка-зависимостей)
4. [Настройка проекта](#настройка-проекта)
5. [Настройка окружения](#настройка-окружения)
6. [Запуск ботов через systemd](#запуск-ботов-через-systemd)
7. [Настройка Nginx (для API)](#настройка-nginx-для-api)
8. [Резервное копирование](#резервное-копирование)
9. [Мониторинг и логи](#мониторинг-и-логи)
10. [Обновление ботов](#обновление-ботов)

## Требования к серверу

### Минимальные требования (реальные):
- **ОС**: Ubuntu 22.04 LTS / Ubuntu 24.04 LTS / Debian 11+ (рекомендуется Ubuntu 24.04 LTS)
- **RAM**: 512 MB (рекомендуется 1 GB для комфортной работы)
- **CPU**: 1 ядро (рекомендуется 1 ядро, 2 для комфорта)
- **Диск**: 3 GB (рекомендуется 5 GB с запасом для логов и бэкапов)
- **Сеть**: Стабильное интернет-соединение
- **Виртуализация**: KVM (рекомендуется) или XEN HVM

### Реальное использование ресурсов:
- **RAM**: ~300-400 MB (оба бота + система)
- **Диск**: ~500 MB (код + зависимости + база данных)
- **CPU**: Минимальная нагрузка (боты простаивают большую часть времени)

### Рекомендуемая конфигурация для старта:
- **CPU**: 1 ядро × 3.6 GHz
- **RAM**: 1 GB
- **Диск**: 80 GB HDD (или 20 GB SSD, если доступно)
- **ОС**: Ubuntu 24.04 LTS
- **Виртуализация**: KVM
- **Предустановленное ПО**: Не установлено (чистый сервер)
- **Стоимость**: ~300-400 ₽/месяц

### Необходимые порты:
- `443` (HTTPS) - для API (опционально)
- `80` (HTTP) - для редиректа на HTTPS (опционально)

## Подготовка сервера

### 1. Подключение к серверу

```bash
ssh root@your-server-ip
# или
ssh your-username@your-server-ip
```

### 2. Обновление системы

```bash
# Ubuntu/Debian
sudo apt update && sudo apt upgrade -y

# CentOS/RHEL
sudo yum update -y
```

### 3. Установка базовых инструментов

```bash
# Ubuntu/Debian
sudo apt install -y git curl wget build-essential python3-pip python3-venv nginx supervisor

# CentOS/RHEL
sudo yum install -y git curl wget gcc python3 python3-pip nginx supervisor
```

### 4. Создание пользователя для ботов

```bash
# Создаем пользователя
sudo useradd -m -s /bin/bash lumi
sudo usermod -aG sudo lumi  # Даем права sudo (опционально)

# Переключаемся на пользователя
sudo su - lumi
```

## Установка зависимостей

### 1. Клонирование репозитория

```bash
cd /home/lumi
git clone https://github.com/your-username/lumi_bot.git
cd lumi_bot
```

### 2. Создание виртуального окружения

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Установка Python-зависимостей

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

## Настройка проекта

### 1. Создание структуры директорий

```bash
mkdir -p /home/lumi/lumi_bot/logs
mkdir -p /home/lumi/lumi_bot/backups
```

### 2. Настройка прав доступа

```bash
chmod +x run_master.py
chmod +x run_client.py
```

## Настройка окружения

### 1. Создание файла .env

```bash
cd /home/lumi/lumi_bot
nano .env
```

### 2. Содержимое файла .env

```env
# Telegram Bot Tokens
BOT_TOKEN=your_master_bot_token_here
CLIENT_BOT_TOKEN=your_client_bot_token_here
CLIENT_BOT_USERNAME=your_client_bot_username

# Database
DATABASE_URL=sqlite:///database.db

# Super Admins (через запятую)
SUPER_ADMINS=123456789,987654321

# YooKassa Payment Configuration
YOOKASSA_SHOP_ID=your_shop_id
YOOKASSA_SECRET_KEY=your_secret_key
YOOKASSA_TEST_MODE=false

# Premium subscription
PREMIUM_PRICE=299.00
PREMIUM_DURATION_DAYS=30

# OpenAI API (для генерации описаний)
OPENAI_API_KEY=your_openai_api_key
```

### 3. Защита файла .env

```bash
chmod 600 .env
```

## Запуск ботов через systemd

### 1. Создание service файла для Master Bot

```bash
sudo nano /etc/systemd/system/lumi-master.service
```

Содержимое:

```ini
[Unit]
Description=Lumi Master Bot
After=network.target

[Service]
Type=simple
User=lumi
Group=lumi
WorkingDirectory=/home/lumi/lumi_bot
Environment="PATH=/home/lumi/lumi_bot/venv/bin"
ExecStart=/home/lumi/lumi_bot/venv/bin/python /home/lumi/lumi_bot/run_master.py
Restart=always
RestartSec=10
StandardOutput=append:/home/lumi/lumi_bot/logs/master.log
StandardError=append:/home/lumi/lumi_bot/logs/master_error.log

[Install]
WantedBy=multi-user.target
```

### 2. Создание service файла для Client Bot

```bash
sudo nano /etc/systemd/system/lumi-client.service
```

Содержимое:

```ini
[Unit]
Description=Lumi Client Bot
After=network.target

[Service]
Type=simple
User=lumi
Group=lumi
WorkingDirectory=/home/lumi/lumi_bot
Environment="PATH=/home/lumi/lumi_bot/venv/bin"
ExecStart=/home/lumi/lumi_bot/venv/bin/python /home/lumi/lumi_bot/run_client.py
Restart=always
RestartSec=10
StandardOutput=append:/home/lumi/lumi_bot/logs/client.log
StandardError=append:/home/lumi/lumi_bot/logs/client_error.log

[Install]
WantedBy=multi-user.target
```

### 3. Запуск и автозапуск сервисов

```bash
# Перезагружаем systemd
sudo systemctl daemon-reload

# Включаем автозапуск
sudo systemctl enable lumi-master.service
sudo systemctl enable lumi-client.service

# Запускаем боты
sudo systemctl start lumi-master.service
sudo systemctl start lumi-client.service

# Проверяем статус
sudo systemctl status lumi-master.service
sudo systemctl status lumi-client.service
```

### 4. Управление сервисами

```bash
# Остановить бота
sudo systemctl stop lumi-master.service
sudo systemctl stop lumi-client.service

# Перезапустить бота
sudo systemctl restart lumi-master.service
sudo systemctl restart lumi-client.service

# Просмотр логов
sudo journalctl -u lumi-master.service -f
sudo journalctl -u lumi-client.service -f

# Просмотр последних логов
sudo journalctl -u lumi-master.service -n 100
sudo journalctl -u lumi-client.service -n 100
```

## Настройка Nginx (для API)

Если вам нужен API для мобильного приложения:

### 1. Создание service файла для API

```bash
sudo nano /etc/systemd/system/lumi-api.service
```

Содержимое:

```ini
[Unit]
Description=Lumi API Server
After=network.target

[Service]
Type=simple
User=lumi
Group=lumi
WorkingDirectory=/home/lumi/lumi_bot/mobile_app/api
Environment="PATH=/home/lumi/lumi_bot/venv/bin"
ExecStart=/home/lumi/lumi_bot/venv/bin/python /home/lumi/lumi_bot/mobile_app/api/run_api.py
Restart=always
RestartSec=10
StandardOutput=append:/home/lumi/lumi_bot/logs/api.log
StandardError=append:/home/lumi/lumi_bot/logs/api_error.log

[Install]
WantedBy=multi-user.target
```

### 2. Настройка Nginx

```bash
sudo nano /etc/nginx/sites-available/lumi-api
```

Содержимое:

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Активируем конфигурацию:

```bash
sudo ln -s /etc/nginx/sites-available/lumi-api /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 3. Настройка SSL (Let's Encrypt)

```bash
# Установка certbot
sudo apt install certbot python3-certbot-nginx

# Получение сертификата
sudo certbot --nginx -d your-domain.com

# Автоматическое обновление
sudo certbot renew --dry-run
```

## Резервное копирование

### 1. Создание скрипта резервного копирования

```bash
nano /home/lumi/lumi_bot/backup.sh
```

Содержимое:

```bash
#!/bin/bash

BACKUP_DIR="/home/lumi/lumi_bot/backups"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/lumi_backup_$DATE.tar.gz"

# Создаем резервную копию базы данных и логов
tar -czf "$BACKUP_FILE" \
    /home/lumi/lumi_bot/database.db \
    /home/lumi/lumi_bot/.env \
    /home/lumi/lumi_bot/logs

# Удаляем старые бэкапы (старше 30 дней)
find "$BACKUP_DIR" -name "lumi_backup_*.tar.gz" -mtime +30 -delete

echo "Backup created: $BACKUP_FILE"
```

Делаем скрипт исполняемым:

```bash
chmod +x /home/lumi/lumi_bot/backup.sh
```

### 2. Настройка автоматического резервного копирования (cron)

```bash
crontab -e
```

Добавляем строку для ежедневного бэкапа в 3:00 ночи:

```
0 3 * * * /home/lumi/lumi_bot/backup.sh >> /home/lumi/lumi_bot/logs/backup.log 2>&1
```

## Мониторинг и логи

### 1. Просмотр логов в реальном времени

```bash
# Логи Master Bot
tail -f /home/lumi/lumi_bot/logs/master.log

# Логи Client Bot
tail -f /home/lumi/lumi_bot/logs/client.log

# Логи через systemd
sudo journalctl -u lumi-master.service -f
sudo journalctl -u lumi-client.service -f
```

### 2. Мониторинг использования ресурсов

```bash
# Использование памяти и CPU
htop

# Использование диска
df -h

# Процессы ботов
ps aux | grep python
```

### 3. Настройка ротации логов

```bash
sudo nano /etc/logrotate.d/lumi-bots
```

Содержимое:

```
/home/lumi/lumi_bot/logs/*.log {
    daily
    rotate 7
    compress
    delaycompress
    notifempty
    missingok
    create 0640 lumi lumi
}
```

## Обновление ботов

### 1. Создание скрипта обновления

```bash
nano /home/lumi/lumi_bot/update.sh
```

Содержимое:

```bash
#!/bin/bash

cd /home/lumi/lumi_bot

# Создаем резервную копию перед обновлением
./backup.sh

# Останавливаем боты
sudo systemctl stop lumi-master.service
sudo systemctl stop lumi-client.service

# Обновляем код
git pull origin master

# Активируем виртуальное окружение
source venv/bin/activate

# Обновляем зависимости
pip install -r requirements.txt

# Запускаем боты
sudo systemctl start lumi-master.service
sudo systemctl start lumi-client.service

echo "Update completed!"
```

Делаем скрипт исполняемым:

```bash
chmod +x /home/lumi/lumi_bot/update.sh
```

### 2. Запуск обновления

```bash
./update.sh
```

## Полезные команды

### Проверка статуса всех сервисов

```bash
sudo systemctl status lumi-master.service lumi-client.service lumi-api.service
```

### Просмотр использования ресурсов

```bash
# Память
free -h

# Диск
df -h

# CPU и процессы
top
```

### Перезапуск всех ботов

```bash
sudo systemctl restart lumi-master.service lumi-client.service
```

### Просмотр последних ошибок

```bash
sudo journalctl -u lumi-master.service -p err -n 50
sudo journalctl -u lumi-client.service -p err -n 50
```

## Решение проблем

### Бот не запускается

1. Проверьте логи:
   ```bash
   sudo journalctl -u lumi-master.service -n 100
   ```

2. Проверьте файл .env:
   ```bash
   cat /home/lumi/lumi_bot/.env
   ```

3. Проверьте права доступа:
   ```bash
   ls -la /home/lumi/lumi_bot/
   ```

### Бот падает

1. Проверьте использование памяти:
   ```bash
   free -h
   ```

2. Проверьте логи ошибок:
   ```bash
   tail -f /home/lumi/lumi_bot/logs/master_error.log
   ```

3. Проверьте статус сервиса:
   ```bash
   sudo systemctl status lumi-master.service
   ```

### Проблемы с базой данных

1. Проверьте права доступа к файлу базы данных:
   ```bash
   ls -la /home/lumi/lumi_bot/database.db
   ```

2. Создайте резервную копию:
   ```bash
   cp /home/lumi/lumi_bot/database.db /home/lumi/lumi_bot/database.db.backup
   ```

## Безопасность

### 1. Настройка файрвола

```bash
# Ubuntu/Debian
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable

# CentOS/RHEL
sudo firewall-cmd --permanent --add-service=ssh
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --reload
```

### 2. Отключение root-доступа по SSH

```bash
sudo nano /etc/ssh/sshd_config
```

Измените:
```
PermitRootLogin no
```

Перезапустите SSH:
```bash
sudo systemctl restart sshd
```

### 3. Регулярное обновление системы

```bash
# Добавьте в crontab
0 2 * * 0 apt update && apt upgrade -y
```

## Поддержка

При возникновении проблем:

1. Проверьте логи ботов
2. Проверьте статус сервисов
3. Проверьте использование ресурсов сервера
4. Создайте issue в репозитории GitHub

---

**Удачи с развертыванием! 🚀**

