from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import os
import json
import uuid
from datetime import datetime
import openai
from dotenv import load_dotenv

from tools import search_train_tickets_ru, search_flight_tickets, search_hotels_abroad, get_ru_hotel_links

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(dotenv_path=os.path.join(BASE_DIR, ".env"))

CHATS_DIR = os.path.join(os.path.dirname(__file__), "chats")
os.makedirs(CHATS_DIR, exist_ok=True)

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def root():
    return FileResponse("static/index.html")

client = openai.OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY", "")
)

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    query: str
    budget: int
    city_from: str = ""
    city: str
    dates: str
    search_tickets: bool
    search_hotels: bool
    history: list[ChatMessage]

class SaveChatRequest(BaseModel):
    id: str | None = None
    title: str
    city: str
    dates: str
    messages: list[dict]


@app.get("/api/chats")
async def list_chats():
    chats = []
    for filename in os.listdir(CHATS_DIR):
        if not filename.endswith(".json"):
            continue
        filepath = os.path.join(CHATS_DIR, filename)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            chats.append({
                "id": data.get("id"),
                "title": data.get("title", "Без названия"),
                "city": data.get("city", ""),
                "dates": data.get("dates", ""),
                "created_at": data.get("created_at", ""),
            })
        except Exception:
            continue
    chats.sort(key=lambda c: c.get("created_at", ""), reverse=True)
    return chats


