import os
import csv
import json
import re
import requests
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(dotenv_path=os.path.join(BASE_DIR, ".env"))

# Load city maps
try:
    with open(os.path.join(BASE_DIR, "yandex_cities.json"), "r", encoding="utf-8") as f:
        YANDEX_CITIES = json.load(f)
except Exception as e:
    print("Warning: failed to load yandex_cities.json", e)
    YANDEX_CITIES = {}

try:
    with open(os.path.join(BASE_DIR, "tutu_cities.json"), "r", encoding="utf-8") as f:
        TUTU_CITIES = json.load(f)
except Exception as e:
    print("Warning: failed to load tutu_cities.json", e)
    TUTU_CITIES = {}

YANDEX_API_KEY = os.getenv('YANDEX_API_KEY')
AVIASALES_API_KEY = os.getenv('AVIASALES_API_KEY')
BOOKING_API_KEY = os.getenv('RAPIDAPI_KEY')

CAR_TYPES_RU = {
    'plazcard': 'Плацкарт',
    'coupe': 'Купе',
    'lux': 'СВ (Люкс)',
    'soft': 'Мягкий',
    'sitting': 'Сидячий'
}

def normalize_train_number(num_str):
    return re.sub(r'[^a-zA-Zа-яА-Я0-9]', '', str(num_str)).upper()

def get_tutu_prices_map(origin_id, destination_id):
    url = "https://suggest.travelpayouts.com/search"
    params = {
        'service': 'tutu_trains',
        'term': origin_id,
        'term2': destination_id,
        'callback': 'n'
    }
    price_map = {}
    try:
        response = requests.get(url, params=params, timeout=10)
        raw_text = response.text
        start_idx = raw_text.find('(') + 1
        end_idx = raw_text.rfind(')')
        if start_idx <= 0 or end_idx == -1:
            print(f"Error fetching tutu prices: {raw_text[:100]}")
            return price_map
        data = json.loads(raw_text[start_idx:end_idx])
        for trip in data.get('trips', []):
            norm_num = normalize_train_number(trip.get('trainNumber', ''))
            price_map[norm_num] = trip.get('categories', [])
    except Exception as e:
        print(f"Error fetching tutu prices: {e}")
    return price_map

def find_tutu_city_id(city_name):
    city_lower = city_name.lower()
    return TUTU_CITIES.get(city_lower)

def find_yandex_city_id(city_name):
    city_lower = city_name.lower()
    return YANDEX_CITIES.get(city_lower)

def search_train_tickets_ru(city_from, city_to, date):
    print(f"Searching trains: {city_from} -> {city_to} on {date}")
    tutu_from = find_tutu_city_id(city_from)
    tutu_to = find_tutu_city_id(city_to)
    
    yandex_from = find_yandex_city_id(city_from)
    yandex_to = find_yandex_city_id(city_to)
    
    if not tutu_from or not tutu_to:
        return json.dumps({"error": "City not found in Tutu database."})

    tutu_prices = get_tutu_prices_map(tutu_from, tutu_to)
    
    yandex_api_key = os.getenv('YANDEX_API_KEY')
    url = "https://api.rasp.yandex.net/v3.0/search/"
    params = {
        'apikey': yandex_api_key,
        'from': yandex_from,
        'to': yandex_to,
        'date': date,
        'format': 'json',
        'lang': 'ru_RU',
        'transport_types': 'train',
        'system': 'yandex'
    }
    
    try:
        response = requests.get(url, params=params)
        data = response.json()
        segments = data.get('segments', [])
        
        result_trains = []
        for segment in segments[:5]: # take top 5
            thread = segment.get('thread', {})
            raw_train_num = thread.get('number', 'Б/Н')
            title = thread.get('short_title', thread.get('title', ''))
            dep_str = segment.get('departure', '')[11:16]
            arr_str = segment.get('arrival', '')[11:16]
            
            norm_num = normalize_train_number(raw_train_num)
            prices = []
            if norm_num in tutu_prices:
                for cat in tutu_prices[norm_num]:
                    raw_type = cat.get('type', 'unknown')
                    car_type = CAR_TYPES_RU.get(raw_type, raw_type)
                    base_price = cat.get('price', 0)
                    prices.append({"car_type": car_type, "price": base_price * 1.5})
            
            result_trains.append({
                "train_number": raw_train_num,
                "title": title,
                "departure": dep_str,
                "arrival": arr_str,
                "prices": prices
            })
            
        return json.dumps({"trains": result_trains})
    except Exception as e:
        return json.dumps({"error": str(e)})


def get_iata(city_name):
    # Устарело, IATA коды теперь отдает сама нейросеть
    return None

