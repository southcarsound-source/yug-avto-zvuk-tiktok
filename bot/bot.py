"""Telegram-бот «Юг Авто Звук»: подбирает штатную магнитолу по машине и принимает заявки.

Каталог (catalog.json) — штатные магнитолы в наличии из каталога Prom (south-car-sound.com.ua).
shortcut: потом перевести ссылки на shtatni-magnitoly.com.ua, когда будет выгрузка нового сайта.

Запуск:  python bot.py   (токен и чат владельца — в bot/.env: BOT_TOKEN=..., OWNER_CHAT_ID=...)
Без библиотек: только стандартный Python, long polling.
"""
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
CATALOG = json.loads((HERE / "catalog.json").read_text(encoding="utf-8"))

# shortcut: только популярные марки кириллицей; остальные клиент пишет латиницей
CYR = {
    "шкода": "skoda", "шкоду": "skoda", "тойота": "toyota", "тойоту": "toyota", "фольксваген": "volkswagen",
    "фольц": "volkswagen", "ауди": "audi", "ауді": "audi", "бмв": "bmw", "мерседес": "mercedes",
    "форд": "ford", "фокус": "focus", "хюндай": "hyundai", "хендай": "hyundai", "хундай": "hyundai",
    "кіа": "kia", "киа": "kia", "рено": "renault", "ниссан": "nissan", "ніссан": "nissan",
    "мазда": "mazda", "мицубиси": "mitsubishi", "міцубісі": "mitsubishi", "опель": "opel",
    "пежо": "peugeot", "ситроен": "citroen", "сітроен": "citroen", "шевроле": "chevrolet",
    "хонда": "honda", "субару": "subaru", "лада": "lada", "ваз": "lada", "дачия": "dacia",
    "октавия": "octavia", "октавія": "octavia", "камри": "camry", "камрі": "camry", "пассат": "passat",
    "гольф": "golf", "джетта": "jetta", "туарег": "touareg", "транзит": "transit", "спринтер": "sprinter",
    "віто": "vito", "вито": "vito", "акцент": "accent", "гетц": "getz", "соната": "sonata",
    "спортейдж": "sportage", "туксон": "tucson", "тусан": "tucson", "логан": "logan", "дастер": "duster",
}
PHONE = re.compile(r"(?:\+?38)?0\d{9}")
YEARS = re.compile(r"((?:19|20)\d\d)\s*[-–]\s*((?:19|20)\d\d)")

HELLO = ("Привіт! Я бот магазину «Юг Авто Звук» 🚗\n\n"
         "Напишіть марку, модель і рік авто — наприклад «Ford Focus 3 2015» або «Шкода Октавія 2012», "
         "і я підберу штатну магнітолу з цінами.\n\n"
         "Хочете, щоб менеджер передзвонив? Надішліть номер телефону.")


def env():
    vals = {}
    for line in (HERE / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip()
    return vals


def search(text, limit=3):
    words = [CYR.get(w, w) for w in re.findall(r"[\w']+", text.lower())]
    year = next((int(w) for w in words if w.isdigit() and 1990 <= int(w) <= 2035), None)
    words = [w for w in words if not (w.isdigit() and len(w) == 4)]
    if not words:
        return []
    found = []
    for p in CATALOG:
        name = p["name"].lower()
        tokens = set(re.findall(r"[\w']+", name))
        hits = sum(w in tokens for w in words)
        if hits < min(2, len(words)):
            continue
        if year:
            rng = YEARS.search(p["name"])
            if rng and not int(rng[1]) <= year <= int(rng[2]):
                continue
        found.append((-hits, not rng if year else 0, p["price"], p))  # с годами в названии — выше
    found.sort(key=lambda x: x[:3])
    unique = {}
    for *_, p in found:  # один и тот же товар в каталоге бывает под разными id
        unique.setdefault(p["name"], p)
    return list(unique.values())[:limit]


def answer(text):
    """Ответ бота на текст клиента; второй элемент — нужно ли переслать владельцу как заявку."""
    if text.startswith("/start") or text.startswith("/help"):
        return HELLO, False
    if PHONE.search(re.sub(r"[\s()-]", "", text)):
        return "Дякуємо! Наш менеджер передзвонить вам найближчим часом 📞", True
    items = search(text)
    if not items:
        return ("Не знайшов магнітолу під це авто 🤔 Напишіть марку і модель латиницею (наприклад «Toyota Camry 40 2010») "
                "або надішліть номер телефону — менеджер підбере вручну."), True
    lines = ["Ось що є під ваше авто:\n"]
    for p in items:
        lines.append(f"• {p['name']}\n  {p['price']:,} грн".replace(",", " ") + f"\n  {p['url']}")
    lines.append("\nГарантія 1 рік · Нова Пошта без передоплати.\nЗалиште номер телефону — допоможемо з вибором і встановленням.")
    return "\n".join(lines), False


def api(token, method, **params):
    data = urllib.parse.urlencode(params).encode()
    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/{method}", data, timeout=70) as r:
        return json.loads(r.read())["result"]


def main():
    cfg = env()
    token, owner = cfg["BOT_TOKEN"], cfg.get("OWNER_CHAT_ID")
    offset = 0
    print("Бот запущено")
    while True:
        try:
            updates = api(token, "getUpdates", offset=offset, timeout=50)
        except Exception as e:  # сеть пропала — ждём и пробуем снова, не падаем
            print("Помилка мережі:", e)
            time.sleep(5)
            continue
        for u in updates:
            offset = u["update_id"] + 1
            msg = u.get("message")
            if not msg or "text" not in msg:
                continue
            text, chat = msg["text"], msg["chat"]["id"]
            reply, is_lead = answer(text)
            try:
                api(token, "sendMessage", chat_id=chat, text=reply, disable_web_page_preview="true")
                if is_lead and owner and str(chat) != owner:
                    who = msg["from"].get("username") or msg["from"].get("first_name", "")
                    api(token, "sendMessage", chat_id=owner, text=f"📥 Заявка з бота від @{who} (id {chat}):\n{text}")
            except Exception as e:
                print("Не вдалося відповісти:", e)


if __name__ == "__main__":
    main()
