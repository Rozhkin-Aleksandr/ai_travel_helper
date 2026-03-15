from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import os
import json
import openai
from dotenv import load_dotenv

from tools import search_train_tickets_ru, search_flight_tickets, search_hotels_abroad

load_dotenv(dotenv_path="../.env")

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
            "description": "Поиск авиабилетов. Используется для поездок за границу или по России, когда на поезде долго.",
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
    }
]

SYSTEM_PROMPT = """
Ты - ИИ-агент по подбору авиа и жд билетов и составлению персональных туров.
Отвечай структурировано в формате JSON.
Твой ответ должен строго соответствовать следующей структуре JSON:
{
  "route_and_hotels": "Строка в формате Markdown. Здесь опиши маршрут, как лучше добраться (поезд или самолет), примерное время и цену билетов. Если пользователь поставил галочки для поиска и ты вызвал функции, используй их результаты! Если город в РФ (Россия) - отели не ищи функциями, а просто посоветуй ссылки на sutochno.ru, avito, Яндекс Путешествия. Если вне РФ - ищи отели функцией.",
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
    
    # Context message
    context = f"Текущий запрос пользователя: {req.query}\n"
    context += f"Бюджет: {req.budget}\n"
    context += f"Город назначения: {req.city}\n"
    context += f"Даты: {req.dates}\n"
    context += f"Искать билеты (разрешено функциями): {'Да' if req.search_tickets else 'Нет'}\n"
    context += f"Искать отели (разрешено функциями): {'Да' if req.search_hotels else 'Нет'}\n"
    
    messages.append({"role": "user", "content": context})
    
    # Add history
    for h in req.history:
        messages.append({"role": h.role, "content": h.content})

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
                    res_str = search_flight_tickets(args.get("city_from"), args.get("city_to"), args.get("date"))
                elif func_name == "search_hotels_abroad" and req.search_hotels:
                    res_str = search_hotels_abroad(args.get("city"), args.get("date_in"), args.get("date_out"))
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

        content = message.content
        return json.loads(content)

    except Exception as e:
        print(f"Error: {e}")
        return {
            "route_and_hotels": f"Произошла ошибка при обращении к нейросети: {str(e)}",
            "tours": [],
            "total_price": "-"
        }
