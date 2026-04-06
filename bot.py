import os
import re
import random
import logging
import time
import sqlite3
from datetime import datetime, timedelta
from vk_api import VkApi
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

VK_TOKEN = os.environ.get('VK_TOKEN')
if not VK_TOKEN:
    logging.error('Переменная окружения VK_TOKEN не установлена!')
    exit(1)

GROUP_ID = 237271897

vk_session = VkApi(token=VK_TOKEN)
vk = vk_session.get_api()
longpoll = VkBotLongPoll(vk_session, group_id=GROUP_ID)

# ---------- Работа с базой данных SQLite ----------
DB_FILE = "bot_stats.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER,
                    peer_id INTEGER,
                    name TEXT,
                    PRIMARY KEY (user_id, peer_id)
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS daily_stats (
                    user_id INTEGER,
                    peer_id INTEGER,
                    date TEXT,
                    messages INTEGER DEFAULT 0,
                    rolls INTEGER DEFAULT 0,
                    PRIMARY KEY (user_id, peer_id, date)
                )''')
    conn.commit()
    conn.close()

def get_today_str():
    return datetime.now().strftime("%Y-%m-%d")

def update_stats(user_id, peer_id, inc_messages=0, inc_rolls=0):
    if inc_messages == 0 and inc_rolls == 0:
        return
    today = get_today_str()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''INSERT INTO daily_stats (user_id, peer_id, date, messages, rolls)
                 VALUES (?, ?, ?, ?, ?)
                 ON CONFLICT(user_id, peer_id, date) DO UPDATE SET
                 messages = messages + ?,
                 rolls = rolls + ?''',
              (user_id, peer_id, today, inc_messages, inc_rolls, inc_messages, inc_rolls))
    conn.commit()
    conn.close()

