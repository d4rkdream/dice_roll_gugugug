def execute_command(cmd: str, peer_id: int, user_id: int):
    """Выполняет одну команду и возвращает ответ (или None)."""
    parsed = parse_single_command(cmd)
    if not parsed:
        return None
    
    cmd_type, params = parsed
    
    # Команды, для которых НЕ нужно добавлять имя перед ответом
    no_prefix_commands = ('setname', 'listnames', 'top', 'kickleft')
    
    # Получаем отображаемое имя, если нужно
    display_name = None
    if cmd_type not in no_prefix_commands:
        display_name = get_display_name(user_id, peer_id)
    
    # ---- существующие обработчики команд ----
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
        lines = [f"{name} (id{uid})" for uid, name in names]
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
    
    if cmd_type == 'kickleft':
        if peer_id <= 2000000000:
            return "❌ Эта команда работает только в беседах."
        try:
            members = vk.messages.getConversationMembers(peer_id=peer_id, fields='')
            current_ids = [abs(member['member_id']) for member in members['items']]
            deleted = remove_users_not_in_peer(peer_id, current_ids)
            return f"🧹 Удалено записей о вышедших пользователях: {deleted}."
        except Exception as e:
            logging.error(f"Ошибка при получении участников беседы {peer_id}: {e}")
            return "❌ Не удалось получить список участников. Убедитесь, что бот является администратором беседы."
    
    # ---- Далее идут команды бросков (к ним добавляем имя) ----
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
            return help_message()  # помощь без имени
        else:
            return None
        return f"{display_name}, {answer}"
    
    return None
