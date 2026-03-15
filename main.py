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
    budget: str
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
Отвечай структурировано в формате JSON.
Твой ответ должен строго соответствовать следующей структуре JSON:
{
  "route_and_hotels": "Строка в формате Markdown. Здесь опиши маршрут, как лучше добраться (поезд или самолет). Если были найдены авиабилеты - обязательно выведи ВСЕ найденные варианты (до 5 штук) списком и добавь небольшой анализ: какой вариант лучше подходит под предпочтения и бюджет пользователя. ВАЖНО: цены на авиабилеты уже указаны за билеты ТУДА И ОБРАТНО. Если город в РФ - вызови функцию get_ru_hotel_links и посоветуй полученные ссылки. Если вне РФ - ищи отели функцией search_hotels_abroad. НИКОГДА не упоминай пользователю технические детали работы, названия функций (get_ru_hotel_links, search_hotels_abroad и т.д.) или фразы в духе 'поиск через функции был запрещен'. Общайся максимально естественно, как живой заботливый турагент.",
  "tours": [
    {
      "title": "Название тура",
      "description": "Описание тура, примерная разметка по дням, достопримечательности."
    }
  ],
  "total_price": "Примерная цена за всю поездку текстом"
}
Пользователь может выбрать до 3 туров, поэтому в массиве tours предоставь 3 разных интересных варианта (или больше/меньше в зависимости от контекста).
Если это продолжение беседы и пользователь просит подробности одного тура, в массиве tours можешь вернуть только этот 1 тур с более детальным описанием, или вообще оставить массив пустым, если это просто ответ на вопрос (тогда пиши ответ в route_and_hotels).
"""

@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    # Add history
    for h in req.history:
        messages.append({"role": h.role, "content": h.content})
        
    # Context message
    context = f"Текущий запрос пользователя: {req.query}\n"
    context += f"Бюджет: {req.budget}\n"
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
        if content.startswith("```json"):
            content = content[7:]
        if content.endswith("```"):
            content = content[:-3]
        
        # Some models use ``` instead of ```json
        if content.startswith("```"):
            content = content[3:]
            
        content = content.strip()
            
        return json.loads(content)

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
