#!/bin/bash
# Скрипт автоматического развертывания ботов на сервере
# ВЕРСИЯ ДЛЯ НОВИЧКОВ - с подробными объяснениями

set -e  # Остановка при ошибке

echo "🚀 Начало развертывания Lumi Bots..."
echo "📖 Этот скрипт автоматически настроит ваших ботов на сервере"
echo ""

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Проверка прав root
if [ "$EUID" -eq 0 ]; then 
    echo -e "${RED}⚠️  ВНИМАНИЕ: Не запускайте скрипт от root!${NC}"
    echo -e "${YELLOW}Создайте пользователя командой: adduser lumi${NC}"
    echo -e "${YELLOW}Затем переключитесь: su - lumi${NC}"
    echo -e "${YELLOW}И запустите скрипт снова${NC}"
    exit 1
fi

# Переменные
PROJECT_DIR="$HOME/lumi_bot"
VENV_DIR="$PROJECT_DIR/venv"
SERVICE_USER=$(whoami)

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}✓ Пользователь: $SERVICE_USER${NC}"
echo -e "${GREEN}✓ Директория проекта: $PROJECT_DIR${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# 1. Обновление системы
echo -e "${YELLOW}📦 Шаг 1/15: Обновление системы...${NC}"
echo -e "${BLUE}   Это может занять 2-5 минут, подождите...${NC}"
sudo apt update && sudo apt upgrade -y
echo -e "${GREEN}✓ Система обновлена${NC}"
echo ""

# 2. Установка базовых пакетов
echo -e "${YELLOW}📦 Шаг 2/15: Установка необходимых программ...${NC}"
echo -e "${BLUE}   Устанавливаем: git, Python, nginx и другие утилиты...${NC}"
sudo apt install -y git curl wget build-essential python3-pip python3-venv nginx supervisor
echo -e "${GREEN}✓ Все программы установлены${NC}"
echo ""

# 3. Клонирование репозитория
echo -e "${YELLOW}📥 Шаг 3/15: Скачивание кода ботов...${NC}"
if [ ! -d "$PROJECT_DIR" ]; then
    echo -e "${BLUE}   Скачиваем код с GitHub...${NC}"
    cd $HOME
    echo -e "${RED}⚠️  ВАЖНО: Нужно указать ссылку на ваш репозиторий!${NC}"
    echo -e "${YELLOW}   Введите ссылку на ваш GitHub репозиторий:${NC}"
    read -r GIT_REPO
    if [ -z "$GIT_REPO" ]; then
        echo -e "${RED}❌ Ссылка не указана! Используем примерную...${NC}"
        echo -e "${YELLOW}   Вы можете изменить это позже, отредактировав файл${NC}"
        GIT_REPO="https://github.com/your-username/lumi_bot.git"
    fi
    git clone "$GIT_REPO" lumi_bot || {
        echo -e "${RED}❌ Ошибка при клонировании репозитория!${NC}"
        echo -e "${YELLOW}   Проверьте ссылку и попробуйте снова${NC}"
        exit 1
    }
else
    echo -e "${BLUE}   Обновляем существующий код...${NC}"
    cd $PROJECT_DIR
    git pull
fi
echo -e "${GREEN}✓ Код скачан${NC}"
echo ""

# 4. Создание виртуального окружения
echo -e "${YELLOW}Создание виртуального окружения...${NC}"
cd $PROJECT_DIR
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv venv
fi
source venv/bin/activate

# 5. Установка зависимостей
echo -e "${YELLOW}Установка зависимостей...${NC}"
pip install --upgrade pip
pip install -r requirements.txt

# 6. Создание директорий
echo -e "${YELLOW}Создание директорий...${NC}"
mkdir -p $PROJECT_DIR/logs
mkdir -p $PROJECT_DIR/backups

# 7. Настройка прав доступа
echo -e "${YELLOW}Настройка прав доступа...${NC}"
chmod +x $PROJECT_DIR/run_master.py
chmod +x $PROJECT_DIR/run_client.py
chmod +x $PROJECT_DIR/deploy.sh

# 8. Проверка файла .env
echo -e "${YELLOW}⚙️  Шаг 8/15: Настройка конфигурации...${NC}"
if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo -e "${BLUE}   Создаем файл .env с настройками...${NC}"
    cat > $PROJECT_DIR/.env << EOF
# Telegram Bot Tokens
BOT_TOKEN=your_master_bot_token_here
CLIENT_BOT_TOKEN=your_client_bot_token_here
CLIENT_BOT_USERNAME=your_client_bot_username

# Database
DATABASE_URL=sqlite:///database.db

# Super Admins (через запятую, без пробелов)
SUPER_ADMINS=

# YooKassa Payment Configuration
YOOKASSA_SHOP_ID=
YOOKASSA_SECRET_KEY=
YOOKASSA_TEST_MODE=true

# Premium subscription
PREMIUM_PRICE=299.00
PREMIUM_DURATION_DAYS=30

