"""Проверка логики бота без Telegram: python bot/test_bot.py"""
from bot import answer, search

assert any("Focus" in p["name"] for p in search("Ford Focus 3 2015")), "Focus не найден"
assert search("Шкода Октавия 2012"), "кириллица не сработала"
for p in search("Hyundai Accent 2012"):
    assert "Accent" in p["name"]
assert answer("/start")[0].startswith("Привіт")
assert answer("мій номер 067 123 45 67")[1] is True
assert answer("qwertyzzz xyz")[1] is True
for q in ("Привет творожок", "Нужна магнитола", "Сколько стоит доставка?", "Спасибо"):
    assert answer(q)[1] is False, q  # болтовня и вопросы — не заявки
assert answer("Привет творожок")[0].startswith("Вітаю")
assert "Новою Поштою" in answer("Как доставка?")[0]
assert "Гарантія" in answer("какая гарантия")[0]
for q in ("хочу заказать", "хочу купить", "у меня стоит", "мне надо", "подскажите", "а есть у вас",
          "а есть в наличии"):
    a, lead = answer(q)
    assert not lead and "Не знайшов" not in a, q
assert "оформимо" in answer("хочу заказать")[0]
focus = answer("Ford Focus 3 2015")[0]
assert "розділ" in focus and "?sort=price" in focus  # раздел, от дешёвых к дорогим
assert "від 7 990" not in focus  # раньше «від» считалось по 3 товарам и было завышено
print("ok")
for q in ("Ford Focus 3 2015", "Шкода Октавия 2012", "Toyota Camry 40", "хочу купить", "а есть в наличии",
          "Привет творожок", "Нужна магнитола", "А установка сложная? и оплата частями есть?"):
    print("\n>>>", q)
    print(answer(q)[0])
