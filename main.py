import asyncio
import logging
import json
import re
import aiohttp
import random
import uuid
from datetime import datetime, timedelta
from io import BytesIO

from vkbottle.bot import Bot, Message
from vkbottle import Keyboard, KeyboardButtonColor, Text, Callback, GroupEventType
from vkbottle.dispatch.rules.base import PayloadRule
from openai import AsyncOpenAI

logging.basicConfig(level=logging.INFO)

# ─── ТОКЕНЫ ───────────────────────────────────────────────
VK_TOKEN   = "vk1.a.xON8IXyV_VoIsNxRxQimg3i051HVP2mWHxV_p6v_LCwPlV4SgR65-yOfjyCu7JEkiwbhJZOXtq69xD21wzI9jzgUCe1R6RGE6V5PWX46p32T7Q_vTqxGCVgIbfJ_CVjlgLLMzI9-Zv21Wc4FDTUz9LKpojL0OMYKkZxuTqGPhF3IynS7VGBekiWzQ84wjh4mjMxef0uMzieXMgi2CrYjgA"   # ← вставь сюда новый токен
MISTRAL_KEY = "rGmIVqCbaDh29Y7t3Yd7ipsbL0ZlQbny"
# ──────────────────────────────────────────────────────────

client = AsyncOpenAI(
    api_key=MISTRAL_KEY,
    base_url="https://api.mistral.ai/v1",
)

bot = Bot(token=VK_TOKEN)

user_history           = {}
user_teacher_selection = {}
user_group_selection   = {}
user_states            = {}
user_saved_schedule    = {}

USERS_FILE = "known_users_vk.json"

# ─── known users ──────────────────────────────────────────
def load_known_users() -> set:
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return set(int(uid) for uid in json.load(f))
    except FileNotFoundError:
        return set()
    except Exception as e:
        logging.error(f"Ошибка загрузки: {e}")
        return set()

def save_known_users():
    try:
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(list(known_users), f)
    except Exception as e:
        logging.error(f"Ошибка сохранения: {e}")

known_users = load_known_users()

# ─── ДАННЫЕ ───────────────────────────────────────────────
INSTITUTE_INFO = """
🏛 Кубанский институт профессионального образования (КИПО)
📌 Основан в 1997 году | 18 специальностей | 5000+ студентов
📝 Приём без экзаменов, по среднему баллу аттестата
📞 8 800 500 40 68 доб. 1180
📍 г. Краснодар, ул. Садовая, 218
"""

NEWBIE_INFO = """
🎓 Добро пожаловать в КИПО!

✨ Поздравляем с поступлением!
📋 Посети вводные занятия и ознакомься с расписанием
🪪 Получи студенческий билет в деканате

━━━━━━━━━━━━━━━━━━━━━
🏢 Корпуса КИПО

📍 Садовая, 218 — Главный корпус (администрация, лекции)
📍 Колхозная, 5/1 — Учебный корпус
📍 Тополиная аллея, 2/1 — Спортзал / Физра
📍 Новокузнечная, 67 — Учебный корпус
📍 Красноармейская, 51 — Учебный корпус / Доп. образование
📍 Леваневского, 187/1 — Учебный корпус

━━━━━━━━━━━━━━━━━━━━━
🚃 Как добраться на трамвае

🔹 Садовая, 218 — №1,2,5,8,15 → «Крупской»/«Садовая»
🔹 Колхозная, 5/1 — №3,20,21,22 → «МОПР, Клиническая»
🔹 Тополиная аллея, 2/1 — №5,8,15,21,22 → «Почта» (5-6 мин пешком)
🔹 Новокузнечная, 67 — №3,5,8,15,20,21,22 → «Промышленная»
🔹 Красноармейская, 51 — №3,5,8,15,21,22 → «Коммунаров»
🔹 Леваневского, 187/1 — №1,2,3,5,8,15,20,21,22 → «Промышленная»

💡 Открой 2ГИС или Яндекс.Карты — там актуальные маршруты.
"""

