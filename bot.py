import os
import re
import random
import logging
import time
from vk_api import VkApi
from vk_api.longpoll import VkLongPoll, VkEventType

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

VK_TOKEN = os.environ.get('VK_TOKEN')
if not VK_TOKEN:
    logging.error('Переменная окружения VK_TOKEN не установлена!')
    exit(1)

vk_session = VkApi(token=VK_TOKEN)
vk = vk_session.get_api()
longpoll = VkLongPoll(vk_session)

def roll_dice(sides: int, modifier: int = 0) -> tuple:
    result = random.randint(1, sides)
    total = result + modifier
    return result, total

def roll_advantage(modifier: int = 0) -> dict:
    """Бросает 2d20, возвращает оба значения, выбранное (макс) и итог с модификатором."""
    roll1 = random.randint(1, 20)
    roll2 = random.randint(1, 20)
    chosen = max(roll1, roll2)
    total = chosen + modifier
    return {
        'roll1': roll1,
        'roll2': roll2,
        'chosen': chosen,
        'total': total,
        'modifier': modifier
    }

def roll_disadvantage(modifier: int = 0) -> dict:
    """Бросает 2d20, возвращает оба значения, выбранное (мин) и итог с модификатором."""
    roll1 = random.randint(1, 20)
    roll2 = random.randint(1, 20)
    chosen = min(roll1, roll2)
    total = chosen + modifier
    return {
        'roll1': roll1,
        'roll2': roll2,
        'chosen': chosen,
        'total': total,
        'modifier': modifier
    }

def parse_command(text: str):
    """Разбирает команду. Возвращает (тип_команды, параметры)."""
    text = text.strip().lower()
    
    # Обычные кубы /d4, /d20+2, /к, /к+1
    match = re.match(r'^/([dк])(\d*)([+-]\d+)?$', text)
    if match:
        cube_type, sides_str, mod_str = match.groups()
        if sides_str:
            sides = int(sides_str)
        else:
            sides = 20  # по умолчанию для /к
        if sides > 100:
            sides = 100
        modifier = int(mod_str) if mod_str else 0
        return ('dice', {'sides': sides, 'modifier': modifier})
    
    # Помеха /кпом, /кпом+2
    match = re.match(r'^/кпом([+-]\d+)?$', text)
    if match:
        mod_str = match.group(1)
        modifier = int(mod_str) if mod_str else 0
        return ('disadvantage', {'modifier': modifier})
    
    # Преимущество /кпре, /кпре+2
    match = re.match(r'^/кпре([+-]\d+)?$', text)
    if match:
        mod_str = match.group(1)
        modifier = int(mod_str) if mod_str else 0
        return ('advantage', {'modifier': modifier})
    
    return None

def attack_roll() -> str:
    roll = random.randint(1, 20)
    if roll == 1:
        return f"🎲 Результат атаки: {roll} — Промах!"
    elif roll == 20:
        return f"🎲 Результат атаки: {roll} — Критическое попадание!"
    else:
        return f"🎲 Результат атаки: {roll} — Попадание!"

def defense_roll() -> str:
    roll = random.randint(1, 20)
    if roll == 1:
        return f"🛡️ Результат защиты: {roll} — Провал!"
    elif roll == 20:
        return f"🛡️ Результат защиты: {roll} — Критический успех!"
    else:
        return f"🛡️ Результат защиты: {roll} — Успех!"

def double_roll() -> str:
    roll = random.randint(1, 6)
    if roll == 6:
        return f"💥 Куб удвоения: {roll} — ×2"
    else:
        return f"💥 Куб удвоения: {roll} — пусто"

def help_message() -> str:
    return (
        "Список команд:\n"
        "/d4, /d6, /d8, /d10, /d12, /d20, /d100 — бросить куб\n"
        "/d4+2, /d20-1 — бросить с модификатором\n"
        "/к — бросить d20 (сокращение)\n"
        "/кпом — бросить с помехой (2d20, берётся меньшее)\n"
        "/кпре — бросить с преимуществом (2d20, берётся большее)\n"
        "/кпом+2, /кпре-1 — с модификатором\n"
        "/attack — бросок атаки (промах/попадание/крит)\n"
        "/defense — бросок защиты (провал/успех/крит)\n"
        "/double — куб удвоения (пусто/×2)\n"
        "/помощь — показать эту справку"
    )

def handle_message(text: str, user_id: int):
    text = text.strip().lower()
    
    if text == '/attack':
        answer = attack_roll()
        vk.messages.send(user_id=user_id, message=answer, random_id=0)
        return
    
    if text == '/defense':
        answer = defense_roll()
        vk.messages.send(user_id=user_id, message=answer, random_id=0)
        return
    
    if text == '/double':
        answer = double_roll()
        vk.messages.send(user_id=user_id, message=answer, random_id=0)
        return
    
    if text in ('/помощь', '/help'):
        answer = help_message()
        vk.messages.send(user_id=user_id, message=answer, random_id=0)
        return
    
    parsed = parse_command(text)
    if not parsed:
        return
    
    cmd_type, params = parsed
    
    if cmd_type == 'dice':
        sides = params['sides']
        modifier = params['modifier']
        roll_result, total = roll_dice(sides, modifier)
        if modifier == 0:
            answer = f"🎲 Бросок d{sides}: {roll_result}"
        else:
            sign = '+' if modifier > 0 else ''
            answer = f"🎲 Бросок d{sides}{sign}{modifier}: {roll_result} {sign}{modifier} = {total}"
        vk.messages.send(user_id=user_id, message=answer, random_id=0)
    
    elif cmd_type == 'advantage':
        modifier = params['modifier']
        data = roll_advantage(modifier)
        sign = '+' if modifier > 0 else ''
        if modifier == 0:
            answer = f"🎲 Преимущество: кубы {data['roll1']} и {data['roll2']} → выбрано {data['chosen']}"
        else:
            answer = f"🎲 Преимущество: кубы {data['roll1']} и {data['roll2']} → выбрано {data['chosen']} {sign}{modifier} = {data['total']}"
        vk.messages.send(user_id=user_id, message=answer, random_id=0)
    
    elif cmd_type == 'disadvantage':
        modifier = params['modifier']
        data = roll_disadvantage(modifier)
        sign = '+' if modifier > 0 else ''
        if modifier == 0:
            answer = f"🎲 Помеха: кубы {data['roll1']} и {data['roll2']} → выбрано {data['chosen']}"
        else:
            answer = f"🎲 Помеха: кубы {data['roll1']} и {data['roll2']} → выбрано {data['chosen']} {sign}{modifier} = {data['total']}"
        vk.messages.send(user_id=user_id, message=answer, random_id=0)

def main():
    logging.info("Бот запущен и слушает сообщения...")
    while True:
        try:
            for event in longpoll.listen():
                if event.type == VkEventType.MESSAGE_NEW and event.to_me:
                    handle_message(event.text.strip(), event.user_id)
        except Exception as e:
            logging.error(f"Ошибка в longpoll: {e}")
            time.sleep(5)

if __name__ == '__main__':
    main()