@app.post("/api/chats")
async def save_chat(req: SaveChatRequest):
    chat_id = req.id or str(uuid.uuid4())
    filepath = os.path.join(CHATS_DIR, f"{chat_id}.json")

    created_at = datetime.now().isoformat()
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                old = json.load(f)
            created_at = old.get("created_at", created_at)
        except Exception:
            pass

    chat_data = {
        "id": chat_id,
        "title": req.title,
        "city": req.city,
        "dates": req.dates,
        "messages": req.messages,
        "created_at": created_at,
        "updated_at": datetime.now().isoformat(),
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(chat_data, f, ensure_ascii=False, indent=2)
    return {"id": chat_id}


@app.get("/api/chats/{chat_id}")
async def get_chat(chat_id: str):
    filepath = os.path.join(CHATS_DIR, f"{chat_id}.json")
    if not os.path.exists(filepath):
        return {"error": "Chat not found"}
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


@app.delete("/api/chats/{chat_id}")
async def delete_chat(chat_id: str):
    filepath = os.path.join(CHATS_DIR, f"{chat_id}.json")
    if os.path.exists(filepath):
        os.remove(filepath)
    return {"ok": True}


# Define tools
tools_schema = [
    {
        "type": "function",
        "function": {
            "name": "search_train_tickets_ru",
            "description": "Поиск билетов на поезд по России (РЖД). Возвращает расписание и цены.",
            "parameters": {
                "type": "object",
                "properties": {
                    "city_from": {"type": "string"},
                    "city_to": {"type": "string"},
                    "date": {"type": "string", "description": "Дата в формате YYYY-MM-DD"}
                },
                "required": ["city_from", "city_to", "date"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_flight_tickets",
            "description": "Поиск авиабилетов. Используется для поездок за границу или по России, когда на поезде долго. ВНИМАНИЕ: Возвращаемая цена — это цена за билеты ТУДА И ОБРАТНО.",
            "parameters": {
                "type": "object",
                "properties": {
                    "origin_iata": {"type": "string", "description": "IATA код города/аэропорта отправления (обязательно 3 латинские буквы, например MOW для Москвы)"},
                    "destination_iata": {"type": "string", "description": "IATA код города/аэропорта назначения (обязательно 3 латинские буквы, например HKT для Пхукета, IST для Стамбула)"},
                    "depart_date": {"type": "string", "description": "Дата отправления в формате YYYY-MM-DD"},
                    "return_date": {"type": "string", "description": "Опционально. Дата обратного вылета в формате YYYY-MM-DD. Если не указано, ищет билет в одну сторону."}
                },
                "required": ["origin_iata", "destination_iata", "depart_date"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_hotels_abroad",
            "description": "Поиск отелей за границей (вне РФ). В РФ эту функцию НЕ использовать.",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string"},
                    "date_in": {"type": "string", "description": "Дата заезда YYYY-MM-DD"},
                    "date_out": {"type": "string", "description": "Дата выезда YYYY-MM-DD"}
                },
                "required": ["city", "date_in", "date_out"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_ru_hotel_links",
            "description": "Генерация прямых ссылок на поиск отелей по России (Суточно.ру, Авито, Яндекс Путешествия). Использовать ТОЛЬКО для городов РФ.",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "Название города на русском языке, например Выборг или Санкт-Петербург"},
                    "date_in": {"type": "string", "description": "Дата заезда в формате YYYY-MM-DD"},
                    "date_out": {"type": "string", "description": "Дата выезда в формате YYYY-MM-DD"}
                },
                "required": ["city", "date_in", "date_out"]
            }
        }
    }
]

SYSTEM_PROMPT = """
Ты - ИИ-агент по подбору авиа и жд билетов и составлению персональных туров.
Бюджет пользователя задаётся по шкале от 1 до 10:
- 1-2: минимальный (хостелы, плацкарт, самый дешёвый транспорт, бюджетная еда)
- 3-4: экономный (недорогие гостиницы, купе, лоукостеры)
- 5-6: средний (хорошие 3-4* отели, комфортный транспорт, рестораны среднего уровня)
- 7-8: комфортный/высокий (4-5* отели, бизнес-класс поезда, хорошие рестораны)
- 9-10: премиум/люкс (5* отели, бизнес-класс авиа, лучшие рестораны, VIP-услуги)
Подбирай варианты, соответствующие указанному уровню бюджета.
Отвечай структурировано в формате JSON.
Твой ответ должен строго соответствовать следующей структуре JSON:
{
  "route_and_hotels": "Строка в формате Markdown. Здесь опиши маршрут. Если были найдены авиабилеты - выведи ВСЕ найденные варианты (до 5 штук) списком. ВАЖНО ПРО ОТЕЛИ: Если ищешь отели через функцию search_hotels_abroad, она вернет поле 'photo' со ссылкой на картинку отеля. ОБЯЗАТЕЛЬНО вставляй эти фотографии в свой Markdown-ответ используя синтаксис: `![Название отеля](ссылка_на_картинку)`. Картинка должна идти сразу после названия отеля, чтобы ответ выглядел как красивый каталог. Если город в РФ - вызови get_ru_hotel_links и просто дай ссылки. Общайся максимально естественно, как живой турагент.",
  "tours": [
    {
      "title": "Название тура",
      "description": "Описание тура, примерная разметка по дням, достопримечательности."
    }
  ],
  "total_price": "Примерная цена за всю поездку текстом"
}
"""

@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    # Add history
    for h in req.history:
        messages.append({"role": h.role, "content": h.content})
        
    # Context message
    context = f"Текущий запрос пользователя: {req.query}\n"
    context += f"Бюджет (шкала 1-10, где 1=минимальный/хостелы/плацкарт, 5=средний/комфорт, 10=люкс/бизнес-класс): {req.budget}\n"
    if req.city_from:
        context += f"Город отправления: {req.city_from}\n"
    context += f"Город назначения: {req.city}\n"
    context += f"Даты: {req.dates}\n"
    context += f"Искать билеты (разрешено функциями): {'Да' if req.search_tickets else 'Нет'}\n"
    context += f"Искать отели (разрешено функциями): {'Да' if req.search_hotels else 'Нет'}\n"
    
    messages.append({"role": "user", "content": context})

    tools = tools_schema if (req.search_tickets or req.search_hotels) else None

    # Call OpenRouter
    model = "google/gemini-2.5-flash-lite-preview-09-2025" # reliable with tools and JSON
    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools,
            tool_choice="auto" if tools else None,
            response_format={"type": "json_object"}
        )
        
        message = response.choices[0].message
        
        # Tool calling loop
        if message.tool_calls:
            messages.append(message) # Add assistant tool call message
            for tool_call in message.tool_calls:
                func_name = tool_call.function.name
                args = json.loads(tool_call.function.arguments)
                print(f"Calling tool: {func_name} with {args}")
                
                res_str = "{}"
                if func_name == "search_train_tickets_ru" and req.search_tickets:
                    res_str = search_train_tickets_ru(args.get("city_from"), args.get("city_to"), args.get("date"))
                elif func_name == "search_flight_tickets" and req.search_tickets:
                    res_str = search_flight_tickets(args.get("origin_iata"), args.get("destination_iata"), args.get("depart_date"), args.get("return_date"))
                elif func_name == "search_hotels_abroad" and req.search_hotels:
                    res_str = search_hotels_abroad(args.get("city"), args.get("date_in"), args.get("date_out"))
                elif func_name == "get_ru_hotel_links" and req.search_hotels:
                    res_str = get_ru_hotel_links(args.get("city"), args.get("date_in"), args.get("date_out"))
                else:
                    res_str = json.dumps({"error": "Tool not allowed or unrecognized."})
                
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": res_str
                })
                
            # Get final response after tools
            second_response = client.chat.completions.create(
                model=model,
                messages=messages,
                response_format={"type": "json_object"}
            )
            message = second_response.choices[0].message

        # OpenRouter returns markdown blocks like ```json ... ``` sometimes, 
        # so we need to clean the string before parsing it.
        content = message.content
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            import re
            content_fixed = re.sub(r'(?<!\\)\\(?!["\\/bfnrtu])', r'\\\\', content)
            try:
                return json.loads(content_fixed)
            except json.JSONDecodeError:
                return {
                    "route_and_hotels": content or "Не удалось обработать ответ.",
                    "tours": [],
                    "total_price": "-"
                }

    except json.JSONDecodeError as e:
        print(f"JSON Decode Error: {e}")
        print(f"Failed content was: {content}")
        # Return what we can or a formatted error instead of crashing the API
        return {
            "route_and_hotels": f"Произошла ошибка при форматировании ответа от нейросети. Попробуйте еще раз или переформулируйте запрос.",
            "tours": [],
            "total_price": "-"
        }
    except Exception as e:
        print(f"Error: {e}")
        return {
            "route_and_hotels": f"Произошла ошибка при обращении к нейросети: {str(e)}",
            "tours": [],
            "total_price": "-"
        }