def set_user_name(user_id, peer_id, name):
    if len(name) > 32:
        name = name[:32]
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''INSERT INTO users (user_id, peer_id, name)
                 VALUES (?, ?, ?)
                 ON CONFLICT(user_id, peer_id) DO UPDATE SET name = excluded.name''',
              (user_id, peer_id, name))
    conn.commit()
    conn.close()

def get_user_name(user_id, peer_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT name FROM users WHERE user_id = ? AND peer_id = ?', (user_id, peer_id))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def get_all_names_in_peer(peer_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT user_id, name FROM users WHERE peer_id = ?', (peer_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_top_users(peer_id, days=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    if days is not None:
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        date_condition = "AND date >= ?"
        params = (peer_id, start_date)
    else:
        date_condition = ""
        params = (peer_id,)
    
    query_messages = f'''
        SELECT user_id, SUM(messages) as total
        FROM daily_stats
        WHERE peer_id = ? {date_condition}
        GROUP BY user_id
        ORDER BY total DESC
        LIMIT 10
    '''
    if days:
        c.execute(query_messages, (peer_id, start_date))
    else:
        c.execute(query_messages, (peer_id,))
    top_messages = c.fetchall()
    
    query_rolls = f'''
        SELECT user_id, SUM(rolls) as total
        FROM daily_stats
        WHERE peer_id = ? {date_condition}
        GROUP BY user_id
        ORDER BY total DESC
        LIMIT 10
    '''
    if days:
        c.execute(query_rolls, (peer_id, start_date))
    else:
        c.execute(query_rolls, (peer_id,))
    top_rolls = c.fetchall()
    
    conn.close()
    
    # --- ИСПРАВЛЕНИЕ: получение имён для топа ---
    user_names = {}
    for user_id, _ in top_messages + top_rolls:
        # Сначала проверяем имя из БД
        name = get_user_name(user_id, peer_id)
        if name:
            user_names[user_id] = name
        else:
            # Если имени нет, получаем screen_name из профиля ВК
            screen_name = get_user_screen_name(user_id)
            user_names[user_id] = screen_name if screen_name else f"id{user_id}"
    
    top_messages_named = [(uid, cnt, user_names.get(uid, f"id{uid}")) for uid, cnt in top_messages]
    top_rolls_named = [(uid, cnt, user_names.get(uid, f"id{uid}")) for uid, cnt in top_rolls]
    
    return top_messages_named, top_rolls_named

# --- НОВАЯ ФУНКЦИЯ ДЛЯ ПОЛУЧЕНИЯ SCREEN_NAME С КЭШИРОВАНИЕМ ---
_screen_name_cache = {}
def get_user_screen_name(user_id: int) -> str:
    """Получает screen_name пользователя через VK API с кэшированием."""
    if user_id in _screen_name_cache:
        return _screen_name_cache[user_id]
    try:
        # Запрашиваем информацию о пользователе
        user_info = vk.users.get(user_ids=user_id, fields='screen_name')[0]
        screen_name = user_info.get('screen_name')
        if screen_name:
            _screen_name_cache[user_id] = screen_name
            return screen_name
        else:
            # Если screen_name нет, используем имя и фамилию
            first_name = user_info.get('first_name', '')
            last_name = user_info.get('last_name', '')
            full_name = f"{first_name} {last_name}".strip()
            if full_name:
                _screen_name_cache[user_id] = full_name
                return full_name
            return None
    except Exception as e:
        logging.error(f"Ошибка при получении screen_name для {user_id}: {e}")
        return None

# --- ОБНОВЛЕННАЯ ФУНКЦИЯ ОТОБРАЖЕНИЯ ИМЕНИ ---
def get_display_name(user_id: int, peer_id: int) -> str:
    """Возвращает имя для отображения: из БД бота или screen_name из ВК."""
    # 1. Приоритет у имени, установленного через бота
    custom_name = get_user_name(user_id, peer_id)
    if custom_name:
        return custom_name
    
    # 2. Если имени в боте нет, получаем screen_name из профиля ВК
    screen_name = get_user_screen_name(user_id)
    if screen_name:
        return screen_name
    
    # 3. Если ничего не найдено, показываем ID
    return f"id{user_id}"

# ---------- ОСТАЛЬНЫЕ ФУНКЦИИ (БЕЗ ИЗМЕНЕНИЙ) ----------
def roll_dice(sides: int, modifier: int = 0) -> tuple:
    result = random.randint(1, sides)
    total = result + modifier
    return result, total

def roll_multiple(count: int, sides: int, modifier: int = 0) -> dict:
    results = [random.randint(1, sides) for _ in range(count)]
    total_sum = sum(results)
    final = total_sum + modifier
    return {
        'results': results,
        'sum': total_sum,
        'final': final,
        'modifier': modifier
    }

def roll_advantage(modifier: int = 0) -> dict:
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

def reroll_cube() -> str:
    roll = random.randint(1, 4)
    if roll <= 2:
        return f"🎲 Куб рерола: {roll} — пусто"
    else:
        return f"🎲 Куб рерола: {roll} — успех"

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
        "/d4+2, /d20-1 — с модификатором\n"
        "/2d20, /3d100, /2к20, /4к6+3 — бросить несколько кубов (до 100 штук, грани до 100)\n"
        "/кпом — помеха (2d20, меньшее)\n"
        "/кпре — преимущество (2d20, большее)\n"
        "/кпом+2, /кпре-1 — с модификатором\n"
        "/attack — атака (промах/попадание/крит)\n"
        "/defense — защита (провал/успех/крит)\n"
        "/double — куб удвоения (пусто/×2)\n"
        "/reroll — куб рерола (пусто/пусто/успех/успех)\n"
        "/имя <текст> — установить своё имя в этой беседе (макс. 32 символа)\n"
        "/имена — показать список всех имён в этой беседе\n"
        "/топ [дни] — топ‑10 по сообщениям и броскам (за всё время или за последние N дней, N≤365)\n"
        "/помощь — эта справка\n"
        "Все команды начинаются с символа /"
    )

# ---------- Разбор команд (только со слешем) ----------
def parse_single_command(text: str):
    text = text.strip().lower()
    if not text.startswith('/'):
        return None
    
    match_name = re.match(r'^/имя\s+(.+)$', text)
    if match_name:
        name_text = match_name.group(1).strip()
        return ('setname', {'name': name_text})
    
    if text == '/имена':
        return ('listnames', None)
    
    match_top = re.match(r'^/топ\s*(\d+)?$', text)
    if match_top:
        days_str = match_top.group(1)
        days = int(days_str) if days_str else None
        if days is not None and (days <= 0 or days > 365):
            days = None
        return ('top', {'days': days})
    
    match_multiple = re.match(r'^/(\d+)([dк])(\d+)([+-]\d+)?$', text)
    if match_multiple:
        count_str, cube_type, sides_str, mod_str = match_multiple.groups()
        count = int(count_str)
        sides = int(sides_str)
        if count > 100:
            count = 100
        if sides > 100:
            sides = 100
        modifier = int(mod_str) if mod_str else 0
        return ('multiple', {'count': count, 'sides': sides, 'modifier': modifier})
    
    match_single = re.match(r'^/([dк])(\d+)([+-]\d+)?$', text)
    if match_single:
        cube_type, sides_str, mod_str = match_single.groups()
        sides = int(sides_str)
        if sides > 100:
            sides = 100
        modifier = int(mod_str) if mod_str else 0
        return ('dice', {'sides': sides, 'modifier': modifier})
    
    match = re.match(r'^/кпом([+-]\d+)?$', text)
    if match:
        mod_str = match.group(1)
        modifier = int(mod_str) if mod_str else 0
        return ('disadvantage', {'modifier': modifier})
    
    match = re.match(r'^/кпре([+-]\d+)?$', text)
    if match:
        mod_str = match.group(1)
        modifier = int(mod_str) if mod_str else 0
        return ('advantage', {'modifier': modifier})
    
    if text in ('/attack', '/defense', '/double', '/reroll', '/помощь', '/help'):
        return ('simple', text)
    
    return None

def split_commands(full_text: str):
    parts = full_text.strip().split()
    commands = []
    for part in parts:
        if part.startswith('/'):
            commands.append(part)
        else:
            if commands and commands[-1].startswith('/имя'):
                commands[-1] += ' ' + part
    return commands

def execute_command(cmd: str, peer_id: int, user_id: int):
    parsed = parse_single_command(cmd)
    if not parsed:
        return None
    
    cmd_type, params = parsed
    
    no_prefix_commands = ('setname', 'listnames', 'top')
    
    if cmd_type not in no_prefix_commands:
        display_name = get_display_name(user_id, peer_id)
    else:
        display_name = None
    
    if cmd_type == 'setname':
        if peer_id <= 2000000000:
            return "❌ Эта команда работает только в беседах."
        name = params['name']
        if len(name) > 32:
            name = name[:32]
        set_user_name(user_id, peer_id, name)
        return f"✅ Ваше имя в этой беседе установлено как «{name}»."
    
    if cmd_type == 'listnames':
        if peer_id <= 2000000000:
            return "❌ Эта команда работает только в беседах."
        names = get_all_names_in_peer(peer_id)
        if not names:
            return "📋 В этой беседе ещё никто не установил имя. Используйте `/имя ВашеИмя`."
        # --- ИСПРАВЛЕНИЕ: получение имён для списка ---
        lines = []
        for uid, name in names:
            lines.append(f"{name} (id{uid})")
        return "📋 Список имён в беседе:\n" + "\n".join(lines)
    
    if cmd_type == 'top':
        if peer_id <= 2000000000:
            return "❌ Эта команда работает только в беседах."
        days = params['days']
        top_msg, top_roll = get_top_users(peer_id, days)
        period = f"за последние {days} дней" if days else "за всё время"
        result = f"📊 Статистика {period}:\n\n"
        result += "✉️ Топ по сообщениям:\n"
        if top_msg:
            for i, (uid, cnt, name) in enumerate(top_msg, 1):
                result += f"{i}. {name}: {cnt} сообщ.\n"
        else:
            result += "Нет данных.\n"
        result += "\n🎲 Топ по броскам:\n"
        if top_roll:
            for i, (uid, cnt, name) in enumerate(top_roll, 1):
                result += f"{i}. {name}: {cnt} бросков\n"
        else:
            result += "Нет данных.\n"
        return result
    
    if cmd_type == 'dice':
        sides = params['sides']
        modifier = params['modifier']
        roll_result, total = roll_dice(sides, modifier)
        if modifier == 0:
            answer = f"🎲 Бросок d{sides}: {roll_result}"
        else:
            sign = '+' if modifier > 0 else ''
            answer = f"🎲 Бросок d{sides}{sign}{modifier}: {roll_result} {sign}{modifier} = {total}"
        return f"{display_name}, {answer}"
    
    elif cmd_type == 'multiple':
        count = params['count']
        sides = params['sides']
        modifier = params['modifier']
        data = roll_multiple(count, sides, modifier)
        results_str = ', '.join(map(str, data['results']))
        sign = '+' if modifier > 0 else ''
        if modifier == 0:
            answer = f"🎲 Бросок {count}d{sides}: [{results_str}] сумма = {data['sum']}"
        else:
            answer = f"🎲 Бросок {count}d{sides}{sign}{modifier}: [{results_str}] сумма {data['sum']} {sign}{modifier} = {data['final']}"
        return f"{display_name}, {answer}"
    
    elif cmd_type == 'advantage':
        modifier = params['modifier']
        data = roll_advantage(modifier)
        sign = '+' if modifier > 0 else ''
        if modifier == 0:
            answer = f"🎲 Преимущество: кубы {data['roll1']} и {data['roll2']} → выбрано {data['chosen']}"
        else:
            answer = f"🎲 Преимущество: кубы {data['roll1']} и {data['roll2']} → выбрано {data['chosen']} {sign}{modifier} = {data['total']}"
        return f"{display_name}, {answer}"
    
    elif cmd_type == 'disadvantage':
        modifier = params['modifier']
        data = roll_disadvantage(modifier)
        sign = '+' if modifier > 0 else ''
        if modifier == 0:
            answer = f"🎲 Помеха: кубы {data['roll1']} и {data['roll2']} → выбрано {data['chosen']}"
        else:
            answer = f"🎲 Помеха: кубы {data['roll1']} и {data['roll2']} → выбрано {data['chosen']} {sign}{modifier} = {data['total']}"
        return f"{display_name}, {answer}"
    
    elif cmd_type == 'simple':
        if params == '/attack':
            answer = attack_roll()
        elif params == '/defense':
            answer = defense_roll()
        elif params == '/double':
            answer = double_roll()
        elif params == '/reroll':
            answer = reroll_cube()
        elif params in ('/помощь', '/help'):
            return help_message()
        else:
            return None
        return f"{display_name}, {answer}"
    
    return None

def handle_message(event):
    msg = event.object.message
    text = msg.get('text', '')
    if not text:
        return
    peer_id = msg['peer_id']
    from_id = msg.get('from_id')
    if from_id == -GROUP_ID:
        return

    if peer_id > 2000000000:
        update_stats(from_id, peer_id, inc_messages=1)

    commands = split_commands(text)
    if not commands:
        return

    for cmd in commands:
        parsed = parse_single_command(cmd)
        is_roll = parsed and parsed[0] in ('dice', 'multiple', 'advantage', 'disadvantage', 'simple') and parsed[1] not in ('/помощь', '/help')
        
        answer = execute_command(cmd, peer_id, from_id)
        if answer:
            if is_roll and peer_id > 2000000000:
                update_stats(from_id, peer_id, inc_rolls=1)
            vk.messages.send(peer_id=peer_id, message=answer, random_id=0)
            time.sleep(0.3)

def main():
    init_db()
    logging.info(f"Бот сообщества {GROUP_ID} запущен. Поддерживаются команды только с символом / в начале.")
    while True:
        try:
            for event in longpoll.listen():
                if event.type == VkBotEventType.MESSAGE_NEW:
                    handle_message(event)
        except Exception as e:
            logging.error(f"Ошибка в longpoll: {e}")
            time.sleep(5)

if __name__ == '__main__':
    main()