MOTIVATIONS = [
    "Каждый день — это новый шанс стать лучше, чем вчера.",
    "Не бойся идти медленно, бойся стоять на месте.",
    "Твои усилия сегодня — твой успех завтра.",
    "Ты уже дальше, чем те, кто даже не начал.",
    "Учёба — это инвестиция в себя, которую никто не отберёт.",
    "Каждая пятёрка начинается с решения попробовать.",
    "Не сравнивай себя с другими. Сравнивай себя с собой вчерашним.",
    "Ошибки — это не провал, это часть обучения.",
    "Образование — это не заполнение ведра, а зажжение огня.",
    "Ты способен на большее, чем думаешь.",
    "Каждый эксперт когда-то был новичком.",
    "Дорогу осилит идущий.",
    "Дисциплина важнее мотивации. Мотивация приходит и уходит.",
    "Один умный вопрос лучше тысячи молчаливых непониманий.",
    "Знание — сила. Применение знаний — власть.",
    "Успех — это сумма маленьких усилий, повторяемых день за днём.",
    "Лучший момент начать учиться был вчера. Второй лучший — сейчас.",
    "Не сдавайся — лучшее всегда впереди.",
]

# ─── JSON ──────────────────────────────────────────────────
try:
    with open('groups.json', 'r', encoding='utf-8') as f:
        GROUP_SCHEDULES = json.load(f)
    logging.info(f"Загружено {len(GROUP_SCHEDULES)} групп")
except Exception as e:
    logging.error(f"groups.json: {e}")
    GROUP_SCHEDULES = {}

try:
    with open('teachers.json', 'r', encoding='utf-8') as f:
        TEACHERS = json.load(f)
    logging.info(f"Загружено {len(TEACHERS)} преподавателей")
except Exception as e:
    logging.error(f"teachers.json: {e}")
    TEACHERS = {}

