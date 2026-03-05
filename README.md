<div align="center">
  <img src="https://via.placeholder.com/1500x500/151B23/FFFFFF?text=Telegram+Clinic+Bot+Banner" alt="Project Banner" width="100%">

  <h1>🏥 Telegram-Бот: Онлайн-запись к врачу</h1>
  <p><b>Профессиональное решение для автоматизации записи пациентов, умные напоминания и панель администратора.</b></p>

  <div>
    <img src="https://img.shields.io/badge/Python_3.12-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python" />
    <img src="https://img.shields.io/badge/Aiogram_3.x-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white" alt="Aiogram" />
    <img src="https://img.shields.io/badge/SQLAlchemy_2.0-CC2927?style=for-the-badge&logo=sqalchemy&logoColor=white" alt="SQLAlchemy" />
    <img src="https://img.shields.io/badge/SQLite-003B57?style=for-the-badge&logo=sqlite&logoColor=white" alt="SQLite" />
    <img src="https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Docker" />
  </div>
</div>

---

## 📱 Демонстрация интерфейса
> **Заметка для тебя:** Запиши короткую GIF (до 5 МБ) с процессом записи к врачу и сделай скриншот панели администратора. Раскомментируй код ниже и вставь свои ссылки. Это критически важно для продажи проекта!

---

## ✨ Основной функционал

### 👤 Для клиентов
* **Бесшовная запись (FSM):** Пошаговый выбор услуги → специалиста → даты (удобный Inline-календарь) → времени.
* **Личный кабинет (`/my_appointments`):** Просмотр предстоящих записей с возможностью отмены (настраиваемый лимит времени).
* **Умные уведомления:** Автоматические напоминания о визите за 24 часа.
* **Конфиденциальность:** Безопасная регистрация через нативный Telegram Contact Sharing.

### 🛡 Для администраторов (`/admin`)
* **Управление записями:** Просмотр списка (с фильтрацией), перенос слотов (с авто-уведомлением клиента), отмена с указанием причины.
* **Каталог услуг (CRUD):** Создание, редактирование и гибкая деактивация услуг.
* **Сотрудники и графики:** Добавление врачей, тонкая настройка расписания с учетом выходных и перерывов.

---

## 🏗 Архитектура и под капотом

Проект спроектирован с упором на **чистую архитектуру** и готов к масштабированию (SOLID, Dependency Injection):

* **Стек:** `aiogram 3.x`, `SQLAlchemy 2.0 (Async)`, `aiosqlite`.
* **База данных:** SQLite (для быстрого старта) + `Alembic` для надежного управления миграциями.
* **Бизнес-логика:** Полностью изолирована в слое `services/` (генерация слотов, управление бронированием) — идеальная база для покрытия Unit-тестами.
* **Транзакционность:** Внедрен строгий контроль состояния гонки (Race Conditions) — абсолютная защита от двойной записи пациентов на одно время.
* **Фоновые задачи:** `APScheduler` с сохранением Job'ов в БД (SQLAlchemyJobStore) гарантирует, что ни одно напоминание не потеряется при перезапуске сервера.
* **Качество кода:** Строгий линтинг и форматирование через `Ruff`.

---

## 🚀 Быстрый старт

Проект полностью готов к Production-развертыванию.

### 1. Подготовка окружения
Склонируйте репозиторий и создайте файл переменных окружения:
```bash
git clone [https://github.com/m1sstak3/tg-appointment-bot.git](https://github.com/m1sstak3/tg-appointment-bot.git)
cd tg-appointment-bot
cp bot/.env.example bot/.env