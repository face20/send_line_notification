# ==============================================================================
# สคริปต์แจ้งเตือนสภาพอากาศ จ.สิงห์บุรี ผ่าน LINE Official Account
#
# การทำงาน:
# 1. ดึงข้อมูลพยากรณ์อากาศจาก OpenWeatherMap
# 2. วิเคราะห์หาเหตุการณ์สำคัญ (แดดร้อนจัด, ฝนตกหนัก, พายุ)
# 3. สร้างข้อความแจ้งเตือนสไตล์น่ารัก อ่านง่าย
# 4. ส่งข้อความแบบ Broadcast ไปยังผู้ติดตามทุกคนใน LINE OA
#
# สิ่งที่ต้องตั้งค่าใน GitHub Secrets:
# - LINE_TOKEN: ต้องเป็น "Channel Access Token" ของ Messaging API จาก LINE Developers Console
# - OWM_API_KEY: API Key จาก OpenWeatherMap
# ==============================================================================

import os
import requests
import json
from datetime import datetime, timedelta

# --- 1. ค่าตั้งต้น ---
# พิกัดของ ต. อินทร์บุรี อ. อินทร์บุรี จ. สิงห์บุรี
LAT = "15.0207"
LON = "100.3425"

# ดึงค่า Secrets จาก GitHub Actions
# สำหรับ LINE OA, LINE_TOKEN คือ Channel Access Token
LINE_TOKEN = os.environ.get("LINE_TOKEN") 
OWM_API_KEY = os.environ.get("OWM_API_KEY")

# ตั้งค่า API URLs
OWM_API_URL = f"https://api.openweathermap.org/data/2.5/onecall?lat={LAT}&lon={LON}&exclude=minutely,current&appid={OWM_API_KEY}&units=metric&lang=th"
LINE_BROADCAST_URL = "https://api.line.me/v2/bot/message/broadcast"


# --- 2. ฟังก์ชันหลัก ---

def get_weather_forecast():
    """ดึงข้อมูลพยากรณ์อากาศล่วงหน้า"""
    try:
        response = requests.get(OWM_API_URL)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"เกิดข้อผิดพลาดในการดึงข้อมูลอากาศ: {e}")
        return None

def get_cute_rain_description(weather_id, description, pop):
    """แปลงรายละเอียดฝนเป็นข้อความน่ารักๆ พร้อม emoji"""
    pop_str = f"({pop:.0f}%)"
    if weather_id // 100 == 2: # พายุฝนฟ้าคะนอง
        return f"ระวัง! มีพายุเข้า ⛈️ {pop_str}"
    if weather_id in [502, 503, 504, 521, 522]: # ฝนตกหนัก
        return f"ฝนตกหนักมว๊ากก 🌧️ {pop_str}"
    if weather_id == 501: # ฝนปานกลาง
        return f"ฝนตกปานกลางนะ 💧 {pop_str}"
    return f"{description} {pop_str}"

def format_weather_message(forecast):
    """สร้างข้อความแจ้งเตือนสไตล์น่ารัก อ่านง่าย สำหรับส่งเข้า LINE OA"""
    alert_parts = []
    now_utc = datetime.utcnow()

    # --- ส่วนที่ 1: เช็คแดดร้อน (ทำงานเฉพาะรอบเช้า) ---
    if now_utc.hour < 8:
        today = forecast.get('daily', [])[0]
        uv_index = today.get('uvi', 0)
        max_temp = today.get('temp', {}).get('max', 0)

        if uv_index > 9 or max_temp > 38:
            heat_message = (
                f"☀️ *วันนี้แดดแรงเฟร่อ!*\n\n"
                f"🥵 อากาศร้อนสุดๆ แตะ {max_temp:.1f}°C\n"
                f"👿 ตัวร้าย UV แรงถึง {uv_index:.1f}\n\n"
                f"คำแนะนำ: ทากันแดด พกร่มด้วยน้า~ อยู่ในที่ร่มดีที่สุดจ้า 😎"
            )
            alert_parts.append(heat_message)

    # --- ส่วนที่ 2: เช็คฝนที่สำคัญ ---
    hourly_forecast = forecast.get('hourly', [])[:24]
    first_significant_rain_event = None

    for hour in hourly_forecast:
        if datetime.fromtimestamp(hour['dt']) < datetime.now() - timedelta(hours=7):
            continue

        pop = hour.get('pop', 0) * 100
        weather_id = hour.get('weather', [{}])[0].get('id', 0)
        
        is_significant = False
        if weather_id // 100 == 2 and pop >= 40: is_significant = True
        elif weather_id in [502, 503, 504, 521, 522] and pop >= 50: is_significant = True
        elif weather_id == 501 and pop >= 70: is_significant = True
        
        if is_significant:
            dt_object = datetime.fromtimestamp(hour['dt']) + timedelta(hours=7)
            description = hour.get('weather', [{}])[0].get('description', '')
            
            first_significant_rain_event = {
                "time": dt_object.strftime('%H:%M น.'),
                "cute_desc": get_cute_rain_description(weather_id, description, pop)
            }
            break # เจอเหตุการณ์สำคัญแรกแล้ว หยุดเลย

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
    header = f"📍 อัปเดตอากาศ | อินทร์บุรี\n(ข้อมูลล่าสุด {now_thai})"
    separator = "\n\n- - - - - - - - - - - - - - -\n\n"
    final_message = f"\n{header}\n\n" + separator.join(alert_parts)
    
    return final_message

def send_line_notification(message):
    """ส่งข้อความเป็นแบบ Broadcast ไปยังผู้ติดตาม LINE OA ทุกคน"""
    if not message or not LINE_TOKEN:
        print("ไม่มีข้อความให้ส่ง หรือ Channel Access Token หายไป")
        return

    headers = {
        "Authorization": f"Bearer {LINE_TOKEN}",
        "Content-Type": "application/json"
    }
    
    data = {
        "messages": [{"type": "text", "text": message}]
    }

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
