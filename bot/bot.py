"""Telegram-бот «Юг Авто Звук»: подбирает штатную магнитолу по машине и принимает заявки.

Каталог (catalog.json) — штатные магнитолы в наличии из каталога Prom (south-car-sound.com.ua).
shortcut: потом перевести ссылки на shtatni-magnitoly.com.ua, когда будет выгрузка нового сайта.

Запуск:  python bot.py   (BOT_TOKEN, OWNER_CHAT_ID, DATABASE_URL — в bot/.env или в переменных окружения)
Переписка и заявки хранятся в Postgres (Railway), владелец смотрит их командами /leads и /stats.
"""
import json
import os
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
    """Настройки из bot/.env (локально) и переменных окружения (Railway)."""
    vals = {}
    if (HERE / ".env").exists():
        for line in (HERE / ".env").read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                vals[k.strip()] = v.strip()
    vals.update({k: os.environ[k] for k in ("BOT_TOKEN", "OWNER_CHAT_ID", "DATABASE_URL") if os.environ.get(k)})
    return vals


class DB:
    """Переписка и заявки в Postgres (DATABASE_URL). Без базы бот работает, просто ничего не хранит."""

    def __init__(self, url):
        self.url, self.conn = url, None

    def run(self, sql, args=()):
        if not self.url:
            return []
        for attempt in (1, 2):  # соединение с базой могло оборваться — переподключаемся один раз
            try:
                if self.conn is None:
                    import psycopg  # нужен только с базой
                    self.conn = psycopg.connect(self.url, autocommit=True)
                    self.conn.execute(
                        "create table if not exists messages (id serial primary key, chat_id bigint, username text,"
                        " text text, reply text, is_lead boolean, created_at timestamptz default now())")
                cur = self.conn.execute(sql, args)
                return cur.fetchall() if cur.description else []
            except Exception as e:
                print("Помилка бази:", e)
                self.conn = None
        return []

    def save(self, chat, username, text, reply, is_lead):
        self.run("insert into messages (chat_id, username, text, reply, is_lead) values (%s, %s, %s, %s, %s)",
                 (chat, username, text, reply, is_lead))

    def leads(self, limit=10):
        rows = self.run("select created_at, username, chat_id, text from messages where is_lead"
                        " order by id desc limit %s", (limit,))
        if not rows:
            return "Заявок у базі поки немає."
        return "📥 Останні заявки з бази:\n\n" + "\n\n".join(
            f"{t:%d.%m %H:%M} UTC · @{u or '—'} (id {c})\n{x}" for t, u, c, x in rows)

    def stats(self):
        rows = self.run("select count(*), count(*) filter (where is_lead), count(distinct chat_id) from messages")
        if not rows:
            return "База не підключена."
        total, leads, people = rows[0]
        return f"📊 У базі: {total} повідомлень, {leads} заявок, {people} людей."


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
        if sec:
            url = sec[1] + "?sort=price"  # на сайте сразу от дешёвых к дорогим
            sections[url] = (sec[0], min_price(url) or p["price"])
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
PRICES = {}


def ld_json(url):
    """Все JSON-LD блоки страницы сайта; [] если сайт не ответил."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        html = urllib.request.urlopen(req, timeout=10).read().decode("utf-8", "ignore")
    except Exception:
        return []
    out = []
    for block in re.findall(r'<script[^>]*ld\+json[^>]*>(.*?)</script>', html, re.S):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        out += data if isinstance(data, list) else [data]
    return out


def min_price(section_url):
    """Самая дешёвая штатная магнитола в наличии на странице раздела (отсортированной по цене)."""
    if section_url not in PRICES:
        prices = [float(x["offers"]["price"]) for x in ld_json(section_url)
                  if x.get("@type") == "Product" and x.get("name", "").lower().startswith("штатна магнітола")
                  and "InStock" in x.get("offers", {}).get("availability", "")]
        PRICES[section_url] = round(min(prices)) if prices else None
    return PRICES[section_url]


def section(product_url):
    """(название, ссылка) раздела модели авто — из хлебных крошек страницы товара; None, если сайт не ответил."""
    if product_url not in SECTIONS:
        blocks = ld_json(product_url)
        if not blocks:
            return None  # не кэшируем: сайт мог просто не ответить
        SECTIONS[product_url] = None
        for data in blocks:
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
    db = DB(cfg.get("DATABASE_URL"))
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
            who = msg["from"].get("username") or msg["from"].get("first_name", "")
            if str(chat) == owner and text in ("/leads", "/stats"):  # команды владельца — данные из базы
                reply, is_lead = (db.leads() if text == "/leads" else db.stats()), False
            else:
                reply, is_lead = answer(text)
                db.save(chat, who, text, reply, is_lead)
            try:
                api(token, "sendMessage", chat_id=chat, text=reply, disable_web_page_preview="true")
                if is_lead and owner and str(chat) != owner:
                    api(token, "sendMessage", chat_id=owner, text=f"📥 Заявка з бота від @{who} (id {chat}):\n{text}")
            except Exception as e:
                print("Не вдалося відповісти:", e)


if __name__ == "__main__":
    main()
