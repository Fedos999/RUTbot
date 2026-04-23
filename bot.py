import logging
import os
import sqlite3
from typing import Dict, Any
import psycopg

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)
from telegram.request import HTTPXRequest


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


LANGUAGES = {
    "ru": "Русский",
    "en": "English",
    "es": "Español",
    "zh": "中文",
    "fr": "Français",
    "mn": "Монгол",
}


MAIN_MENU_KEYS = ("schedule", "events", "offices", "channels", "support")
DB_PATH = os.getenv("BOT_STATS_DB_PATH", "bot_stats.sqlite3")
DATABASE_URL = (os.getenv("DATABASE_URL") or "").strip()


def init_stats_db() -> None:
    if DATABASE_URL:
        with psycopg.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS users (
                        user_id BIGINT PRIMARY KEY,
                        first_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        last_seen TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
            conn.commit()
        logger.info("Stats storage: PostgreSQL")
        return

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL
            )
            """
        )
        conn.commit()
    logger.info("Stats storage: SQLite (%s)", DB_PATH)


def track_user(update: Update) -> None:
    user = update.effective_user
    if not user:
        return

    if DATABASE_URL:
        with psycopg.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO users(user_id, first_seen, last_seen)
                    VALUES (%s, NOW(), NOW())
                    ON CONFLICT (user_id)
                    DO UPDATE SET last_seen = EXCLUDED.last_seen
                    """,
                    (user.id,),
                )
            conn.commit()
        return

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO users(user_id, first_seen, last_seen)
            VALUES (?, datetime('now'), datetime('now'))
            """,
            (user.id,),
        )
        conn.execute(
            "UPDATE users SET last_seen = datetime('now') WHERE user_id = ?",
            (user.id,),
        )
        conn.commit()


def get_admin_ids() -> set[int]:
    raw = os.getenv("ADMIN_USER_IDS") or os.getenv("ADMIN_USER_ID") or ""
    admin_ids: set[int] = set()
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            admin_ids.add(int(item))
        except ValueError:
            logger.warning("Invalid admin id in env: %s", item)
    return admin_ids


def get_stats() -> dict[str, int]:
    if DATABASE_URL:
        with psycopg.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM users")
                total = cur.fetchone()[0]
                cur.execute(
                    "SELECT COUNT(*) FROM users WHERE last_seen >= NOW() - INTERVAL '1 day'"
                )
                active_24h = cur.fetchone()[0]
                cur.execute(
                    "SELECT COUNT(*) FROM users WHERE last_seen >= NOW() - INTERVAL '7 day'"
                )
                active_7d = cur.fetchone()[0]
        return {"total": total, "active_24h": active_24h, "active_7d": active_7d}

    with sqlite3.connect(DB_PATH) as conn:
        total = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        active_24h = conn.execute(
            "SELECT COUNT(*) FROM users WHERE last_seen >= datetime('now', '-1 day')"
        ).fetchone()[0]
        active_7d = conn.execute(
            "SELECT COUNT(*) FROM users WHERE last_seen >= datetime('now', '-7 day')"
        ).fetchone()[0]
    return {"total": total, "active_24h": active_24h, "active_7d": active_7d}


def get_texts(lang: str) -> Dict[str, str]:
    if lang == "en":
        return {
            "start_title": "Welcome to the RUT (MIIT) assistant 👋",
            "start_body": (
                "Here you can quickly find key information about studies and campus life at "
                "the Russian University of Transport."
            ),
            "choose_language": "Please choose a language:",
            "main_title": "Main menu",
            "main_body": "Select the section you are interested in.",
            "schedule": "Class timetable",
            "events": "Events and activities",
            "offices": "Important offices",
            "channels": "Useful channels",
            "support": "Technical support",
            "back": "⬅️ Back",
            "back_to_main": "Back to main menu",
            "back_to_languages": "Back to language selection",
            "schedule_text": (
                "📚 *Class timetable*\n\n"
                "At the Russian University of Transport, a modular timetable system is used.\n"
                "Class schedule may differ on odd and even weeks.\n\n"
                "• The academic year starts with an *odd (first) week* on *1 September*.\n"
                "• The *even (second) week* starts on *7 September*.\n\n"
                "You can always find the up‑to‑date timetable:\n"
                "• on the information boards near your dean's office;\n"
                "• on the official website in the timetable section: https://rut-miit.ru/timetable\n\n"
                "*Class hours:*\n"
                "1st period — 08:30–09:50\n"
                "2nd period — 10:05–11:25\n"
                "3rd period — 11:40–13:00\n"
                "4th period — 13:45–15:05\n"
                "5th period — 15:20–16:40\n"
                "6th period — 16:55–18:15\n"
                "7th period — 18:30–19:50\n"
                "8th period — 20:00–21:20"
            ),
            "events_text": (
                "🎉 *Events at RUT (MIIT)*\n\n"
                "RUT (MIIT) regularly hosts educational, cultural and sports events: "
                "lectures, master classes, festivals, student clubs and much more.\n\n"
                "The most up‑to‑date announcements, registration links and photo reports are "
                "published in the official Telegram channel:\n"
                "• RUT (MIIT) — https://t.me/rut\\_live\n\n"
                "Subscribe to stay tuned to campus life!"
            ),
            "offices_text": (
                "🏛 *Important offices and services*\n\n"
                "• International Cooperation Office — room 1414\n"
                "• Visa Office — room 1302\n"
                "• Academic Office for International Students — room 1301\n"
                "• RUT (MIIT) Multifunctional Center — room 1224\n"
                "• Scientific and Technical Library:\n"
                "  – Main collection and reading room — room 1230\n"
                "• Military Registration Office — room 10103\n"
                "• Ceremonial Hall — room 1201\n"
                "• RUT (MIIT) Museum — room 1149"
            ),
            "channels_text": (
                "🔗 *Useful channels and communities*\n\n"
                "• RUT (MIIT) — official news and announcements:\n"
                "  https://t.me/rut\\_live\n\n"
                "• Global RUT — support and communication for international students:\n"
                "  https://t.me/global\\_rut\n\n"
                "• First Faculty channel — student life and events:\n"
                "  https://t.me/perviy\\_fakultetskiy\n\n"
                "• RUT (MIIT) Student Council community in VK:\n"
                "  https://vk.com/studsovetrut"
            ),
            "support_text": (
                "💬 *Technical support*\n\n"
                "If you have questions about using the bot or suggestions for improvement, "
                "you can contact the administrators in Telegram:\n\n"
                "• https://t.me/fedyan999\n"
                "• https://t.me/oltakmi\n"
                "• https://t.me/zx4et1x"
            ),
        }

    if lang == "es":
        return {
            "start_title": "Bienvenido al asistente de RUT (MIIT) 👋",
            "start_body": (
                "Aquí puedes encontrar rápidamente la información más importante "
                "sobre los estudios y la vida universitaria en la Universidad Rusa de Transporte."
            ),
            "choose_language": "Elige el idioma:",
            "main_title": "Menú principal",
            "main_body": "Selecciona la sección que te interesa.",
            "schedule": "Horario de clases",
            "events": "Eventos y actividades",
            "offices": "Oficinas importantes",
            "channels": "Canales útiles",
            "support": "Soporte técnico",
            "back": "⬅️ Volver",
            "back_to_main": "Volver al menú principal",
            "back_to_languages": "Volver a elegir idioma",
            "schedule_text": (
                "📚 *Horario de clases*\n\n"
                "En la Universidad Rusa de Transporte se utiliza un sistema modular de horario.\n"
                "El horario puede ser diferente en las semanas impares y pares.\n\n"
                "• El 1 de septiembre comienza la *primera semana (impar)*.\n"
                "• El 7 de septiembre comienza la *segunda semana (par).* \n\n"
                "Puedes consultar el horario actual:\n"
                "• en los tableros de información cerca de tu decanato;\n"
                "• en el sitio web oficial, en la sección de horario: https://rut-miit.ru/timetable\n\n"
                "*Horas de clase:*\n"
                "1ª clase — 08:30–09:50\n"
                "2ª clase — 10:05–11:25\n"
                "3ª clase — 11:40–13:00\n"
                "4ª clase — 13:45–15:05\n"
                "5ª clase — 15:20–16:40\n"
                "6ª clase — 16:55–18:15\n"
                "7ª clase — 18:30–19:50\n"
                "8ª clase — 20:00–21:20"
            ),
            "events_text": (
                "🎉 *Eventos en RUT (MIIT)*\n\n"
                "En RUT (MIIT) se organizan regularmente eventos educativos, culturales y deportivos: "
                "conferencias, talleres, festivales, clubes estudiantiles y mucho más.\n\n"
                "Los anuncios más recientes, enlaces de registro y reportajes fotográficos se publican en el "
                "canal oficial de Telegram:\n"
                "• RUT (MIIT) — https://t.me/rut\\_live\n\n"
                "¡Suscríbete para no perderte nada importante!"
            ),
            "offices_text": (
                "🏛 *Oficinas y servicios importantes*\n\n"
                "• Dirección de Cooperación Internacional — aula 1414\n"
                "• Oficina de Visados — aula 1302\n"
                "• Departamento Académico para Estudiantes Extranjeros — aula 1301\n"
                "• Centro Multifunccional de RUT (MIIT) — aula 1224\n"
                "• Biblioteca Científico‑Técnica:\n"
                "  – Biblioteca central y sala de lectura — aula 1230\n"
                "• Oficina de Registro Militar — aula 10103\n"
                "• Salón de actos — aula 1201\n"
                "• Museo de RUT (MIIT) — aula 1149"
            ),
            "channels_text": (
                "🔗 *Canales y comunidades útiles*\n\n"
                "• RUT (MIIT) — noticias y anuncios oficiales:\n"
                "  https://t.me/rut\\_live\n\n"
                "• Global RUT — apoyo y comunicación para estudiantes internacionales:\n"
                "  https://t.me/global\\_rut\n\n"
                "• Primer canal de facultad — vida estudiantil y eventos:\n"
                "  https://t.me/perviy\\_fakultetskiy\n\n"
                "• Consejo Estudiantil de RUT (MIIT) en VK:\n"
                "  https://vk.com/studsovetrut"
            ),
            "support_text": (
                "💬 *Soporte técnico*\n\n"
                "Si tienes preguntas sobre el uso del bot o sugerencias, puedes ponerte en contacto "
                "con los administradores en Telegram:\n\n"
                "• https://t.me/fedyan999\n"
                "• https://t.me/oltakmi\n"
                "• https://t.me/zx4et1x"
            ),
        }

    if lang == "zh":
        return {
            "start_title": "欢迎使用 RUT (MIIT) 助手 👋",
            "start_body": (
                "在这里，您可以快速了解俄罗斯交通大学的学习安排和校园生活。"
            ),
            "choose_language": "请选择语言：",
            "main_title": "主菜单",
            "main_body": "请选择您感兴趣的版块。",
            "schedule": "课程时间表",
            "events": "活动与事件",
            "offices": "重要办公室",
            "channels": "实用频道",
            "support": "技术支持",
            "back": "⬅️ 返回",
            "back_to_main": "返回主菜单",
            "back_to_languages": "返回语言选择",
            "schedule_text": (
                "📚 *课程时间表*\n\n"
                "俄罗斯交通大学采用模块化课程表制度。\n"
                "单双周的课程安排可能不同。\n\n"
                "• 9 月 1 日开始为*第一周（单周）*。\n"
                "• 9 月 7 日开始为*第二周（双周）。*\n\n"
                "您可以在以下位置查看最新课程表：\n"
                "• 院系办公室附近的信息公告栏；\n"
                "• 学校官网课表页面：https://rut-miit.ru/timetable\n\n"
                "*上课时间：*\n"
                "第 1 节 — 08:30–09:50\n"
                "第 2 节 — 10:05–11:25\n"
                "第 3 节 — 11:40–13:00\n"
                "第 4 节 — 13:45–15:05\n"
                "第 5 节 — 15:20–16:40\n"
                "第 6 节 — 16:55–18:15\n"
                "第 7 节 — 18:30–19:50\n"
                "第 8 节 — 20:00–21:20"
            ),
            "events_text": (
                "🎉 *RUT (MIIT) 活动*\n\n"
                "学校定期举办讲座、文化节、体育赛事和学生社团等各类活动。\n\n"
                "最新的活动预告、报名链接和照片报道会发布在官方 Telegram 频道：\n"
                "• RUT (MIIT) — https://t.me/rut\\_live\n\n"
                "欢迎订阅，及时了解校园生活！"
            ),
            "offices_text": (
                "🏛 *重要办公室和服务*\n\n"
                "• 国际合作处 — 1414 教室\n"
                "• 签证办公室 — 1302 教室\n"
                "• 外国留学生教务处 — 1301 教室\n"
                "• RUT (MIIT) 多功能服务中心 — 1224 教室\n"
                "• 科技图书馆：\n"
                "  – 基本书库与阅览室 — 1230 教室\n"
                "• 兵役登记办公室 — 10103 教室\n"
                "• 礼堂 — 1201 教室\n"
                "• RUT (MIIT) 博物馆 — 1149 教室"
            ),
            "channels_text": (
                "🔗 *实用频道与社区*\n\n"
                "• RUT (MIIT) — 官方新闻与公告：\n"
                "  https://t.me/rut\\_live\n\n"
                "• Global RUT — 为国际学生提供支持与交流：\n"
                "  https://t.me/global\\_rut\n\n"
                "• 第一学院频道 — 学生活动与校园生活：\n"
                "  https://t.me/perviy\\_fakultetskiy\n\n"
                "• RUT (MIIT) 学生会 VK 社区：\n"
                "  https://vk.com/studsovetrut"
            ),
            "support_text": (
                "💬 *技术支持*\n\n"
                "如果您在使用机器人时遇到问题，或有改进建议，\n"
                "可以通过 Telegram 联系管理员：\n\n"
                "• https://t.me/fedyan999\n"
                "• https://t.me/oltakmi\n"
                "• https://t.me/zx4et1x"
            ),
        }

    if lang == "fr":
        return {
            "start_title": "Bienvenue dans l'assistant RUT (MIIT) 👋",
            "start_body": (
                "Ici, vous pouvez trouver rapidement les informations importantes sur les études "
                "et la vie étudiante à l'Université russe des transports."
            ),
            "choose_language": "Veuillez choisir une langue :",
            "main_title": "Menu principal",
            "main_body": "Sélectionnez la section qui vous intéresse.",
            "schedule": "Emploi du temps",
            "events": "Événements et activités",
            "offices": "Bureaux importants",
            "channels": "Canaux utiles",
            "support": "Support technique",
            "back": "⬅️ Retour",
            "back_to_main": "Retour au menu principal",
            "back_to_languages": "Changer de langue",
            "schedule_text": (
                "📚 *Emploi du temps*\n\n"
                "À l'Université russe des transports, un système modulaire est utilisé.\n"
                "L'emploi du temps peut différer entre les semaines impaires et paires.\n\n"
                "• L'année académique commence par la *semaine impaire (première)* le *1er septembre*.\n"
                "• La *semaine paire (deuxième)* commence le *7 septembre*.\n\n"
                "Vous pouvez toujours consulter l'emploi du temps actualisé :\n"
                "• sur les panneaux d'information près de votre décanat ;\n"
                "• sur le site officiel, section emploi du temps : https://rut-miit.ru/timetable\n\n"
                "*Horaires des cours :*\n"
                "1er cours — 08:30–09:50\n"
                "2e cours — 10:05–11:25\n"
                "3e cours — 11:40–13:00\n"
                "4e cours — 13:45–15:05\n"
                "5e cours — 15:20–16:40\n"
                "6e cours — 16:55–18:15\n"
                "7e cours — 18:30–19:50\n"
                "8e cours — 20:00–21:20"
            ),
            "events_text": (
                "🎉 *Événements à RUT (MIIT)*\n\n"
                "L'université organise régulièrement des événements éducatifs, culturels et sportifs : "
                "conférences, ateliers, festivals étudiants et plus encore.\n\n"
                "Les annonces les plus récentes, liens d'inscription et photos sont publiés "
                "sur le canal Telegram officiel :\n"
                "• RUT (MIIT) — https://t.me/rut\\_live\n\n"
                "Abonnez-vous pour suivre la vie du campus !"
            ),
            "offices_text": (
                "🏛 *Bureaux et services importants*\n\n"
                "• Direction de la coopération internationale — salle 1414\n"
                "• Bureau des visas — salle 1302\n"
                "• Service académique pour les étudiants étrangers — salle 1301\n"
                "• Centre multifonctionnel RUT (MIIT) — salle 1224\n"
                "• Bibliothèque scientifique et technique :\n"
                "  – Bibliothèque principale et salle de lecture — salle 1230\n"
                "• Bureau d'enregistrement militaire — salle 10103\n"
                "• Salle des cérémonies — salle 1201\n"
                "• Musée RUT (MIIT) — salle 1149"
            ),
            "channels_text": (
                "🔗 *Canaux et communautés utiles*\n\n"
                "• RUT (MIIT) — actualités et annonces officielles :\n"
                "  https://t.me/rut\\_live\n\n"
                "• Global RUT — soutien et communication pour étudiants internationaux :\n"
                "  https://t.me/global\\_rut\n\n"
                "• Canal de la première faculté — vie étudiante et activités :\n"
                "  https://t.me/perviy\\_fakultetskiy\n\n"
                "• Communauté du Conseil étudiant RUT (MIIT) sur VK :\n"
                "  https://vk.com/studsovetrut"
            ),
            "support_text": (
                "💬 *Support technique*\n\n"
                "Si vous avez des questions sur l'utilisation du bot ou des idées d'amélioration, "
                "contactez les administrateurs sur Telegram :\n\n"
                "• https://t.me/fedyan999\n"
                "• https://t.me/oltakmi\n"
                "• https://t.me/zx4et1x"
            ),
        }

    if lang == "mn":
        return {
            "start_title": "RUT (MIIT) туслах ботод тавтай морил 👋",
            "start_body": (
                "Эндээс та Оросын Тээврийн Их Сургуулийн хичээл болон оюутны амьдралын "
                "чухал мэдээллийг хурдан олох боломжтой."
            ),
            "choose_language": "Хэлээ сонгоно уу:",
            "main_title": "Үндсэн цэс",
            "main_body": "Сонирхож буй хэсгээ сонгоно уу.",
            "schedule": "Хичээлийн хуваарь",
            "events": "Арга хэмжээ",
            "offices": "Чухал өрөөнүүд",
            "channels": "Хэрэгтэй сувгууд",
            "support": "Техникийн дэмжлэг",
            "back": "⬅️ Буцах",
            "back_to_main": "Үндсэн цэс рүү буцах",
            "back_to_languages": "Хэл солих",
            "schedule_text": (
                "📚 *Хичээлийн хуваарь*\n\n"
                "Оросын Тээврийн Их Сургуульд модуль хуваарийн систем ашигладаг.\n"
                "Сондгой болон тэгш долоо хоногт хичээлийн хуваарь өөр байж болно.\n\n"
                "• *9-р сарын 1*-нд *сондгой (1-р) долоо хоног* эхэлнэ.\n"
                "• *9-р сарын 7*-нд *тэгш (2-р) долоо хоног* эхэлнэ.\n\n"
                "Шинэчилсэн хуваарийг дараах газраас харна уу:\n"
                "• деканы албаны ойролцоох мэдээллийн самбар;\n"
                "• сургуулийн албан ёсны сайт: https://rut-miit.ru/timetable\n\n"
                "*Хичээлийн цагууд:*\n"
                "1-р хичээл — 08:30–09:50\n"
                "2-р хичээл — 10:05–11:25\n"
                "3-р хичээл — 11:40–13:00\n"
                "4-р хичээл — 13:45–15:05\n"
                "5-р хичээл — 15:20–16:40\n"
                "6-р хичээл — 16:55–18:15\n"
                "7-р хичээл — 18:30–19:50\n"
                "8-р хичээл — 20:00–21:20"
            ),
            "events_text": (
                "🎉 *RUT (MIIT)-ийн арга хэмжээнүүд*\n\n"
                "Сургуульд лекц, мастер класс, наадам, спортын тэмцээн зэрэг "
                "боловсролын болон соёлын олон арга хэмжээ тогтмол зохион байгуулагддаг.\n\n"
                "Хамгийн сүүлийн зар, бүртгэлийн холбоос, тайлангууд албан ёсны Telegram сувагт нийтлэгддэг:\n"
                "• RUT (MIIT) — https://t.me/rut\\_live\n\n"
                "Сургуулийн амьдралаас хоцрохгүй байхын тулд бүртгүүлээрэй!"
            ),
            "offices_text": (
                "🏛 *Чухал өрөөнүүд ба үйлчилгээ*\n\n"
                "• Олон улсын хамтын ажиллагааны газар — 1414 өрөө\n"
                "• Визийн алба — 1302 өрөө\n"
                "• Гадаад оюутны сургалтын алба — 1301 өрөө\n"
                "• RUT (MIIT) олон үйлдэлт төв — 1224 өрөө\n"
                "• Шинжлэх ухаан, техникийн номын сан:\n"
                "  – Үндсэн номын сан ба уншлагын танхим — 1230 өрөө\n"
                "• Цэргийн бүртгэлийн товчоо — 10103 өрөө\n"
                "• Ёслолын танхим — 1201 өрөө\n"
                "• RUT (MIIT) музей — 1149 өрөө"
            ),
            "channels_text": (
                "🔗 *Хэрэгтэй сувгууд ба нийгэмлэгүүд*\n\n"
                "• RUT (MIIT) — албан ёсны мэдээ, зарууд:\n"
                "  https://t.me/rut\\_live\n\n"
                "• Global RUT — гадаад оюутнуудад зориулсан дэмжлэг ба харилцаа:\n"
                "  https://t.me/global\\_rut\n\n"
                "• Нэгдүгээр факультетийн суваг — оюутны амьдрал ба арга хэмжээ:\n"
                "  https://t.me/perviy\\_fakultetskiy\n\n"
                "• RUT (MIIT) Оюутны зөвлөлийн VK нийгэмлэг:\n"
                "  https://vk.com/studsovetrut"
            ),
            "support_text": (
                "💬 *Техникийн дэмжлэг*\n\n"
                "Бот ашиглахтай холбоотой асуулт эсвэл санал байвал Telegram-аар админтай холбогдоно уу:\n\n"
                "• https://t.me/fedyan999\n"
                "• https://t.me/oltakmi\n"
                "• https://t.me/zx4et1x"
            ),
        }

    # Russian is default
    return {
        "start_title": "Добро пожаловать в помощник РУТ (МИИТ) 👋",
        "start_body": (
            "Здесь вы можете быстро найти важную информацию об учёбе "
            "и студенческой жизни в Российском университете транспорта."
        ),
        "choose_language": "Выберите язык общения:",
        "main_title": "Главное меню",
        "main_body": "Выберите интересующий вас раздел.",
        "schedule": "Расписание занятий",
        "events": "Расписание мероприятий",
        "offices": "Важные кабинеты",
        "channels": "Полезные сообщества",
        "support": "Техническая поддержка",
        "back": "⬅️ Вернуться назад",
        "back_to_main": "Вернуться в главное меню",
        "back_to_languages": "Сменить язык",
        "schedule_text": (
            "📚 *Расписание занятий*\n\n"
            "В Российском университете транспорта действует модульная система занятий.\n"
            "По чётным и нечётным неделям расписание пар может отличаться.\n\n"
            "• *1 сентября* начинается *нечётная (первая) неделя*.\n"
            "• *7 сентября* — *чётная (вторая) неделя*.\n\n"
            "Актуальное расписание вы всегда можете посмотреть:\n"
            "• на информационных стендах возле деканата;\n"
            "• на официальном сайте университета в разделе расписания: https://rut-miit.ru/timetable\n\n"
            "*Время занятий:*\n"
            "1 пара — 08:30–09:50\n"
            "2 пара — 10:05–11:25\n"
            "3 пара — 11:40–13:00\n"
            "4 пара — 13:45–15:05\n"
            "5 пара — 15:20–16:40\n"
            "6 пара — 16:55–18:15\n"
            "7 пара — 18:30–19:50\n"
            "8 пара — 20:00–21:20"
        ),
        "events_text": (
            "🎉 *Мероприятия РУТ (МИИТ)*\n\n"
            "В университете регулярно проходят лекции, мастер‑классы, творческие вечера, "
            "спортмероприятия и большие студенческие фестивали.\n\n"
            "Самые свежие анонсы, формы регистрации и фотоотчёты публикуются в официальном "
            "Telegram‑канале РУТ (МИИТ):\n"
            "• РУТ (МИИТ) — https://t.me/rut\\_live\n\n"
            "Подписывайтесь, чтобы не пропускать важные события университетской жизни!"
        ),
        "offices_text": (
            "🏛 *Важные кабинеты и службы*\n\n"
            "• Управление международного сотрудничества — ауд. 1414\n"
            "• Визовый отдел — ауд. 1302\n"
            "• Учебный отдел по работе с иностранными гражданами — ауд. 1301\n"
            "• Многофункциональный центр РУТ (МИИТ) — ауд. 1224\n"
            "• Научно‑техническая библиотека РУТ (МИИТ):\n"
            "  — фундаментальная библиотека и читальный зал — ауд. 1230\n"
            "• Военно‑учётное бюро — ауд. 10103\n"
            "• Зал торжеств — ауд. 1201\n"
            "• Музей РУТ (МИИТ) — ауд. 1149"
        ),
        "channels_text": (
            "🔗 *Полезные Telegram‑каналы и сообщества*\n\n"
            "• РУТ (МИИТ) — официальные новости и объявления университета:\n"
            "  https://t.me/rut\\_live\n\n"
            "• Глобальный RUT — поддержка и общение для иностранных студентов:\n"
            "  https://t.me/global\\_rut\n\n"
            "• Первый факультетский — жизнь факультета и студенческие активности:\n"
            "  https://t.me/perviy\\_fakultetskiy\n\n"
            "• Студенческий совет РУТ (МИИТ) во VK — инициативы и проекты студсовета:\n"
            "  https://vk.com/studsovetrut"
        ),
        "support_text": (
            "💬 *Техническая поддержка бота*\n\n"
            "Если у вас есть вопросы по работе бота или идеи, как сделать его лучше, "
            "напишите администраторам в Telegram:\n\n"
            "• https://t.me/fedyan999\n"
            "• https://t.me/oltakmi\n"
            "• https://t.me/zx4et1x"
        ),
    }


def make_language_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(name, callback_data=f"lang:{code}")
            for code, name in (("ru", LANGUAGES["ru"]), ("en", LANGUAGES["en"]))
        ],
        [
            InlineKeyboardButton(name, callback_data=f"lang:{code}")
            for code, name in (("es", LANGUAGES["es"]), ("zh", LANGUAGES["zh"]))
        ],
        [
            InlineKeyboardButton(name, callback_data=f"lang:{code}")
            for code, name in (("fr", LANGUAGES["fr"]), ("mn", LANGUAGES["mn"]))
        ],
    ]
    return InlineKeyboardMarkup(buttons)


def make_main_menu_keyboard(lang: str) -> InlineKeyboardMarkup:
    t = get_texts(lang)
    buttons = [
        [
            InlineKeyboardButton(t["schedule"], callback_data=f"menu:schedule"),
            InlineKeyboardButton(t["events"], callback_data=f"menu:events"),
        ],
        [
            InlineKeyboardButton(t["offices"], callback_data=f"menu:offices"),
            InlineKeyboardButton(t["channels"], callback_data=f"menu:channels"),
        ],
        [
            InlineKeyboardButton(t["support"], callback_data=f"menu:support"),
        ],
        [
            InlineKeyboardButton(t["back_to_languages"], callback_data="nav:languages"),
        ],
    ]
    return InlineKeyboardMarkup(buttons)


def make_section_keyboard(lang: str) -> InlineKeyboardMarkup:
    t = get_texts(lang)
    buttons = [
        [
            InlineKeyboardButton(t["back_to_main"], callback_data="nav:main"),
        ],
        [
            InlineKeyboardButton(t["back_to_languages"], callback_data="nav:languages"),
        ],
    ]
    return InlineKeyboardMarkup(buttons)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    track_user(update)
    user = update.effective_user
    context.user_data.setdefault("lang", "ru")
    lang = context.user_data["lang"]
    t = get_texts(lang)

    text = (
        f"*{t['start_title']}*\n\n"
        f"{t['start_body']}\n\n"
        f"{t['choose_language']}"
    )

    if update.message:
        await update.message.reply_text(
            text,
            reply_markup=make_language_keyboard(),
            parse_mode="Markdown",
        )
    elif update.callback_query:
        await update.callback_query.edit_message_text(
            text,
            reply_markup=make_language_keyboard(),
            parse_mode="Markdown",
        )

    logger.info("User %s started the bot", user.id if user else "unknown")


async def handle_language_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    _, lang = query.data.split(":", 1)
    if lang not in LANGUAGES:
        lang = "ru"

    context.user_data["lang"] = lang
    t = get_texts(lang)

    welcome_text = (
        "Трудности с расписанием или поиском нужной информации? "
        "Скучная студенческая жизнь?🤔\n\n"
        "Привет! 👋\n"
        "Добро пожаловать в чат-бот для иностранных студентов 🎓\n\n"
        "Здесь ты найдёшь расписание занятий, мероприятия, важные ссылки и всё, что нужно для удобной учёбы.\n\n"
        "Удачи и классного старта 🚀"
    )

    text = f"{welcome_text}\n\n*{t['main_title']}*\n\n{t['main_body']}"
    await query.edit_message_text(
        text,
        reply_markup=make_main_menu_keyboard(lang),
        parse_mode="Markdown",
    )


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    lang = context.user_data.get("lang", "ru")
    t = get_texts(lang)
    text = f"*{t['main_title']}*\n\n{t['main_body']}"

    await query.edit_message_text(
        text,
        reply_markup=make_main_menu_keyboard(lang),
        parse_mode="Markdown",
    )


async def show_section(update: Update, context: ContextTypes.DEFAULT_TYPE, section: str) -> None:
    query = update.callback_query
    await query.answer()

    lang = context.user_data.get("lang", "ru")
    t = get_texts(lang)

    key = f"{section}_text"
    text = t.get(key)
    if not text:
        text = "Section is under construction."

    await query.edit_message_text(
        text,
        reply_markup=make_section_keyboard(lang),
        parse_mode="Markdown",
        disable_web_page_preview=False,
    )


async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    track_user(update)
    query = update.callback_query
    data = query.data or ""

    if data.startswith("lang:"):
        await handle_language_choice(update, context)
        return

    if data == "nav:languages":
        await start(update, context)
        return

    if data == "nav:main":
        await show_main_menu(update, context)
        return

    if data.startswith("menu:"):
        _, section = data.split(":", 1)
        if section in MAIN_MENU_KEYS:
            await show_section(update, context, section)
            return

    await query.answer()


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not update.message or not user:
        return

    admin_ids = get_admin_ids()
    if user.id not in admin_ids:
        await update.message.reply_text("У вас нет доступа к этой команде.")
        return

    stats = get_stats()
    await update.message.reply_text(
        "Статистика бота:\n"
        f"- Всего уникальных пользователей: {stats['total']}\n"
        f"- Активных за 24 часа: {stats['active_24h']}\n"
        f"- Активных за 7 дней: {stats['active_7d']}"
    )


def build_application(token: str | None = None) -> Any:
    init_stats_db()

    if token is None:
        token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN is not set. "
            "Set it as an environment variable or pass explicitly to build_application()."
        )

    # Defaults are short (e.g. 5s connect); slow or unstable routes need more time.
    # If api.telegram.org is blocked, use proxy vars and/or custom Telegram Bot API URL.
    req_kw: dict[str, Any] = {
        "connect_timeout": 30.0,
        "read_timeout": 30.0,
        "write_timeout": 30.0,
        "pool_timeout": 15.0,
    }
    proxy = (
        os.getenv("TELEGRAM_PROXY")
        or os.getenv("HTTPS_PROXY")
        or os.getenv("https_proxy")
        or os.getenv("HTTP_PROXY")
        or os.getenv("http_proxy")
    )
    if proxy:
        req_kw["proxy"] = proxy
    request = HTTPXRequest(**req_kw)

    builder = ApplicationBuilder().token(token).request(request)

    base_url = os.getenv("TELEGRAM_BASE_URL")
    base_file_url = os.getenv("TELEGRAM_BASE_FILE_URL")
    if base_url:
        builder = builder.base_url(base_url)
    if base_file_url:
        builder = builder.base_file_url(base_file_url)

    app = builder.build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CallbackQueryHandler(callback_router))

    return app


def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    app = build_application(token)
    logger.info("Bot started. Press Ctrl+C to stop.")
    app.run_polling()


if __name__ == "__main__":
    main()