# ─── КЛАВИАТУРЫ ────────────────────────────────────────────
def main_keyboard():
    kb = Keyboard(one_time=False, inline=False)
    kb.add(Text("📚 Расписание"), color=KeyboardButtonColor.PRIMARY)
    kb.add(Text("💡 Мотивация"), color=KeyboardButtonColor.POSITIVE)
    kb.row()
    kb.add(Text("🆕 Для новичков"), color=KeyboardButtonColor.SECONDARY)
    kb.add(Text("💾 Запомнить расписание"), color=KeyboardButtonColor.SECONDARY)
    kb.row()
    kb.add(Text("📥 Скачать расписание"), color=KeyboardButtonColor.SECONDARY)
    kb.add(Text("💰 Оплата"), color=KeyboardButtonColor.SECONDARY)
    kb.row()
    kb.add(Text("🏛 Об институте"), color=KeyboardButtonColor.SECONDARY)
    kb.add(Text("📞 Контакты"), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()

def back_keyboard():
    kb = Keyboard(one_time=True, inline=False)
    kb.add(Text("Назад"), color=KeyboardButtonColor.NEGATIVE)
    return kb.get_json()

def revoke_keyboard():
    kb = Keyboard(one_time=True, inline=False)
    kb.add(Text("Отозвать запоминание"), color=KeyboardButtonColor.NEGATIVE)
    kb.row()
    kb.add(Text("Назад"), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()

def motivation_keyboard():
    kb = Keyboard(inline=True)
    kb.add(Callback("✨ Новая мотивация", {"cmd": "new_motivation"}), color=KeyboardButtonColor.POSITIVE)
    kb.add(Callback("◀️ Назад", {"cmd": "back_main"}), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()

# ─── РАСПИСАНИЕ ────────────────────────────────────────────
def get_today() -> str:
    return datetime.now().strftime("%Y-%m-%d")

async def fetch_schedule_raw(url: str) -> dict:
    try:
        match = re.search(r'publications/([a-f0-9-]+)#/(groups|teachers)/(\d+)/lessons', url)
        if not match:
            return {}
        pub_uuid    = match.group(1)
        entity_type = match.group(2)
        entity_id   = match.group(3)
        if entity_type == "groups":
            api_url = "https://schedule.mstimetables.ru/api/publications/group/lessons"
            payload = {"groupId": entity_id, "date": get_today(), "publicationId": pub_uuid}
        else:
            api_url = "https://schedule.mstimetables.ru/api/publications/teacher/lessons"
            payload = {"teacherId": entity_id, "date": get_today(), "publicationId": pub_uuid}
        headers = {
            "User-Agent": "Mozilla/5.0", "Accept": "application/json",
            "Content-Type": "application/json",
            "Origin": "https://schedule.mstimetables.ru",
            "Referer": f"https://schedule.mstimetables.ru/publications/{pub_uuid}",
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(api_url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200: return {}
                return await resp.json()
    except Exception as e:
        logging.error(f"Ошибка расписания: {e}")
        return {}

async def fetch_schedule_text(url: str) -> str:
    data = await fetch_schedule_raw(url)
    if not data:
        return "Не удалось загрузить расписание."
    return format_schedule(data)

def format_schedule(data: dict) -> str:
    days_ru   = {1:"Понедельник",2:"Вторник",3:"Среда",4:"Четверг",5:"Пятница",6:"Суббота",7:"Воскресенье"}
    day_emoji = {1:"🔵",2:"🟢",3:"🟡",4:"🟠",5:"🔴",6:"🟣",7:"⚫"}
    try:
        lessons = data.get("lessons", [])
        if not lessons:
            return "На эту неделю занятий нет."
        by_day = {}
        for lesson in lessons:
            day = lesson.get("weekday")
            by_day.setdefault(day, []).append(lesson)
        result = []
        sd = data.get("startDate","")[:10]; ed = data.get("endDate","")[:10]
        if sd and ed:
            result += [f"Неделя: {sd} — {ed}", "─"*21]
        for day_num in sorted(by_day):
            entries = sorted(by_day[day_num], key=lambda x: x.get("startTime",""))
            result += ["", f"{day_emoji.get(day_num,'')} {days_ru.get(day_num,'').upper()}", "─"*21]
            for l in entries:
                result.append(f"{l.get('lesson','')} пара  {l.get('startTime','')}–{l.get('endTime','')}")
                result.append(f"📖 {l.get('subject',{}).get('name','?')}")
                t = ", ".join(x.get("fio","") for x in l.get("teachers",[]))
                if t: result.append(f"👤 {t}")
                cab = l.get("cabinet",{}).get("name","")
                if cab: result.append(f"🏫 {cab}")
                result.append("")
            result.append("═"*21)
        return "\n".join(result)
    except Exception as e:
        logging.error(f"Форматирование: {e}")
        return "Не удалось отформатировать расписание."

# ─── ICS ───────────────────────────────────────────────────
def fold_ics(line: str) -> str:
    if len(line.encode('utf-8')) <= 75: return line
    res = []
    while len(line.encode('utf-8')) > 75:
        cut = 75
        while len(line[:cut].encode('utf-8')) > 75: cut -= 1
        res.append(line[:cut]); line = ' ' + line[cut:]
    res.append(line)
    return '\r\n'.join(res)

def esc(t): return t.replace('\\','\\\\').replace(';','\\;').replace(',','\\,').replace('\n','\\n')

async def generate_ics(name, url, entity_type) -> bytes | None:
    data = await fetch_schedule_raw(url)
    if not data or not data.get("lessons"): return None
    sd = datetime.strptime(data.get("startDate", datetime.now().strftime("%Y-%m-%d"))[:10], "%Y-%m-%d")
    ed = datetime.strptime(data.get("endDate",   (datetime.now()+timedelta(days=30)).strftime("%Y-%m-%d"))[:10], "%Y-%m-%d")
    now_utc = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR","VERSION:2.0","PRODID:-//КИПО//RU","CALSCALE:GREGORIAN","METHOD:PUBLISH",
             f"X-WR-CALNAME:{esc('Расписание '+name)}","X-WR-TIMEZONE:Europe/Moscow",
             "BEGIN:VTIMEZONE","TZID:Europe/Moscow","BEGIN:STANDARD",
             "TZOFFSETFROM:+0300","TZOFFSETTO:+0300","TZNAME:MSK","DTSTART:19700101T000000",
             "END:STANDARD","END:VTIMEZONE"]
    seen = set()
    for lesson in data["lessons"]:
        wd = lesson.get("weekday")
        if not wd: continue
        try: sh,sm = map(int,lesson.get("startTime","0:0").split(":")); eh,em = map(int,lesson.get("endTime","0:0").split(":"))
        except: continue
        cur = sd; ev = None
        while cur <= ed:
            if cur.weekday()+1 == wd: ev = cur; break
            cur += timedelta(days=1)
        if not ev: continue
        ds = ev.replace(hour=sh,minute=sm,second=0,microsecond=0)
        de = ev.replace(hour=eh,minute=em,second=0,microsecond=0)
        subj = lesson.get("subject",{}).get("name","Занятие")[:50]
        cab  = lesson.get("cabinet",{}).get("name","")
        tch  = ", ".join(t.get("fio","") for t in lesson.get("teachers",[]))[:80]
        key  = f"{ds}-{subj}-{cab}"
        if key in seen: continue
        seen.add(key)
        lines += ["BEGIN:VEVENT", f"UID:{uuid.uuid4()}@kipo.ru",
                  f"DTSTAMP:{now_utc}", f"CREATED:{now_utc}",
                  f"DTSTART;TZID=Europe/Moscow:{ds.strftime('%Y%m%dT%H%M%S')}",
                  f"DTEND;TZID=Europe/Moscow:{de.strftime('%Y%m%dT%H%M%S')}",
                  f"SUMMARY:{esc(subj+(' ('+cab+')' if cab else ''))}",
                  f"DESCRIPTION:{esc('Препод: '+tch)}",
                  "BEGIN:VALARM","ACTION:DISPLAY","DESCRIPTION:Напоминание","TRIGGER:-PT30M","END:VALARM",
                  "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return ("\r\n".join(fold_ics(l) for l in lines)+"\r\n").encode('utf-8')

# ─── ПОИСК ─────────────────────────────────────────────────
def search_group(query):
    matches = re.findall(r'(\d{2}-?[А-ЯA-ZЁё]{2,5}\d?(?:-\d{1,2})?(?:\s*ЗФО)?)', query, re.IGNORECASE)
    q = matches[0].upper().replace(" ","").replace("-","") if matches else re.sub(r'[^А-ЯA-Z0-9ЗФО]','',query.upper())
    return [(c,u) for c,u in GROUP_SCHEDULES.items() if q and (q in c.upper().replace(" ","").replace("-","") or c.upper().replace(" ","").replace("-","") == q)]

def search_teacher(query):
    words = [w for w in query.lower().replace("."," ").split() if len(w)>=3]
    found = []
    for name,url in TEACHERS.items():
        sur = name.lower().split()[0] if name.split() else ""
        if any(sur.startswith(w) for w in words): found.append((name,url))
    seen = {}
    for n,u in found:
        cl = n.replace("*","").strip()
        if cl not in seen: seen[cl] = (n,u)
    return list(seen.values())

# ══════════════════════════════════════════════════════════
#  ХЕНДЛЕРЫ
# ══════════════════════════════════════════════════════════

async def send_main(message: Message, text: str):
    await message.answer(text, keyboard=main_keyboard())

@bot.on.message(text="/start")
@bot.on.message(text="начать")
async def cmd_start(message: Message):
    uid = message.from_id
    user_history[uid] = []
    if uid not in known_users: known_users.add(uid); save_known_users()
    await send_main(message,
        "Привет! Я ассистент КИПО. 🎓\n\n"
        "Могу:\n"
        "• показывать расписание группы (пиши: расписание 24-ИСП1-9)\n"
        "• искать преподавателя по фамилии (пиши: Иванова)\n"
        "• отвечать на вопросы об институте\n\n"
        "Используй кнопки ниже 👇"
    )

@bot.on.message(text="📚 Расписание")
async def btn_schedule(message: Message):
    uid = message.from_id
    if uid not in user_saved_schedule:
        await message.answer("Сначала запомни расписание через '💾 Запомнить расписание'.", keyboard=main_keyboard())
        return
    s = user_saved_schedule[uid]
    typ = "группы" if s['type']=='group' else "преподавателя"
    await message.answer(f"Загружаю расписание {typ} {s['code']}...")
    await message.answer("Расписание:\n\n" + await fetch_schedule_text(s['url']), keyboard=main_keyboard())

@bot.on.message(text="💡 Мотивация")
async def btn_motivation(message: Message):
    uid = message.from_id
    if uid not in known_users: known_users.add(uid); save_known_users()
    await message.answer("Мотивация дня:\n\n" + random.choice(MOTIVATIONS), keyboard=motivation_keyboard())

@bot.on.message(text="🆕 Для новичков")
async def btn_newbie(message: Message):
    await send_main(message, NEWBIE_INFO)

@bot.on.message(text="🏛 Об институте")
async def btn_about(message: Message):
    await send_main(message, INSTITUTE_INFO)

@bot.on.message(text="📞 Контакты")
async def btn_contacts(message: Message):
    await send_main(message,
        "📞 Контакты КИПО:\n\n"
        "☎️ 8 800 500 40 68 (доб. 1180)\n"
        "📍 г. Краснодар, ул. Садовая, 218\n"
        "🌐 kipo.ru"
    )

@bot.on.message(text="💰 Оплата")
async def btn_payment(message: Message):
    await send_main(message,
        "💰 Оплата обучения:\n\n"
        "Уточняйте в деканате или по телефону:\n"
        "☎️ 8 800 500 40 68 (доб. 1180)"
    )

@bot.on.message(text="💾 Запомнить расписание")
async def btn_remember(message: Message):
    uid = message.from_id
    if uid not in known_users: known_users.add(uid); save_known_users()
    if uid in user_saved_schedule:
        s = user_saved_schedule[uid]
        typ = "группы" if s['type']=='group' else "преподавателя"
        await message.answer(f"Запомнено расписание {typ} {s['code']}\n\nВыбери действие:", keyboard=revoke_keyboard())
    else:
        await message.answer("Напиши номер группы или фамилию преподавателя.\nПример: 24-ИСП1-9 или Иванова", keyboard=back_keyboard())
        user_states[uid] = 'waiting_schedule'

@bot.on.message(text="📥 Скачать расписание")
async def btn_download(message: Message):
    uid = message.from_id
    if uid not in known_users: known_users.add(uid); save_known_users()
    await message.answer("Чьё расписание скачать в .ics?\n\nНапиши номер группы или фамилию:", keyboard=back_keyboard())
    user_states[uid] = 'waiting_download_schedule'

@bot.on.message(text="Отозвать запоминание")
async def btn_revoke(message: Message):
    uid = message.from_id
    user_saved_schedule.pop(uid, None)
    await send_main(message, "Запоминание отозвано! ✅")

@bot.on.message(text="Назад")
async def btn_back(message: Message):
    uid = message.from_id
    user_states.pop(uid, None)
    user_group_selection.pop(uid, None)
    user_teacher_selection.pop(uid, None)
    await send_main(message, "Главное меню:")

# ─── Callback (inline кнопки мотивации) ──────────────────
@bot.on.raw_event(GroupEventType.MESSAGE_EVENT, dataclass=dict)
async def on_callback(event: dict):
    payload = event.get("object", {}).get("payload", {})
    user_id = event.get("object", {}).get("user_id")
    peer_id = event.get("object", {}).get("peer_id")
    cmd     = payload.get("cmd")
    if cmd == "new_motivation":
        await bot.api.messages.send(
            peer_id=peer_id, random_id=0,
            message="Мотивация:\n\n" + random.choice(MOTIVATIONS),
            keyboard=motivation_keyboard()
        )
    elif cmd == "back_main":
        await bot.api.messages.send(
            peer_id=peer_id, random_id=0,
            message="Главное меню:", keyboard=main_keyboard()
        )

# ─── Главный обработчик всех сообщений ───────────────────
@bot.on.message()
async def handle_all(message: Message):
    uid       = message.from_id
    user_text = (message.text or "").strip()
    lower     = user_text.lower()

    if uid not in known_users: known_users.add(uid); save_known_users()
    history = user_history.get(uid, [])
    history.append({"role": "user", "content": user_text})

    # ── Состояние: скачать расписание ──
    if user_states.get(uid) == 'waiting_download_schedule':
        found, et = [], None
        if any(c.isdigit() for c in user_text):
            found = search_group(user_text); et = 'group'
        else:
            found = search_teacher(user_text); et = 'teacher'
        if not found:
            await message.answer("Не нашёл. Пример: 24-ИСП1-9 или Пясецкий", keyboard=back_keyboard())
            return
        if len(found) == 1:
            name, url = found[0]
            await message.answer(f"Генерирую .ics для {name}...")
            ics = await generate_ics(name, url, et)
            if ics:
                # Загружаем файл через VK docs API
                upload = await bot.api.docs.get_messages_upload_server(peer_id=message.peer_id, type="doc")
                async with aiohttp.ClientSession() as sess:
                    data = aiohttp.FormData()
                    data.add_field('file', ics, filename=f"Расписание_{name.replace(' ','_')}.ics", content_type='text/calendar')
                    async with sess.post(upload.upload_url, data=data) as r:
                        res = await r.json()
                saved = await bot.api.docs.save(file=res['file'], title=f"Расписание {name}")
                doc = saved.doc
                await bot.api.messages.send(
                    peer_id=message.peer_id, random_id=0,
                    message="📅 Добавь в Google Календарь или Apple Календарь",
                    attachment=f"doc{doc.owner_id}_{doc.id}",
                    keyboard=main_keyboard()
                )
            else:
                await message.answer("Не удалось сгенерировать.", keyboard=main_keyboard())
            user_states.pop(uid, None)
            return
        if et == 'group':
            user_group_selection[uid] = found
            lines = "\n".join(f"{i+1}. {c}" for i,(c,_) in enumerate(found[:8]))
            await message.answer(f"Нашёл несколько групп:\n\n{lines}\n\nНапиши номер:")
        else:
            user_teacher_selection[uid] = found
            lines = "\n".join(f"{i+1}. {n}" for i,(n,_) in enumerate(found[:12]))
            await message.answer(f"Нашёл несколько преподавателей:\n\n{lines}\n\nНапиши номер:")
        user_states[uid] = 'waiting_download_choice'
        return

    # ── Состояние: запомнить расписание ──
    if user_states.get(uid) == 'waiting_schedule':
        found, et = [], None
        if any(c.isdigit() for c in user_text):
            found = search_group(user_text); et = 'group'
        else:
            found = search_teacher(user_text); et = 'teacher'
        if not found:
            await send_main(message, "Не нашёл. Попробуй другой запрос.")
            user_states.pop(uid, None); return
        if len(found) == 1:
            code, url = found[0]
            user_saved_schedule[uid] = {'type':et,'code':code,'url':url}
            await send_main(message, f"Запомнил {'группу' if et=='group' else 'преподавателя'} {code}! ✅")
            user_states.pop(uid, None)
        else:
            if et == 'group':
                user_group_selection[uid] = found
                lines = "\n".join(f"{i+1}. {c}" for i,(c,_) in enumerate(found[:8]))
                await message.answer(f"Нашёл несколько групп:\n\n{lines}\n\nНапиши номер:")
            else:
                user_teacher_selection[uid] = found
                lines = "\n".join(f"{i+1}. {n}" for i,(n,_) in enumerate(found[:12]))
                await message.answer(f"Нашёл несколько преподавателей:\n\n{lines}\n\nНапиши номер:")
            user_states.pop(uid, None)
        return

    # ── Выбор из списка ──
    if uid in user_group_selection and user_text.strip().isdigit():
        idx = int(user_text.strip()) - 1
        sel = user_group_selection[uid]
        if 0 <= idx < len(sel):
            code, url = sel[idx]; del user_group_selection[uid]
            user_saved_schedule[uid] = {'type':'group','code':code,'url':url}
            await message.answer(f"Запомнил группу {code}! ✅")
            await message.answer("Загружаю расписание...")
            await send_main(message, "Расписание:\n\n" + await fetch_schedule_text(url))
        else:
            await message.answer("Неверный номер.")
        return

    if uid in user_teacher_selection and user_text.strip().isdigit():
        idx = int(user_text.strip()) - 1
        sel = user_teacher_selection[uid]
        if 0 <= idx < len(sel):
            name, url = sel[idx]; del user_teacher_selection[uid]
            user_saved_schedule[uid] = {'type':'teacher','code':name,'url':url}
            await message.answer(f"Запомнил {name}! ✅")
            await message.answer("Загружаю расписание...")
            await send_main(message, "Расписание:\n\n" + await fetch_schedule_text(url))
        else:
            await message.answer("Неверный номер.")
        return

    # ── Поиск расписания ──
    if any(kw in lower for kw in ["расписание","распис","расп","уроки","занятия","пары"]) and GROUP_SCHEDULES:
        found = search_group(user_text)
        if found:
            if len(found) == 1:
                code, url = found[0]
                await message.answer(f"Загружаю расписание {code}...")
                await send_main(message, "Расписание:\n\n" + await fetch_schedule_text(url))
            else:
                user_group_selection[uid] = found
                lines = "\n".join(f"{i+1}. {c}" for i,(c,_) in enumerate(found[:8]))
                await message.answer(f"Нашёл {len(found)} групп:\n\n{lines}\n\nНапиши номер:")
            return
        await message.answer("Группу не нашёл. Пример: расписание 24-ИСП1-9")
        return

    # ── Поиск преподавателя ──
    if TEACHERS and bool(re.match(r'^[а-яёА-ЯЁ][а-яёА-ЯЁ\s\.\-]{2,}$', lower.strip())) and len(lower.strip()) >= 4:
        found = search_teacher(user_text)
        if found:
            if len(found) == 1:
                name, url = found[0]
                await message.answer(f"Загружаю расписание {name}...")
                await send_main(message, "Расписание:\n\n" + await fetch_schedule_text(url))
            else:
                user_teacher_selection[uid] = found
                lines = "\n".join(f"{i+1}. {n}" for i,(n,_) in enumerate(found[:12]))
                await message.answer(f"Нашёл {len(found)} преподавателей:\n\n{lines}\n\nНапиши номер:")
            return

    # ── Дата/время ──
    if any(kw in lower for kw in ["сегодня","дата","время","число","день недели"]):
        import pytz
        now = datetime.now(pytz.timezone('Europe/Moscow'))
        days = {'Monday':'понедельник','Tuesday':'вторник','Wednesday':'среда',
                'Thursday':'четверг','Friday':'пятница','Saturday':'суббота','Sunday':'воскресенье'}
        await send_main(message, f"Сегодня {days[now.strftime('%A')]}, {now.strftime('%d.%m.%Y')}.\nВремя в Москве: {now.strftime('%H:%M')}")
        return

    # ── Mistral AI ──
    sys_prompt = (
        "Ты дружелюбный ассистент КИПО ВКонтакте. Отвечай на русском, кратко и по делу.\n"
        f"Инфо:\n{INSTITUTE_INFO}\n"
        "Про расписание — советуй написать номер группы (пример: расписание 24-ИСП1-9)\n"
        "Про преподавателя — советуй написать просто фамилию"
    )
    msgs = [{"role":"system","content":sys_prompt}] + history[-12:]
    try:
        await message.answer("Думаю...")
        resp = await client.chat.completions.create(model="mistral-small-latest", messages=msgs, temperature=0.7, max_tokens=800)
        reply = resp.choices[0].message.content.strip()
        history.append({"role":"assistant","content":reply})
        user_history[uid] = history
        await send_main(message, reply)
    except Exception as e:
        logging.error(f"Mistral: {e}")
        await send_main(message, "Проблема. Попробуй позже или звони: 8 800 500 40 68 доб. 1180")

# ══════════════════════════════════════════════════════════
if __name__ == "__main__":
    bot.run_forever()
