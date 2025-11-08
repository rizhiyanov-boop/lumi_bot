# Быстрое развертывание ботов Lumi

## Быстрый старт (5 минут)

### 1. Подключение к серверу

```bash
ssh root@your-server-ip
# или
ssh your-username@your-server-ip
```

### 2. Создание пользователя

```bash
sudo useradd -m -s /bin/bash lumi
sudo usermod -aG sudo lumi
sudo su - lumi
```

### 3. Автоматическое развертывание

```bash
cd ~
git clone https://github.com/your-username/lumi_bot.git
cd lumi_bot
chmod +x deploy.sh
./deploy.sh
```

### 4. Настройка .env

```bash
nano ~/lumi_bot/.env
```

Заполните все необходимые значения:
- `BOT_TOKEN` - токен Master бота
- `CLIENT_BOT_TOKEN` - токен Client бота
- `CLIENT_BOT_USERNAME` - username Client бота
- `SUPER_ADMINS` - ID администраторов (через запятую)
- Остальные настройки по необходимости

### 5. Перезапуск ботов

```bash
sudo systemctl restart lumi-master.service
sudo systemctl restart lumi-client.service
```

### 6. Проверка статуса

```bash
sudo systemctl status lumi-master.service
sudo systemctl status lumi-client.service
```

## Основные команды

### Управление ботами

```bash
# Запуск
sudo systemctl start lumi-master.service
sudo systemctl start lumi-client.service

# Остановка
sudo systemctl stop lumi-master.service
sudo systemctl stop lumi-client.service

# Перезапуск
sudo systemctl restart lumi-master.service
sudo systemctl restart lumi-client.service

# Статус
sudo systemctl status lumi-master.service
sudo systemctl status lumi-client.service
```

### Просмотр логов

```bash
# В реальном времени
sudo journalctl -u lumi-master.service -f
sudo journalctl -u lumi-client.service -f

# Последние 100 строк
sudo journalctl -u lumi-master.service -n 100

# Только ошибки
sudo journalctl -u lumi-master.service -p err -n 50
```

### Обновление

```bash
cd ~/lumi_bot
./update.sh
```

### Резервное копирование

```bash
cd ~/lumi_bot
./backup.sh
```

Автоматическое резервное копирование настраивается автоматически на 3:00 каждый день.

## Настройка API (опционально)

Если нужен API для мобильного приложения:

### 1. Создание service файла

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

```bash
sudo ln -s /etc/nginx/sites-available/lumi-api /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 3. SSL сертификат

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

## Решение проблем

### Бот не запускается

```bash
# Проверьте логи
sudo journalctl -u lumi-master.service -n 100

# Проверьте .env
cat ~/lumi_bot/.env

# Проверьте права
ls -la ~/lumi_bot/
```

### Бот падает

```bash
# Проверьте использование памяти
free -h

# Проверьте логи ошибок
tail -f ~/lumi_bot/logs/master_error.log

# Проверьте статус
sudo systemctl status lumi-master.service
```

### Проблемы с базой данных

```bash
# Проверьте права
ls -la ~/lumi_bot/database.db

# Создайте бэкап
cp ~/lumi_bot/database.db ~/lumi_bot/database.db.backup
```

## Безопасность

### Файрвол

```bash
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

### Отключение root SSH

```bash
sudo nano /etc/ssh/sshd_config
# Измените: PermitRootLogin no
sudo systemctl restart sshd
```

## Поддержка

При возникновении проблем проверьте:
1. Логи ботов
2. Статус сервисов
3. Использование ресурсов
4. Файл .env

---

**Подробное руководство**: см. `DEPLOYMENT.md`

