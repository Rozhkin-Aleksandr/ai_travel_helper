# AI Travel Agent 🌍✈️
ССЫЛКА НА ДЕМОНСТРАЦИЮ: https://disk.yandex.ru/i/Fct8l6pVdQ8X1w
AI Travel Agent — это умный помощник для планирования путешествий, созданный на базе нейросетей (OpenRouter / Gemini) и FastAPI. Сервис позволяет в пару кликов сгенерировать маршрут, подобрать туры, а также найти билеты на самолет/поезд и отели.

## Возможности
- 🤖 **Интеллектуальный подбор туров**: генерация уникальных маршрутов по вашим пожеланиям и бюджету.
- ✈️ **Поиск авиабилетов**: интеграция с API Travelpayouts (Aviasales) для актуальных цен и маршрутов по всему миру.
- 🚆 **Поиск билетов на поезда (по РФ)**: интеграция с API Яндекс Расписаний и Tutu.ru.
- 🏨 **Поиск отелей**:
  - **По России**: автоматическая генерация смарт-ссылок с предзаполненными параметрами на Суточно.ру, Авито и Яндекс.Путешествия.
  - **За границей**: поиск отелей через Booking.com API (RapidAPI).
- 💬 **Контекстный диалог**: возможность общаться с ИИ для уточнения деталей по конкретному туру.

## Технологический стек
- **Backend**: Python 3, FastAPI, Uvicorn, Requests
- **Frontend**: HTML5, Vue.js 3, Tailwind CSS
- **AI**: OpenAI SDK (подключение к моделям через OpenRouter)
- **API Интеграции**: Travelpayouts, Yandex Rasp API, Booking API

## Структура проекта
```text
repo/
├── main.py               # Главный файл FastAPI приложения и логика работы с ИИ
├── tools.py              # Функции-инструменты (tools) для вызова внешних API билетов и отелей
├── static/
│   ├── index.html        # Фронтенд: Vue.js + Tailwind
│   └── travel_hack.png   # Логотип сайта
├── tutu_cities.json      # Справочник городов для API Tutu
├── yandex_cities.json    # Справочник городов для API Yandex
├── requirements.txt      # Зависимости Python
└── .env                  # (Не включен в git) Файл с API-ключами
```

## Установка и запуск локально

1. **Склонируйте репозиторий** и перейдите в папку проекта:
   ```bash
   cd repo
   ```

2. **Создайте виртуальное окружение** и активируйте его:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Для macOS/Linux
   # или venv\Scripts\activate для Windows
   ```

3. **Установите зависимости**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Настройте переменные окружения**:
   Создайте файл `.env` в корневой папке `repo` и добавьте ваши API ключи:
   ```env
   AVIASALES_API_KEY=ваш_ключ_от_travelpayouts
   YANDEX_API_KEY=ваш_ключ_от_яндекс_расписаний
   OPENROUTER_API_KEY=ваш_ключ_от_openrouter
   RAPIDAPI_KEY=ваш_ключ_от_rapidapi_booking_com
   ```

5. **Запустите сервер**:
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000
   ```

6. **Откройте приложение**:
   Перейдите в браузере по адресу [http://localhost:8000](http://localhost:8000)

## Лицензия
MIT
