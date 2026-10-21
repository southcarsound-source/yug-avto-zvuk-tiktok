"""Проверка логики бота без Telegram: python bot/test_bot.py"""
from bot import answer, search

assert any("Focus" in p["name"] for p in search("Ford Focus 3 2015")), "Focus не найден"
assert search("Шкода Октавия 2012"), "кириллица не сработала"
for p in search("Hyundai Accent 2012"):
    assert "Accent" in p["name"]
assert answer("/start")[0].startswith("Привіт")
assert answer("мій номер 067 123 45 67")[1] is True
assert answer("qwertyzzz xyz")[1] is True
print("ok")
for q in ("Ford Focus 3 2015", "Шкода Октавия 2012", "Toyota Camry 40"):
    print("\n>>>", q)
    print(answer(q)[0])
