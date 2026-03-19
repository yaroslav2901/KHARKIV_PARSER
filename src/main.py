import argparse
import os
import asyncio
import json
from zoneinfo import ZoneInfo
from datetime import datetime
from pathlib import Path

# Імпорти модулів проекту
from telegram_notify import send_error, send_message, send_photo
import gener_im_1_G
import gener_im_full
import upload_to_github
from utils import clean_old_files, clean_log
import kharkiv_telegram_parser

BASE = Path(__file__).parent.parent.absolute()
LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "main.log")
FULL_LOG_FILE = os.path.join(LOG_DIR, "full_log.log")
json_file = "Kharkivoblenerho.json"
json_path = BASE / "out" / json_file
os.makedirs(LOG_DIR, exist_ok=True)


def log(message):
    timestamp = datetime.now(ZoneInfo("Europe/Kyiv")).strftime("%Y-%m-%d %H:%M:%S")
    line = f"{timestamp} [main] {message}"
    print(line)
    with open(FULL_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def parse_args():
    parser = argparse.ArgumentParser(description="Run Kharkiv Oblenergo parser")
    parser.add_argument("--parse", "-p", action="store_true", help="Запустити парсинг Telegram-каналу")
    return parser.parse_args()


def main():
    # Видаляємо зображення старше 5 днів у кількох папках
    folders = ["in", "DEBUG_IMAGES"]
    deleted_total = 0

    for folder in folders:
        deleted = clean_old_files(folder, 5, [".png", ".jpg", ".jpeg", ".webp"])
        count = len(deleted)
        deleted_total += count

        if count > 0:
            log(f"🗑️ Видалено {count} старих файлів у папці: {folder}")

    if deleted_total > 0:
        log(f"📦 Разом видалено {deleted_total} старих файлів у вибраних папках")

    # Чистимо лог від даних старше 3 днів
    removed = clean_log(FULL_LOG_FILE, days=3)
    if removed is not None:
        if removed > 0:
            log(f"🧹 Логи очищено — видалено {removed} старих рядків")
    else:
        log("⚠️ Файла логів ще не існує — очищення пропущено")
    
    args = parse_args()
    
    # ---- ПАРСИНГ TELEGRAM-КАНАЛУ ----
    if args.parse:
        log("📱 Запускаю парсинг Telegram-каналу")
        try:
            result = asyncio.run(kharkiv_telegram_parser.main())
            
            if result:
                log("✔️ Парсинг завершено успішно — JSON оновлено")
                
                # ---- ГЕНЕРАЦІЯ ЗОБРАЖЕНЬ ----
                try:
                    log(f"▶️ Запускаю генерацію PNG з {json_path}")
                    gener_im_1_G.generate_from_json(json_path)
                    log("✔️ Генерація PNG завершена")
                except Exception as e:
                    log(f"❌ Помилка при генерації зображень по групах: {e}")
                    send_error(f"❌ Помилка генерації PNG: {e}")
                    return False
                
                try:
                    log(f"▶️ Запускаю генерацію зображення gpv-all-today.png з {json_path}")
                    gener_im_full.generate_from_json(json_path)
                    log("✔️ Генерація зображення gpv-all-today.png завершена")
                except Exception as e:
                    log(f"❌ Помилка при генерації зображення gpv-all-today.png: {e}")
                    send_error(f"❌ Помилка при генерації зображення gpv-all-today.png: {e}")
                    return False

                # ---- ЗАПУСК UPLOAD  GitHub ----
                try:
                    log("▶️ Запускаю завантаження даних на GitHub")
                    upload_to_github.run_upload()
                    log("✔️ Завантаження на GitHub успішно завершене")
                except Exception as e:
                    log(f"❌ Помилка при завантаженні на GitHub: {e}")
                    send_error(f"❌ Помилка при завантаженні на GitHub: {e}")
                    return False
                
                # ---- ВІДПРАВКА ФОТО В TELEGRAM ----
                try:
                    # Читаємо JSON для перевірки дат
                    with open(json_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    
                    # Отримуємо сьогоднішню дату в timestamp
                    today_ts = data.get("fact", {}).get("today")
                    
                    # Отримуємо всі дати з графіками
                    schedules = data.get("fact", {}).get("data", {})
                    schedule_timestamps = [int(ts) for ts in schedules.keys()]
                    
                    # Визначаємо яке фото відправляти
                    if len(schedule_timestamps) >= 2:
                        # Є дві дати (сьогодні + завтра)
                        photo_path = "out/images/gpv-all-tomorrow.png"
                        caption = "🔄 <b>Харківобленерго</b>\nГрафік на завтра\n#Харківобленерго"
                        log("📸 Відправляю графік на ЗАВТРА (є 2 дати)")
                    else:
                        # Тільки одна дата (сьогодні)
                        photo_path = "out/images/gpv-all-today.png"
                        caption = "🔄 <b>Харківобленерго</b>\nГрафік на сьогодні\n#Харківобленерго"
                        log("📸 Відправляю графік на СЬОГОДНІ (1 дата)")
                    
                    # Перевіряємо чи файл існує
                    if os.path.exists(photo_path):
                        send_photo(photo_path, caption)
                        log(f"✔️ Фото відправлено: {photo_path}")
                    else:
                        log(f"⚠️ Файл не знайдено: {photo_path}")
                        send_error(f"⚠️ Файл не знайдено: {photo_path}")
                        
                except Exception as e:
                    log(f"❌ Помилка при відправці фото: {e}")
                    send_error(f"❌ Помилка при відправці фото: {e}")
                
                log("🎉 Повний цикл оновлення завершено успішно")
                return True
            else:
                log("ℹ️ Парсинг завершено — дані не змінились, оновлення не потрібне")
                return True
                
        except Exception as e:
            log(f"❌ Помилка при парсингу Telegram: {e}")
            send_error(f"❌ Помилка при парсингу Telegram: {e}")
            import traceback
            log(traceback.format_exc())
            return False
    else:
        log("ℹ️ Використайте --parse (-p) для запуску парсингу Telegram-каналу")
        log("   Приклад: python3 src/main.py --parse")


if __name__ == "__main__":
    main()