def search_flight_tickets(origin_iata, destination_iata, depart_date, return_date=None):
    print(f"Searching flights: {origin_iata} -> {destination_iata} on {depart_date} (Return: {return_date})")
    
    if not origin_iata or not destination_iata:
        err_msg = "IATA code is missing"
        print(f"[DEBUG] {err_msg}")
        return json.dumps({"error": err_msg})
        
    url = "https://api.travelpayouts.com/v2/prices/latest"
    
    # API v2 filters
    # beginning_of_period needs to be the first day of the month (e.g. 2026-05-01 instead of 2026-05-10)
    month_start = f"{depart_date[:7]}-01"
    
    querystring = {
        "currency": "rub",
        "origin": origin_iata.upper(),
        "destination": destination_iata.upper(),
        "beginning_of_period": month_start,
        "period_type": "month",
        "limit": "30",
        "sorting": "price",
        "trip_class": "0"
    }
    
    # If a return date is provided, we search for roundtrip
    if return_date:
        querystring["one_way"] = "false"
    else:
        querystring["one_way"] = "true"
        
    api_key = os.getenv('AVIASALES_API_KEY')
    headers = {'x-access-token': api_key}
    
    try:
        response = requests.get(url, headers=headers, params=querystring)
        print(f"[DEBUG] Flights API status: {response.status_code}")
        if response.status_code != 200:
            print(f"[DEBUG] API Error response: {response.text}")
        data = response.json()
        print(f"[DEBUG] Flights response body: {json.dumps(data, ensure_ascii=False)[:300]}...")
        if data.get("success") and data.get("data"):
            # Return top 5 results as requested
            return json.dumps({"flights": data["data"][:5]})
        return json.dumps({"info": "No flights found", "raw": data})
    except Exception as e:
        print(f"[DEBUG] search_flight_tickets error: {e}")
        return json.dumps({"error": str(e)})


def search_hotels_abroad(city, date_in, date_out):
    print(f"Searching hotels abroad: {city} {date_in} - {date_out}")
    HEADERS = {
        'x-rapidapi-key': BOOKING_API_KEY,
        'x-rapidapi-host': "booking-com15.p.rapidapi.com",
    }
    
    dest_url = "https://booking-com15.p.rapidapi.com/api/v1/hotels/searchDestination"
    try:
        dest_response = requests.get(dest_url, headers=HEADERS, params={"query": city})
        dest_data = dest_response.json()
        if not dest_data.get('data'):
            return json.dumps({"error": "City not found on Booking"})
            
        first_result = dest_data['data'][0]
        dest_id = first_result['dest_id']
        search_type = first_result['search_type']
        
        hotels_url = "https://booking-com15.p.rapidapi.com/api/v1/hotels/searchHotels"
        hotel_params = {
            "dest_id": dest_id,
            "search_type": search_type,
            "arrival_date": date_in,
            "departure_date": date_out,
            "adults": "2",
            "room_qty": "1",
            "page_number": "1"
        }
        
        hotels_response = requests.get(hotels_url, headers=HEADERS, params=hotel_params)
        hotels_data = hotels_response.json()
        
        results = []
        if 'data' in hotels_data and 'hotels' in hotels_data['data']:
            for hotel in hotels_data['data']['hotels'][:5]:
                prop = hotel.get('property', {})
                name = prop.get('name', 'Без названия')
                
                # Извлекаем цену безопасно
                price = "Неизвестно"
                currency = ""
                price_bd = prop.get('priceBreakdown', {}).get('grossPrice', {})
                if price_bd:
                    price = price_bd.get('value', 'Неизвестно')
                    currency = price_bd.get('currency', '')
                
                # Извлекаем фото (Booking API обычно отдает photoUrls массивом)
                photo_url = ""
                photo_urls = prop.get('photoUrls', [])
                if photo_urls and len(photo_urls) > 0:
                    # Можно взять первое фото из массива
                    photo_url = photo_urls[0]
                
                results.append({
                    "name": name, 
                    "price": price, 
                    "currency": currency,
                    "photo": photo_url
                })
        return json.dumps({"hotels": results})
        
    except Exception as e:
        return json.dumps({"error": str(e)})

import urllib.parse

def translit_city(city):
    mapping = {
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e', 'ж': 'zh',
        'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o',
        'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'h', 'ц': 'ts',
        'ч': 'ch', 'ш': 'sh', 'щ': 'shch', 'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu',
        'я': 'ya', ' ': '-', '-': '-'
    }
    return ''.join(mapping.get(c, c) for c in city.lower())

def get_ru_hotel_links(city, date_in, date_out):
    print(f"Generating RU hotel links for: {city} {date_in} - {date_out}")
    city_translit = translit_city(city)
    city_url = urllib.parse.quote(city)
    
    avito_link = f"https://www.avito.ru/{city_translit}/kvartiry/sdam/posutochno/"
    sutochno_link = f"https://sutochno.ru/front/searchapp/search?occupied={date_in};{date_out}&guests_adults=2&term={city_url}"
    yandex_link = f"https://travel.yandex.ru/hotels/{city_translit}/?adults=2&checkinDate={date_in}&checkoutDate={date_out}"
    
    return json.dumps({
        "info": "Успешно сгенерированы ссылки. Пожалуйста, передайте их пользователю в ответе.",
        "links": {
            "avito": avito_link,
            "sutochno": sutochno_link,
            "yandex_travel": yandex_link
        }
    })
