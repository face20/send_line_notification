# ==============================================================================
# สคริปต์แจ้งเตือนสภาพอากาศ จ.สิงห์บุรี ผ่าน LINE Official Account
# เวอร์ชันแก้ไข: เปลี่ยนไปใช้ API (forecast) ที่อยู่ในแผนบริการฟรีแน่นอน
# ==============================================================================

import os
import requests
import json
from datetime import datetime, timedelta

# --- 1. ค่าตั้งต้น ---
LAT = "15.0207"
LON = "100.3425"
LINE_TOKEN = os.environ.get("LINE_TOKEN") 
OWM_API_KEY = os.environ.get("OWM_API_KEY")

# !! เปลี่ยน URL ไปใช้ API ตัวใหม่ที่ฟรีแน่นอน !!
OWM_API_URL = f"https://api.openweathermap.org/data/2.5/forecast?lat={LAT}&lon={LON}&appid={OWM_API_KEY}&units=metric&lang=th"
LINE_BROADCAST_URL = "https://api.line.me/v2/bot/message/broadcast"


# --- 2. ฟังก์ชันหลัก ---

def get_weather_forecast():
    """ดึงข้อมูลพยากรณ์อากาศล่วงหน้าจาก API ตัวใหม่"""
    try:
        response = requests.get(OWM_API_URL)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"เกิดข้อผิดพลาดในการดึงข้อมูลอากาศ: {e}")
        return None

def get_cute_rain_description(weather_id, description, pop):
    """แปลงรายละเอียดฝนเป็นข้อความน่ารักๆ (เหมือนเดิม)"""
    pop_str = f"({pop:.0f}%)"
    if weather_id // 100 == 2:
        return f"ระวัง! มีพายุเข้า ⛈️ {pop_str}"
    if weather_id in [502, 503, 504, 521, 522]:
        return f"ฝนตกหนักมว๊ากก 🌧️ {pop_str}"
    if weather_id == 501:
        return f"ฝนตกปานกลางนะ 💧 {pop_str}"
    return f"{description} {pop_str}"

def format_weather_message(forecast):
    """สร้างข้อความแจ้งเตือนจากข้อมูลของ API ตัวใหม่"""
    alert_parts = []
    
    # --- ส่วนที่ 1: เช็คแดดร้อน (จากข้อมูลพยากรณ์ 24 ชม. ข้างหน้า) ---
    # API ตัวนี้ไม่มีค่า UV เราจะเช็คจากอุณหภูมิสูงสุดแทน
    max_temp = -99
    forecast_list = forecast.get('list', [])[:8] # เอา 8 ช่วงเวลา = 24 ชม.
    for period in forecast_list:
        if period['main']['temp_max'] > max_temp:
            max_temp = period['main']['temp_max']

    if max_temp > 38:
        heat_message = (
            f"☀️ *พยากรณ์อากาศร้อนจัด!*\n\n"
            f"🥵 อุณหภูมิอาจพุ่งสูงสุดถึง {max_temp:.1f}°C ใน 24 ชม. ข้างหน้า\n\n"
            f"คำแนะนำ: อากาศร้อนจัด พยายามอยู่ในที่ร่มและดื่มน้ำเยอะๆ น้า 😎"
        )
        alert_parts.append(heat_message)

    # --- ส่วนที่ 2: เช็คฝนที่สำคัญ ---
    first_significant_rain_event = None
    for period in forecast_list: # ใช้ข้อมูลชุดเดียวกับข้างบน
        pop = period.get('pop', 0) * 100
        weather_id = period.get('weather', [{}])[0].get('id', 0)
        
        is_significant = False
        if weather_id // 100 == 2 and pop >= 40: is_significant = True
        elif weather_id in [502, 503, 504, 521, 522] and pop >= 50: is_significant = True
        elif weather_id == 501 and pop >= 70: is_significant = True
        
        if is_significant:
            dt_object = datetime.fromtimestamp(period['dt']) + timedelta(hours=7)
            description = period.get('weather', [{}])[0].get('description', '')
            
            first_significant_rain_event = {
                "time": dt_object.strftime('%H:%M น.'),
                "cute_desc": get_cute_rain_description(weather_id, description, pop)
            }
            break

    if first_significant_rain_event:
        rain_message = (
            f"☔️ *เตรียมร่มด่วน! ฝนกำลังมา!*\n\n"
            f"⏰ คาดว่าจะเริ่มตกช่วง *{first_significant_rain_event['time']}*\n"
            f"ลักษณะ: {first_significant_rain_event['cute_desc']}\n\n"
            f"คำแนะนำ: เก็บผ้าที่ตากด่วน! ใครจะกลับบ้านรีบเลยน้า 👕👖"
        )
        alert_parts.append(rain_message)

    # --- ส่วนที่ 3: ประกอบร่างข้อความสุดท้าย ---
    if not alert_parts:
        print("อากาศดี ไม่มีอะไรน่าห่วง ไม่ส่งแจ้งเตือนจ้า~")
        return None

    now_thai = datetime.now().strftime('%H:%M น.')
    city_name = forecast.get('city', {}).get('name', 'อินทร์บุรี')
    header = f"📍 อัปเดตอากาศ | {city_name}\n(ข้อมูลล่าสุด {now_thai})"
    separator = "\n\n- - - - - - - - - - - - - - -\n\n"
    final_message = f"\n{header}\n\n" + separator.join(alert_parts)
    
    return final_message

def send_line_notification(message):
    """ส่งข้อความแบบ Broadcast ไปยังผู้ติดตาม LINE OA ทุกคน"""
    if not message or not LINE_TOKEN:
        return
    headers = {"Authorization": f"Bearer {LINE_TOKEN}", "Content-Type": "application/json"}
    data = {"messages": [{"type": "text", "text": message}]}
    try:
        response = requests.post(LINE_BROADCAST_URL, headers=headers, data=json.dumps(data))
        response.raise_for_status()
        print("ส่ง Broadcast เข้า LINE OA สำเร็จแล้ว!")
    except requests.exceptions.RequestException as e:
        print(f"อุ๊ปส์! ส่ง Broadcast เข้า LINE OA ไม่ได้: {e.response.text}")

# --- 3. ส่วนที่รันโปรแกรม ---
if __name__ == "__main__":
    print("===== เริ่มกระบวนการเช็คสภาพอากาศ =====")
    weather_data = get_weather_forecast()
    if weather_data:
        notification_message = format_weather_message(weather_data)
        if notification_message:
            send_line_notification(notification_message)
    print("===== กระบวนการเสร็จสิ้น =====")
