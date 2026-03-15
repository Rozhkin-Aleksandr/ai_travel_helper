import os
import csv
import json
import re
import requests
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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
BOOKING_API_KEY = "7d42b4d30dmsh570ecb00dc077f7p1a42d2jsn5af1e2013714"

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
    
    url = "https://api.rasp.yandex.net/v3.0/search/"
    params = {
        'apikey': YANDEX_API_KEY,
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
    url = "https://engine.hotellook.com/api/v2/lookup.json"
    querystring = {"query": city_name, "lang": "ru", "lookFor": "city", "limit": "1", "token": AVIASALES_API_KEY}
    try:
        resp = requests.get(url, params=querystring, headers={'x-access-token': AVIASALES_API_KEY}).json()
        if resp and resp.get('results') and resp['results'].get('locations'):
            return resp['results']['locations'][0]['iata']
    except Exception as e:
        pass
    return None

def search_flight_tickets(city_from, city_to, date):
    print(f"Searching flights: {city_from} -> {city_to} on {date}")
    origin = get_iata(city_from)
    destination = get_iata(city_to)
    
    if not origin or not destination:
        return json.dumps({"error": "IATA code not found for one of the cities."})
        
    url = "https://api.travelpayouts.com/v1/prices/cheap"
    querystring = {"origin": origin, "destination": destination, "depart_date": date}
    headers = {'x-access-token': AVIASALES_API_KEY}
    
    try:
        response = requests.get(url, headers=headers, params=querystring)
        data = response.json()
        if data.get("success") and data.get("data") and destination in data["data"]:
            flights = data["data"][destination]
            # flights is usually a dict keyed by some id, let's just return the values
            return json.dumps({"flights": list(flights.values())[:5]})
        return json.dumps({"info": "No flights found", "raw": data})
    except Exception as e:
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
                name = hotel['property']['name']
                price = hotel['property']['priceBreakdown']['grossPrice']['value']
                currency = hotel['property']['priceBreakdown']['grossPrice']['currency']
                results.append({"name": name, "price": price, "currency": currency})
        return json.dumps({"hotels": results})
        
    except Exception as e:
        return json.dumps({"error": str(e)})
