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

ASK_CAR = ("Напишіть марку, модель і рік авто — наприклад «Ford Focus 3 2015» або «Шкода Октавія 2012», "
           "і я підберу штатну магнітолу з цінами.")
HELLO = ("Привіт! Я бот магазину «Юг Авто Звук» 🚗\n\n" + ASK_CAR +
         "\n\nХочете, щоб менеджер передзвонив? Надішліть номер телефону.")

# Частые вопросы: (основы слов RU/UA, ответ). Факты — из my-project/facts.json.
FAQ = [
    (("доставк", "відправ", "отправ", "пошт", "почт"),
     "🚚 Відправляємо Новою Поштою по всій Україні, без передоплати — оплата при отриманні."),
    (("оплат", "частин", "розстроч", "рассроч", "кредит", "карт"),
     "💳 Можна частинами до 9 платежів без переплат (ПриватБанк, ПУМБ, monobank, Розетка, А-Банк, ОТП Банк), "
     "карткою через Пром-оплату або при отриманні — без передоплати."),
    (("гарант", "поверн", "возврат", "обмін", "обмен"),
     "🛡 Гарантія 1 рік, обмін і повернення 14 днів."),
    (("встанов", "установ", "монтаж", "підключ", "подключ", "стане", "встане", "підійде", "подойдет"),
     "🔧 Магнітола штатна: рамка саме під ваше авто, підключення роз'єм-в-роз'єм без різання проводки. "
     "У комплекті рамка, проводка, навіть болтики. Усі штатні функції зберігаються, кнопки на кермі працюють."),
    (("камер",),
     "📷 Можна підключити камеру заднього виду в плафон підсвітки номера, AHD 1920×1080, провід 6 метрів у комплекті."),
    (("carplay", "кар", "android", "андро"),
     "📱 Бездротовий CarPlay і Android Auto: дзвінки, карта, музика і голосовий помічник на екрані авто."),
    (("замов", "заказ", "купи", "купл", "оформ", "придба"),
     "Чудово, оформимо! 🙌 Напишіть марку, модель і рік авто — підберу магнітолу. "
     "Або одразу надішліть номер телефону — менеджер передзвонить і все оформить."),
    (("дякую", "спасиб"), "Будь ласка! Якщо будуть питання — пишіть 🙌"),
]
# Общие фразы — отвечаем, только если конкретных вопросов выше нет (первое совпадение)
FALLBACK = [
    (("наявн", "наличи", "есть", "є"),
     "✅ Бот показує тільки те, що є в наявності. " + ASK_CAR),
    (("ціна", "цін", "цена", "цен", "скільки", "сколько", "стоит", "стоїть", "коштує", "магнітол", "магнитол",
      "підібр", "подбер", "подобр", "нужн", "потрібн", "треба", "надо", "хочу", "подска", "підкаж", "допомож",
      "помог", "порад", "посовет"),
     "Підберу! " + ASK_CAR),
]
GREET = ("привіт", "привет", "вітаю", "добр", "здравств", "здоров", "hello", "hi", "хай", "салют")


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
        words = re.findall(r"[\w']+", text.lower())
        has = lambda stems: any(w.startswith(s) for w in words for s in stems)
        faq = list(dict.fromkeys(a for stems, a in FAQ if has(stems)))
        faq = faq or [a for stems, a in FALLBACK if has(stems)][:1]
        if faq or has(GREET):
            greet = "Вітаю! 👋 " if has(GREET) else ""
            return greet + ("\n\n".join(faq) if faq else ASK_CAR), False
        return ("Не знайшов магнітолу під це авто 🤔 Напишіть марку і модель латиницею (наприклад «Toyota Camry 40 2010») "
                "або надішліть номер телефону — менеджер підбере вручну."), True
    sections = {}  # ссылка раздела -> (название, цена «від»)
    for p in items:
        sec = section(p["url"])
        if sec and (sec[1] not in sections or p["price"] < sections[sec[1]][1]):
            sections[sec[1]] = (sec[0], p["price"])
    if sections:
        lines = ["Ось розділ з магнітолами під ваше авто:\n"]
        for url, (name, price) in sections.items():
            lines.append(f"• {name} — від {price:,} грн".replace(",", " ") + f"\n  {url}")
    else:  # сайт не ответил — даём сами товары
        lines = ["Ось що є під ваше авто:\n"]
        for p in items:
            lines.append(f"• {p['name']}\n  {p['price']:,} грн".replace(",", " ") + f"\n  {p['url']}")
    lines.append("\nГарантія 1 рік · Нова Пошта без передоплати.\nЗалиште номер телефону — допоможемо з вибором і встановленням.")
    return "\n".join(lines), False


SECTIONS = {}


def section(product_url):
    """(название, ссылка) раздела модели авто — из хлебных крошек страницы товара; None, если сайт не ответил."""
    if product_url not in SECTIONS:
        try:
            req = urllib.request.Request(product_url, headers={"User-Agent": "Mozilla/5.0"})
            html = urllib.request.urlopen(req, timeout=10).read().decode("utf-8", "ignore")
        except Exception:
            return None
        SECTIONS[product_url] = None
        for block in re.findall(r'<script[^>]*ld\+json[^>]*>(.*?)</script>', html, re.S):
            try:
                data = json.loads(block)
            except ValueError:
                continue
            if isinstance(data, dict) and data.get("@type") == "BreadcrumbList":
                crumbs = [i["item"] for i in data["itemListElement"]]
                if len(crumbs) >= 2 and "/g" in crumbs[-2]["@id"]:
                    root = "/".join(product_url.split("/")[:3])
                    SECTIONS[product_url] = (crumbs[-2]["name"], root + crumbs[-2]["@id"])
    return SECTIONS[product_url]


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