# OpenAI API
OPENAI_API_KEY=
EOF
    chmod 600 $PROJECT_DIR/.env
    echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${RED}⚠️  ВАЖНО: Нужно заполнить файл .env!${NC}"
    echo -e "${YELLOW}1. Откройте файл: nano $PROJECT_DIR/.env${NC}"
    echo -e "${YELLOW}2. Заполните токены ботов и другие настройки${NC}"
    echo -e "${YELLOW}3. Сохраните: Ctrl+O, Enter, Ctrl+X${NC}"
    echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo -e "${BLUE}Нажмите Enter после того, как заполните .env файл...${NC}"
    read -r
else
    echo -e "${GREEN}✓ Файл .env уже существует${NC}"
fi
echo ""

# 9. Создание systemd service файлов
echo -e "${YELLOW}Создание systemd service файлов...${NC}"

# Master Bot Service
sudo tee /etc/systemd/system/lumi-master.service > /dev/null << EOF
[Unit]
Description=Lumi Master Bot
After=network.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$VENV_DIR/bin"
ExecStart=$VENV_DIR/bin/python $PROJECT_DIR/run_master.py
Restart=always
RestartSec=10
StandardOutput=append:$PROJECT_DIR/logs/master.log
StandardError=append:$PROJECT_DIR/logs/master_error.log

[Install]
WantedBy=multi-user.target
EOF

# Client Bot Service
sudo tee /etc/systemd/system/lumi-client.service > /dev/null << EOF
[Unit]
Description=Lumi Client Bot
After=network.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$VENV_DIR/bin"
ExecStart=$VENV_DIR/bin/python $PROJECT_DIR/run_client.py
Restart=always
RestartSec=10
StandardOutput=append:$PROJECT_DIR/logs/client.log
StandardError=append:$PROJECT_DIR/logs/client_error.log

[Install]
WantedBy=multi-user.target
EOF

# 10. Создание скрипта резервного копирования
echo -e "${YELLOW}Создание скрипта резервного копирования...${NC}"
cat > $PROJECT_DIR/backup.sh << 'BACKUP_EOF'
#!/bin/bash

BACKUP_DIR="$HOME/lumi_bot/backups"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/lumi_backup_$DATE.tar.gz"

# Создаем резервную копию базы данных и логов
tar -czf "$BACKUP_FILE" \
    "$HOME/lumi_bot/database.db" \
    "$HOME/lumi_bot/.env" \
    "$HOME/lumi_bot/logs" 2>/dev/null

# Удаляем старые бэкапы (старше 30 дней)
find "$BACKUP_DIR" -name "lumi_backup_*.tar.gz" -mtime +30 -delete

echo "Backup created: $BACKUP_FILE"
BACKUP_EOF

chmod +x $PROJECT_DIR/backup.sh

# 11. Создание скрипта обновления
echo -e "${YELLOW}Создание скрипта обновления...${NC}"
cat > $PROJECT_DIR/update.sh << 'UPDATE_EOF'
#!/bin/bash

cd $HOME/lumi_bot

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
UPDATE_EOF

chmod +x $PROJECT_DIR/update.sh

# 12. Перезагрузка systemd
echo -e "${YELLOW}Перезагрузка systemd...${NC}"
sudo systemctl daemon-reload

# 13. Включение автозапуска
echo -e "${YELLOW}Включение автозапуска...${NC}"
sudo systemctl enable lumi-master.service
sudo systemctl enable lumi-client.service

# 14. Запуск ботов
echo -e "${YELLOW}Запуск ботов...${NC}"
sudo systemctl start lumi-master.service
sudo systemctl start lumi-client.service

# 15. Проверка статуса
echo -e "${YELLOW}Проверка статуса...${NC}"
sleep 3
sudo systemctl status lumi-master.service --no-pager
sudo systemctl status lumi-client.service --no-pager

# 16. Настройка cron для резервного копирования
echo -e "${YELLOW}Настройка автоматического резервного копирования...${NC}"
(crontab -l 2>/dev/null; echo "0 3 * * * $PROJECT_DIR/backup.sh >> $PROJECT_DIR/logs/backup.log 2>&1") | crontab -

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}✅ Развертывание завершено!${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${YELLOW}📋 Полезные команды:${NC}"
echo -e "  ${GREEN}Статус ботов:${NC} sudo systemctl status lumi-master.service lumi-client.service"
echo -e "  ${GREEN}Логи в реальном времени:${NC} sudo journalctl -u lumi-master.service -f"
echo -e "  ${GREEN}Перезапуск:${NC} sudo systemctl restart lumi-master.service"
echo -e "  ${GREEN}Остановка:${NC} sudo systemctl stop lumi-master.service"
echo -e "  ${GREEN}Запуск:${NC} sudo systemctl start lumi-master.service"
echo ""
echo -e "${YELLOW}📖 Подробная инструкция:${NC} См. файл DEPLOYMENT_FOR_BEGINNERS.md"
echo ""
echo -e "${GREEN}🎉 Боты должны быть запущены! Проверьте их в Telegram.${NC}"
echo ""

