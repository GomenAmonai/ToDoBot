import logging
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, ParseMode
)
from telegram.ext import (
    Updater, CommandHandler, MessageHandler, Filters, CallbackContext,
    CallbackQueryHandler, ConversationHandler
)
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
import sqlite3
import pytz
import traceback

# Включаем логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logger = logging.getLogger(__name__)

# Определяем состояния для ConversationHandler
(
    CHOOSING, ADD_TASK_TOPIC, ADD_TASK_ATTACHMENTS, ADD_TASK_DONE,
    TYPING_TIME, CONFIRMING, SELECT_DAY, SELECT_TIME_OF_DAY,
    SET_SCHEDULE_HOUR, SAVE_SCHEDULE, RESET_SCHEDULE,
    QUICK_NOTE, QUICK_NOTE_CONFIRM, QUICK_NOTE_TIME,
    SETTINGS, SET_NOTIFICATION_TIME,
    SUBSCRIPTIONS, SUBSCRIPTION_CATEGORY, VIEW_SUBSCRIPTION,
    ADD_SUBSCRIPTION
) = range(20)

# Указываем ваш часовой пояс
TIMEZONE = pytz.timezone('Europe/Moscow')

# Подключаемся к базе данных
conn = sqlite3.connect('tasks.db', check_same_thread=False)
cursor = conn.cursor()

# Создаем таблицы, если они не существуют
cursor.execute('''
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    topic TEXT,
    description TEXT,
    attachments TEXT,
    time TEXT
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    day TEXT,
    time_of_day TEXT,
    hour INTEGER,
    task TEXT
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    category TEXT,
    content TEXT
)
''')

conn.commit()

# Создаем планировщик
scheduler = BackgroundScheduler(timezone=TIMEZONE)
scheduler.start()

# Укажите здесь ваш chat_id для получения уведомлений об ошибках (без кавычек)
ADMIN_CHAT_ID = 6698369098  # Замените на ваш реальный chat_id

# Время напоминания по умолчанию (в минутах)
DEFAULT_NOTIFICATION_TIME = 5

def error_handler(update: object, context: CallbackContext):
    """Отправляет уведомление администратору при возникновении ошибки."""
    logger.error(msg="Произошла ошибка при обработке обновления:", exc_info=context.error)
    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = ''.join(tb_list)

    message = (
        f"⚠️ Произошла ошибка:\n\n"
        f"{context.error}\n\n"
        f"Трейсбек:\n"
        f"{tb_string}"
    )

    if ADMIN_CHAT_ID:
        try:
            context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=message, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение админу: {e}")

def start(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    context.user_data['user_id'] = chat_id
    logger.info(f"Пользователь {chat_id} начал взаимодействие с ботом.")
    main_menu(update, context)
    return CHOOSING

def main_menu(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton('➕ Добавить задачу', callback_data='main_add_task')],
        [InlineKeyboardButton('📅 Расписание на неделю', callback_data='main_weekly_schedule')],
        [InlineKeyboardButton('📝 Быстрая заметка', callback_data='main_quick_note')],
        [InlineKeyboardButton('🔔 Настройки', callback_data='main_settings')],
        [InlineKeyboardButton('📌 Подписки', callback_data='main_subscriptions')],
        [InlineKeyboardButton('📋 Мои задачи', callback_data='main_my_tasks')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    welcome_text = '👋 <b>Добро пожаловать в To-Do бот!</b>\nВыберите действие:'
    try:
        if update.callback_query:
            query = update.callback_query
            query.edit_message_text(welcome_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        else:
            update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Ошибка при редактировании главного меню: {e}")
    return CHOOSING

def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    data = query.data
    logger.info(f"Получены данные callback_data: {data}")
    query.answer()

    if data == 'main_add_task':
        context.user_data['previous_menu'] = 'main_menu'
        try:
            query.edit_message_text('📌 <b>Добавление задачи:</b>\nВведите топик задачи.', reply_markup=back_button(), parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"Ошибка при редактировании сообщения для добавления задачи: {e}")
            query.message.reply_text('📌 <b>Добавление задачи:</b>\nВведите топик задачи.', reply_markup=back_button(), parse_mode=ParseMode.HTML)
        return ADD_TASK_TOPIC

    elif data == 'main_my_tasks':
        context.user_data['previous_menu'] = 'main_menu'
        return my_tasks(update, context)

    elif data == 'main_weekly_schedule':
        context.user_data['previous_menu'] = 'main_menu'
        return manage_schedule(update, context)

    elif data == 'main_quick_note':
        context.user_data['previous_menu'] = 'main_menu'
        try:
            query.edit_message_text('📝 <b>Быстрая заметка:</b>\nВведите вашу заметку.', reply_markup=back_button(), parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"Ошибка при редактировании сообщения для быстрой заметки: {e}")
            query.message.reply_text('📝 <b>Быстрая заметка:</b>\nВведите вашу заметку.', reply_markup=back_button(), parse_mode=ParseMode.HTML)
        return QUICK_NOTE

    elif data == 'main_settings':
        return settings_menu(update, context)

    elif data == 'main_subscriptions':
        return subscriptions_menu(update, context)

    elif data == 'main_my_tasks':
        return my_tasks(update, context)

    elif data == 'back':
        return main_menu(update, context)

    else:
        logger.warning(f"Неизвестные callback_data: {data}")
        return CHOOSING

def add_task_topic(update: Update, context: CallbackContext):
    topic = update.message.text
    context.user_data['task_topic'] = topic
    logger.info(f"Получен топик задачи: {topic}")
    # Спрашиваем, нужно ли прикреплять материалы
    keyboard = [
        [
            InlineKeyboardButton("✅ Да", callback_data='attach_yes'),
            InlineKeyboardButton("❌ Нет", callback_data='attach_no')
        ],
        [InlineKeyboardButton('🔙 Назад', callback_data='back')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text('Хотите прикрепить к задаче файлы, ссылки, видео или фото?', reply_markup=reply_markup)
    return ADD_TASK_ATTACHMENTS

def add_task_attachments_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    data = query.data
    logger.info(f"Получено решение прикреплять материалы: {data}")
    query.answer()

    if data == 'attach_yes':
        try:
            query.edit_message_text('📎 Прикрепите материалы к задаче. Когда закончите, нажмите кнопку "Готово".', reply_markup=done_button(), parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"Ошибка при редактировании сообщения для прикрепления материалов: {e}")
            query.message.reply_text('📎 Прикрепите материалы к задаче. Когда закончите, нажмите кнопку "Готово".', reply_markup=done_button(), parse_mode=ParseMode.HTML)
        context.user_data['attachments'] = []
        return ADD_TASK_ATTACHMENTS
    elif data == 'attach_no':
        context.user_data['attachments'] = []
        # Запрашиваем время задачи
        try:
            query.edit_message_text(
                '🕒 Теперь отправьте время задачи в формате <code>ГГГГ-ММ-ДД ЧЧ:ММ</code> или <code>ЧЧ:ММ</code> для сегодняшней даты.',
                parse_mode=ParseMode.HTML,
                reply_markup=back_button()
            )
        except Exception as e:
            logger.error(f"Ошибка при отправке запроса времени задачи: {e}")
            query.message.reply_text(
                '🕒 Теперь отправьте время задачи в формате <code>ГГГГ-ММ-ДД ЧЧ:ММ</code> или <code>ЧЧ:ММ</code> для сегодняшней даты.',
                parse_mode=ParseMode.HTML,
                reply_markup=back_button()
            )
        return TYPING_TIME
    elif data == 'back':
        return add_task_topic(update, context)
    else:
        logger.warning(f"Неизвестное callback_data в прикреплениях: {data}")
        return ADD_TASK_ATTACHMENTS

def add_task_done(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    # Запрашиваем время задачи
    try:
        query.edit_message_text(
            '🕒 Теперь отправьте время задачи в формате <code>ГГГГ-ММ-ДД ЧЧ:ММ</code> или <code>ЧЧ:ММ</code> для сегодняшней даты.',
            parse_mode=ParseMode.HTML,
            reply_markup=back_button()
        )
    except Exception as e:
        logger.error(f"Ошибка при отправке запроса времени задачи после прикреплений: {e}")
        query.message.reply_text(
            '🕒 Теперь отправьте время задачи в формате <code>ГГГГ-ММ-ДД ЧЧ:ММ</code> или <code>ЧЧ:ММ</code> для сегодняшней даты.',
            parse_mode=ParseMode.HTML,
            reply_markup=back_button()
        )
    return TYPING_TIME

    # ... ваш предыдущий код ...

def back_button():
    keyboard = [[InlineKeyboardButton('🔙 Назад', callback_data='back')]]
    return InlineKeyboardMarkup(keyboard)

def done_button():
    keyboard = [[InlineKeyboardButton('✅ Готово', callback_data='done')]]
    return InlineKeyboardMarkup(keyboard)

def add_task_attachments_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    data = query.data
    logger.info(f"Получено решение прикреплять материалы: {data}")
    query.answer()

    if data == 'attach_yes':
        try:
            query.edit_message_text('📎 Прикрепите материалы к задаче. Когда закончите, нажмите кнопку "✅ Готово".', reply_markup=done_button(), parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"Ошибка при редактировании сообщения для прикрепления материалов: {e}")
            query.message.reply_text('📎 Прикрепите материалы к задаче. Когда закончите, нажмите кнопку "✅ Готово".', reply_markup=done_button(), parse_mode=ParseMode.HTML)
        context.user_data['attachments'] = []
        return ADD_TASK_ATTACHMENTS
    elif data == 'attach_no' or data == 'done':
        context.user_data['attachments'] = context.user_data.get('attachments', [])
        # Запрашиваем время задачи
        try:
            query.edit_message_text(
                '🕒 Теперь отправьте время задачи в формате <code>ГГГГ-ММ-ДД ЧЧ:ММ</code> или <code>ЧЧ:ММ</code> для сегодняшней даты.',
                parse_mode=ParseMode.HTML,
                reply_markup=back_button()
            )
        except Exception as e:
            logger.error(f"Ошибка при отправке запроса времени задачи: {e}")
            query.message.reply_text(
                '🕒 Теперь отправьте время задачи в формате <code>ГГГГ-ММ-ДД ЧЧ:ММ</code> или <code>ЧЧ:ММ</code> для сегодняшней даты.',
                parse_mode=ParseMode.HTML,
                reply_markup=back_button()
            )
        return TYPING_TIME
    elif data == 'back':
        return add_task_topic(update, context)
    else:
        logger.warning(f"Неизвестное callback_data в прикреплениях: {data}")
        return ADD_TASK_ATTACHMENTS

def received_task_attachment(update: Update, context: CallbackContext):
    user_input = update.message

    if user_input.text and user_input.text.lower() == 'готово':
        # Завершение прикрепления
        update.message.reply_text('📌 Прикрепление материалов завершено. Переходим к времени задачи.', reply_markup=back_button())
        # Запрашиваем время задачи
        update.message.reply_text(
            '🕒 Теперь отправьте время задачи в формате <code>ГГГГ-ММ-ДД ЧЧ:ММ</code> или <code>ЧЧ:ММ</code> для сегодняшней даты.',
            parse_mode=ParseMode.HTML,
            reply_markup=back_button()
        )
        return TYPING_TIME

    # Обработка различных типов вложений
    attachment = None
    if user_input.document:
        attachment = f'📄 Файл: {user_input.document.file_name}'
    elif user_input.photo:
        attachment = '🖼️ Фото'
    elif user_input.video:
        attachment = '📹 Видео'
    elif user_input.text and user_input.entities:
        # Проверка на ссылки
        for entity in user_input.entities:
            if entity.type == 'url':
                attachment = f'🔗 Ссылка: {user_input.text[entity.offset:entity.offset + entity.length]}'
                break
    elif user_input.text:
        attachment = user_input.text

    if attachment:
        context.user_data['attachments'].append(attachment)
        update.message.reply_text(f'✅ Добавлено: {attachment}', reply_markup=done_button())
    else:
        update.message.reply_text('❌ Не удалось распознать прикрепленный материал. Попробуйте снова.', reply_markup=done_button())

    return ADD_TASK_ATTACHMENTS

# ... ваш последующий код ...

def received_time(update: Update, context: CallbackContext):
    input_time = update.message.text
    logger.info(f"Получено время задачи: {input_time}")
    try:
        task_time = parse_time(input_time)
        if not task_time:
            update.message.reply_text(
                '❌ Неверный формат времени. Пожалуйста, используйте формат <code>ГГГГ-ММ-ДД ЧЧ:ММ</code> или <code>ЧЧ:ММ</code>',
                parse_mode=ParseMode.HTML,
                reply_markup=back_button()
            )
            logger.warning("Некорректный формат времени.")
            return TYPING_TIME

        context.user_data['task_time'] = task_time
        attachments = context.user_data.get('attachments', [])

        task_info = f"📝 <b>Топик:</b> {context.user_data['task_topic']}\n⏰ <b>Время:</b> {task_time.strftime('%Y-%m-%d %H:%M')}"
        if attachments:
            task_info += "\n📎 <b>Прикрепленные материалы:</b>\n" + "\n".join(attachments)

        keyboard = [
            [
                InlineKeyboardButton("✅ Да", callback_data='conf_confirm_yes'),
                InlineKeyboardButton("❌ Нет", callback_data='conf_confirm_no')
            ],
            [InlineKeyboardButton('🔙 Назад', callback_data='conf_back')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        # Отправляем новое сообщение с подтверждением
        update.message.reply_text(
            f'📋 <b>Проверьте информацию:</b>\n{task_info}\n\nВсе верно?',
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )
        logger.info("Отправлено подтверждение задачи.")
        return CONFIRMING
    except Exception as e:
        logger.error(f"Ошибка при обработке времени: {e}")
        update.message.reply_text(
            '⚠️ Произошла ошибка при обработке времени. Пожалуйста, попробуйте снова.',
            reply_markup=back_button()
        )
        return TYPING_TIME

def parse_time(input_time):
    now = datetime.now(TIMEZONE)
    try:
        if len(input_time) == 5:  # Формат ЧЧ:ММ
            task_time = datetime.strptime(input_time, '%H:%M').replace(
                year=now.year,
                month=now.month,
                day=now.day
            )
            task_time = TIMEZONE.localize(task_time)
            if task_time < now:
                task_time += timedelta(days=1)
            logger.info(f"Parsed time (ЧЧ:ММ): {task_time}")
        elif len(input_time) == 16:  # Формат ГГГГ-ММ-ДД ЧЧ:ММ
            task_time = datetime.strptime(input_time, '%Y-%m-%d %H:%M')
            task_time = TIMEZONE.localize(task_time)
            logger.info(f"Parsed time (ГГГГ-ММ-ДД ЧЧ:ММ): {task_time}")
        else:
            logger.warning("Введено время неподходящего формата.")
            return None
        return task_time
    except ValueError:
        logger.warning("Ошибка при парсинге времени.")
        return None

def confirm_task(update: Update, context: CallbackContext):
    query = update.callback_query
    data = query.data
    logger.info(f"Получено подтверждение задачи: {data}")
    query.answer()

    if data == 'conf_confirm_yes':
        user_id = context.user_data.get('user_id')
        topic = context.user_data.get('task_topic')
        time = context.user_data.get('task_time')
        attachments = context.user_data.get('attachments', [])

        if topic and time:
            # Сохраняем задачу в базу данных
            cursor.execute('INSERT INTO tasks (user_id, topic, description, attachments, time) VALUES (?, ?, ?, ?, ?)',
                           (user_id, topic, '', '; '.join(attachments), time.strftime('%Y-%m-%d %H:%M')))
            conn.commit()

            # Планируем напоминание
            notification_time = context.user_data.get('notification_time', DEFAULT_NOTIFICATION_TIME)
            schedule_notification(user_id, topic, time, notification_time, attachments)

            try:
                query.edit_message_text('✅ Задача сохранена! Уведомление будет отправлено вовремя.')
                logger.info("Задача успешно сохранена и напоминание запланировано.")
            except Exception as e:
                logger.error(f"Ошибка при редактировании сообщения после сохранения задачи: {e}")
                query.message.reply_text('✅ Задача сохранена! Уведомление будет отправлено вовремя.')

            return main_menu(update, context)

        else:
            try:
                query.edit_message_text('❌ Ошибка: отсутствуют данные задачи или времени.')
                logger.error("Отсутствуют данные задачи или времени.")
            except Exception as e:
                logger.error(f"Ошибка при редактировании сообщения об ошибке: {e}")
                query.message.reply_text('❌ Ошибка: отсутствуют данные задачи или времени.')
            return main_menu(update, context)

    elif data == 'conf_confirm_no':
        try:
            query.edit_message_text('❌ Добавление задачи отменено.', reply_markup=back_button())
            logger.info("Добавление задачи отменено пользователем.")
        except Exception as e:
            logger.error(f"Ошибка при редактировании сообщения после отмены задачи: {e}")
            query.message.reply_text('❌ Добавление задачи отменено.', reply_markup=back_button())
        return main_menu(update, context)

    elif data == 'conf_back':
        # Возвращаемся к вводу времени
        try:
            query.edit_message_text(
                '🕒 Отправьте время задачи в формате <code>ГГГГ-ММ-ДД ЧЧ:ММ</code> или <code>ЧЧ:ММ</code> для сегодняшней даты.',
                parse_mode=ParseMode.HTML,
                reply_markup=back_button()
            )
            logger.info("Возврат к вводу времени.")
        except Exception as e:
            logger.error(f"Ошибка при возврате к вводу времени: {e}")
            query.message.reply_text(
                '🕒 Отправьте время задачи в формате <code>ГГГГ-ММ-ДД ЧЧ:ММ</code> или <code>ЧЧ:ММ</code> для сегодняшней даты.',
                parse_mode=ParseMode.HTML,
                reply_markup=back_button()
            )
        return TYPING_TIME

    else:
        logger.warning(f"Неизвестное подтверждение задачи: {data}")
        return CONFIRMING

def manage_schedule(update: Update, context: CallbackContext):
    """Менеджер расписания: просмотр, добавление, сброс."""
    keyboard = [
        [InlineKeyboardButton('➕ Добавить расписание', callback_data='schedule_add')],
        [InlineKeyboardButton('🗑️ Сбросить расписание', callback_data='schedule_reset')],
        [InlineKeyboardButton('🔙 Назад', callback_data='back')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    try:
        if update.callback_query:
            query = update.callback_query
            query.edit_message_text('📅 <b>Управление расписанием:</b>', reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        else:
            update.message.reply_text('📅 <b>Управление расписанием:</b>', reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Ошибка при редактировании меню управления расписанием: {e}")
        if update.callback_query:
            update.callback_query.message.reply_text('📅 <b>Управление расписанием:</b>', reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        else:
            update.message.reply_text('📅 <b>Управление расписанием:</b>', reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    return SELECT_DAY

def schedule_reset(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    user_id = context.user_data.get('user_id')
    cursor.execute('DELETE FROM schedules WHERE user_id = ?', (user_id,))
    conn.commit()
    try:
        query.edit_message_text('🗑️ Расписание сброшено.', reply_markup=back_button(), parse_mode=ParseMode.HTML)
        logger.info("Расписание сброшено пользователем.")
    except Exception as e:
        logger.error(f"Ошибка при редактировании сообщения после сброса расписания: {e}")
        query.message.reply_text('🗑️ Расписание сброшено.', reply_markup=back_button(), parse_mode=ParseMode.HTML)
    return manage_schedule(update, context)

def schedule_add(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    keyboard = [
        [InlineKeyboardButton('Понедельник', callback_data='schedule_Monday')],
        [InlineKeyboardButton('Вторник', callback_data='schedule_Tuesday')],
        [InlineKeyboardButton('Среда', callback_data='schedule_Wednesday')],
        [InlineKeyboardButton('Четверг', callback_data='schedule_Thursday')],
        [InlineKeyboardButton('Пятница', callback_data='schedule_Friday')],
        [InlineKeyboardButton('Суббота', callback_data='schedule_Saturday')],
        [InlineKeyboardButton('Воскресенье', callback_data='schedule_Sunday')],
        [InlineKeyboardButton('🔙 Назад', callback_data='back')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    try:
        query.edit_message_text('📅 Выберите день недели для добавления расписания:', reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Ошибка при редактировании сообщения выбора дня недели для расписания: {e}")
        query.message.reply_text('📅 Выберите день недели для добавления расписания:', reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    return SUBSCRIPTION_CATEGORY  # Reusing a state; better to define a new one if needed

def select_schedule_day(update: Update, context: CallbackContext):
    query = update.callback_query
    data = query.data
    day = data.split('_')[1]  # 'schedule_Monday' -> 'Monday'
    context.user_data['schedule_day'] = day
    logger.info(f"Выбран день для расписания: {day}")

    keyboard = [
        [InlineKeyboardButton('🌅 Утро (6-12)', callback_data='schedule_time_Morning')],
        [InlineKeyboardButton('🌇 День (12-18)', callback_data='schedule_time_Afternoon')],
        [InlineKeyboardButton('🌃 Вечер (18-24)', callback_data='schedule_time_Evening')],
        [InlineKeyboardButton('🔙 Назад', callback_data='back')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    try:
        query.edit_message_text(f'📅 Выберите время суток для {day}:', reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Ошибка при редактировании сообщения выбора времени суток: {e}")
        query.message.reply_text(f'📅 Выберите время суток для {day}:', reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    return SELECT_TIME_OF_DAY

def select_schedule_time_of_day(update: Update, context: CallbackContext):
    query = update.callback_query
    data = query.data
    time_of_day = data.split('_')[2]  # 'schedule_time_Morning' -> 'Morning'
    context.user_data['schedule_time_of_day'] = time_of_day
    logger.info(f"Выбрано время суток для расписания: {time_of_day}")

    # Определяем диапазон времени суток
    time_ranges = {
        'Morning': (6, 12),
        'Afternoon': (12, 18),
        'Evening': (18, 24)
    }

    start_hour, end_hour = time_ranges.get(time_of_day, (6, 12))
    hours = list(range(start_hour, end_hour))  # Например, 6-12 -> 6,7,...11

    context.user_data['schedule_hours'] = hours
    context.user_data['current_schedule_hour'] = 0
    context.user_data['schedule_tasks'] = {}

    if hours:
        current_hour = hours[0]
        context.user_data['current_schedule_hour'] = 0
        update.message.reply_text(f'🕒 Введите задачу для {time_of_day} в {current_hour}:00:')
        logger.info(f"Запрошена задача для {time_of_day} в {current_hour}:00")
        return SET_SCHEDULE_HOUR
    else:
        update.message.reply_text('❌ Некорректный диапазон времени.', reply_markup=back_button())
        logger.error("Некорректный диапазон времени.")
        return manage_schedule(update, context)

def set_schedule_hour(update: Update, context: CallbackContext):
    task = update.message.text
    hour_index = context.user_data['current_schedule_hour']
    hours = context.user_data['schedule_hours']
    time_of_day = context.user_data['schedule_time_of_day']
    day = context.user_data['schedule_day']

    current_hour = hours[hour_index]
    context.user_data['schedule_tasks'][current_hour] = task
    logger.info(f"Задача для {day} {time_of_day} в {current_hour}:00 установлена: {task}")

    # Переходим к следующему часу или завершению
    if hour_index + 1 < len(hours):
        context.user_data['current_schedule_hour'] += 1
        next_hour = hours[hour_index + 1]
        update.message.reply_text(f'🕒 Введите задачу для {time_of_day} в {next_hour}:00:')
        logger.info(f"Запрошена задача для {time_of_day} в {next_hour}:00")
        return SET_SCHEDULE_HOUR
    else:
        # Все задачи для выбранного времени суток введены
        keyboard = [
            [InlineKeyboardButton('✅ Сохранить расписание', callback_data='schedule_save')],
            [InlineKeyboardButton('🔙 Назад', callback_data='back')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        update.message.reply_text('📅 Все задачи для этого времени суток введены. Сохранить расписание?', reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        logger.info("Запрошено сохранение расписания.")
        return SAVE_SCHEDULE

def save_schedule(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    user_id = context.user_data.get('user_id')
    day = context.user_data.get('schedule_day')
    time_of_day = context.user_data.get('schedule_time_of_day')
    tasks = context.user_data.get('schedule_tasks', {})

    for hour, task in tasks.items():
        cursor.execute('INSERT INTO schedules (user_id, day, time_of_day, hour, task) VALUES (?, ?, ?, ?, ?)',
                       (user_id, day, time_of_day, hour, task))
    conn.commit()

    try:
        query.edit_message_text('✅ Расписание сохранено.', reply_markup=back_button(), parse_mode=ParseMode.HTML)
        logger.info("Расписание успешно сохранено.")
    except Exception as e:
        logger.error(f"Ошибка при редактировании сообщения после сохранения расписания: {e}")
        query.message.reply_text('✅ Расписание сохранено.', reply_markup=back_button(), parse_mode=ParseMode.HTML)

    return manage_schedule(update, context)

def reset_schedule(update: Update, context: CallbackContext):
    """Функция для сброса расписания пользователя."""
    query = update.callback_query
    query.answer()
    user_id = context.user_data.get('user_id')
    cursor.execute('DELETE FROM schedules WHERE user_id = ?', (user_id,))
    conn.commit()
    try:
        query.edit_message_text('🗑️ Расписание сброшено.', reply_markup=back_button(), parse_mode=ParseMode.HTML)
        logger.info("Расписание сброшено пользователем.")
    except Exception as e:
        logger.error(f"Ошибка при редактировании сообщения после сброса расписания: {e}")
        query.message.reply_text('🗑️ Расписание сброшено.', reply_markup=back_button(), parse_mode=ParseMode.HTML)
    return manage_schedule(update, context)

def schedule_notification(chat_id, task, time, notification_time, attachments):
    notify_time = time - timedelta(minutes=notification_time)
    now = datetime.now(TIMEZONE)
    if notify_time < now:
        send_notification(chat_id, task, attachments)
        logger.info(f"Напоминание отправлено сразу для задачи '{task}'.")
    else:
        try:
            job_id = f"notif_{chat_id}_{task}_{notify_time.timestamp()}"
            scheduler.add_job(
                send_notification,
                'date',
                run_date=notify_time,
                args=[chat_id, task, attachments],
                timezone=TIMEZONE,
                id=job_id
            )
            logger.info(f"Запланировано напоминание для задачи '{task}' на {notify_time}.")
        except Exception as e:
            logger.error(f"Ошибка при планировании напоминания: {e}")

def send_notification(chat_id, task, attachments):
    notification_text = f'🔔 <b>Напоминание о задаче:</b>\n📝 {task}'
    if attachments:
        notification_text += '\n\n📎 <b>Прикрепленные материалы:</b>\n' + '\n'.join(attachments)
    try:
        updater.bot.send_message(chat_id=chat_id, text=notification_text, parse_mode=ParseMode.HTML)
        logger.info(f"Напоминание отправлено для задачи: {task}")
    except Exception as e:
        logger.error(f"Ошибка при отправке уведомления: {e}")

def my_tasks(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    user_id = context.user_data.get('user_id')

    cursor.execute('SELECT topic, description, attachments, time FROM tasks WHERE user_id = ? ORDER BY time', (user_id,))
    tasks = cursor.fetchall()
    if tasks:
        message = '📋 <b>Ваши задачи:</b>\n\n'
        for task in tasks:
            topic, description, attachments, time_str = task
            message += f"• 📝 <b>Топик:</b> {topic}\n  ⏰ <b>Время:</b> {time_str}\n"
            if attachments:
                message += f"  📎 <b>Прикрепления:</b> {attachments}\n"
            message += "\n"
    else:
        message = '📋 У вас нет задач.'

    keyboard = [[InlineKeyboardButton('🔙 Назад', callback_data='back')]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        query.edit_message_text(text=message, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
        logger.info("Отображены текущие задачи пользователя.")
    except Exception as e:
        logger.error(f"Ошибка при редактировании сообщения с задачами: {e}")
        query.message.reply_text(text=message, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    return CHOOSING

def quick_note_handler(update: Update, context: CallbackContext):
    context.user_data['quick_note'] = update.message.text
    logger.info(f"Получена быстрая заметка: {update.message.text}")
    keyboard = [
        [
            InlineKeyboardButton("✅ Установить напоминание", callback_data='quick_confirm_yes'),
            InlineKeyboardButton("❌ Без напоминания", callback_data='quick_confirm_no')
        ],
        [InlineKeyboardButton('🔙 Назад', callback_data='back')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text('Хотите установить напоминание для этой заметки?', reply_markup=reply_markup)
    return QUICK_NOTE_CONFIRM

def handle_quick_note_confirmation(update: Update, context: CallbackContext):
    query = update.callback_query
    data = query.data
    logger.info(f"Получено подтверждение для быстрой заметки: {data}")
    query.answer()

    if data == 'quick_confirm_yes':
        try:
            query.edit_message_text(
                '🕒 Введите время напоминания для заметки в формате <code>ГГГГ-ММ-ДД ЧЧ:ММ</code> или <code>ЧЧ:ММ</code> для сегодняшней даты.',
                parse_mode=ParseMode.HTML,
                reply_markup=back_button()
            )
            logger.info("Запрошено время напоминания для быстрой заметки.")
        except Exception as e:
            logger.error(f"Ошибка при редактировании сообщения для ввода времени напоминания: {e}")
            query.message.reply_text(
                '🕒 Введите время напоминания для заметки в формате <code>ГГГГ-ММ-ДД ЧЧ:ММ</code> или <code>ЧЧ:ММ</code> для сегодняшней даты.',
                parse_mode=ParseMode.HTML,
                reply_markup=back_button()
            )
        return QUICK_NOTE_TIME

    elif data == 'quick_confirm_no':
        # Сохраняем заметку без напоминания
        user_id = context.user_data.get('user_id')
        note = context.user_data.get('quick_note')
        cursor.execute('INSERT INTO tasks (user_id, topic, description, attachments, time) VALUES (?, ?, ?, ?, ?)',
                       (user_id, 'Быстрая заметка', note, '', ''))
        conn.commit()
        try:
            query.edit_message_text('✅ Заметка сохранена без напоминания.', reply_markup=back_button(), parse_mode=ParseMode.HTML)
            logger.info("Заметка сохранена без напоминания.")
        except Exception as e:
            logger.error(f"Ошибка при редактировании сообщения после сохранения заметки без напоминания: {e}")
            query.message.reply_text('✅ Заметка сохранена без напоминания.', reply_markup=back_button(), parse_mode=ParseMode.HTML)
        return main_menu(update, context)

    elif data == 'back':
        try:
            query.edit_message_text('📝 <b>Быстрая заметка:</b>\nВведите вашу заметку.', reply_markup=back_button(), parse_mode=ParseMode.HTML)
            logger.info("Возврат к вводу заметки.")
        except Exception as e:
            logger.error(f"Ошибка при возврате к вводу заметки: {e}")
            query.message.reply_text('📝 <b>Быстрая заметка:</b>\nВведите вашу заметку.', reply_markup=back_button(), parse_mode=ParseMode.HTML)
        return QUICK_NOTE

    else:
        logger.warning(f"Неизвестное подтверждение для быстрой заметки: {data}")
        return QUICK_NOTE_CONFIRM

def quick_note_time_handler(update: Update, context: CallbackContext):
    input_time = update.message.text
    logger.info(f"Получено время напоминания для заметки: {input_time}")
    try:
        task_time = parse_time(input_time)
        if not task_time:
            update.message.reply_text(
                '❌ Неверный формат времени. Пожалуйста, используйте формат <code>ГГГГ-ММ-ДД ЧЧ:ММ</code> или <code>ЧЧ:ММ</code>',
                parse_mode=ParseMode.HTML,
                reply_markup=back_button()
            )
            logger.warning("Некорректный формат времени для заметки.")
            return QUICK_NOTE_TIME

        context.user_data['quick_note_time'] = task_time
        note = context.user_data.get('quick_note')

        # Сохраняем заметку в базу данных
        user_id = context.user_data.get('user_id')
        cursor.execute('INSERT INTO tasks (user_id, topic, description, attachments, time) VALUES (?, ?, ?, ?, ?)',
                       (user_id, 'Быстрая заметка', note, '', task_time.strftime('%Y-%m-%d %H:%M')))
        conn.commit()

        # Планируем напоминание
        notification_time = context.user_data.get('notification_time', DEFAULT_NOTIFICATION_TIME)
        schedule_notification(user_id, note, task_time, notification_time, [])

        # Отправляем подтверждение
        try:
            update.message.reply_text('✅ Заметка сохранена с напоминанием!', reply_markup=back_button(), parse_mode=ParseMode.HTML)
            logger.info("Заметка сохранена с напоминанием.")
        except Exception as e:
            logger.error(f"Ошибка при отправке подтверждения сохранения заметки с напоминанием: {e}")
            update.message.reply_text('✅ Заметка сохранена с напоминанием!', reply_markup=back_button(), parse_mode=ParseMode.HTML)

        return main_menu(update, context)

    except Exception as e:
        logger.error(f"Ошибка при обработке времени для заметки: {e}")
        update.message.reply_text(
            '⚠️ Произошла ошибка при обработке времени. Пожалуйста, попробуйте снова.',
            reply_markup=back_button()
        )
        return QUICK_NOTE_TIME

def settings_menu(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton('⏰ Настроить время напоминания', callback_data='set_notification_time')],
        [InlineKeyboardButton('🔙 Назад', callback_data='back')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    query = update.callback_query
    try:
        query.edit_message_text('🔔 <b>Настройки:</b>', reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        logger.info("Отображено меню настроек.")
    except Exception as e:
        logger.error(f"Ошибка при редактировании сообщения настроек: {e}")
        query.message.reply_text('🔔 <b>Настройки:</b>', reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    return SETTINGS

def set_notification_time(update: Update, context: CallbackContext):
    input_minutes = update.message.text
    logger.info(f"Устанавливается время напоминания: {input_minutes} минут")
    try:
        minutes = int(input_minutes)
        if minutes <= 0:
            raise ValueError("Время должно быть положительным числом.")
        context.user_data['notification_time'] = minutes
        update.message.reply_text(f'⏰ Время напоминания установлено на {minutes} минут(ы) перед задачей.', reply_markup=back_button())
        logger.info(f"Время напоминания установлено: {minutes} минут")
        return settings_menu(update, context)
    except ValueError:
        update.message.reply_text('❌ Пожалуйста, введите положительное число.', reply_markup=back_button())
        logger.warning("Пользователь ввел некорректное значение времени напоминания.")
        return SET_NOTIFICATION_TIME
    except Exception as e:
        logger.error(f"Ошибка при установке времени напоминания: {e}")
        update.message.reply_text('⚠️ Произошла ошибка при установке времени. Попробуйте снова.', reply_markup=back_button())
        return SET_NOTIFICATION_TIME

def subscriptions_menu(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    user_id = context.user_data.get('user_id')

    keyboard = [
        [InlineKeyboardButton('🏋️‍♂️ Спорт', callback_data='subscription_Sport')],
        [InlineKeyboardButton('📚 Учеба', callback_data='subscription_Study')],
        [InlineKeyboardButton('🎉 Отдых', callback_data='subscription_Rest')],
        [InlineKeyboardButton('💌 Личное', callback_data='subscription_Personal')],
        [InlineKeyboardButton('➕ Добавить подписку', callback_data='add_subscription')],
        [InlineKeyboardButton('🔙 Назад', callback_data='back')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        query.edit_message_text('📌 <b>Подписки:</b>\nВыберите категорию:', reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        logger.info("Отображено меню подписок с категориями.")
    except Exception as e:
        logger.error(f"Ошибка при редактировании меню подписок: {e}")
        query.message.reply_text('📌 <b>Подписки:</b>\nВыберите категорию:', reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    return SUBSCRIPTION_CATEGORY

def subscription_category_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    data = query.data
    category = data.split('_')[1]  # 'subscription_Sport' -> 'Sport'
    context.user_data['subscription_category'] = category
    logger.info(f"Выбрана категория подписок: {category}")

    keyboard = [
        [InlineKeyboardButton('📄 Просмотр подписок', callback_data='view_subscriptions')],
        [InlineKeyboardButton('➕ Добавить подписку', callback_data='add_subscription')],
        [InlineKeyboardButton('🔙 Назад', callback_data='back')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        query.edit_message_text(f'📌 <b>Категория:</b> {category}\nВыберите действие:', reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        logger.info(f"Отображено меню действий для категории {category}.")
    except Exception as e:
        logger.error(f"Ошибка при редактировании меню действий для категории {category}: {e}")
        query.message.reply_text(f'📌 <b>Категория:</b> {category}\nВыберите действие:', reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    return VIEW_SUBSCRIPTION

def view_subscriptions(update: Update, context: CallbackContext):
    query = update.callback_query
    category = context.user_data.get('subscription_category')
    user_id = context.user_data.get('user_id')

    cursor.execute('SELECT content FROM subscriptions WHERE user_id = ? AND category = ?', (user_id, category))
    subs = cursor.fetchall()
    if subs:
        message = f'📌 <b>Ваши подписки в категории "{category}":</b>\n\n'
        for sub in subs:
            message += f"• {sub[0]}\n"
    else:
        message = f'📌 У вас нет подписок в категории "{category}".'

    keyboard = [
        [InlineKeyboardButton('➕ Добавить подписку', callback_data='add_subscription')],
        [InlineKeyboardButton('🔙 Назад', callback_data='back')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        query.edit_message_text(text=message, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
        logger.info(f"Отображены подписки в категории {category}.")
    except Exception as e:
        logger.error(f"Ошибка при редактировании сообщения с подписками в категории {category}: {e}")
        query.message.reply_text(text=message, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    return VIEW_SUBSCRIPTION

def add_subscription_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    data = query.data
    if data == 'add_subscription':
        try:
            query.edit_message_text('📌 <b>Добавление подписки:</b>\nВыберите категорию:', reply_markup=subscription_categories_buttons(), parse_mode=ParseMode.HTML)
            logger.info("Запрошена категория для новой подписки.")
        except Exception as e:
            logger.error(f"Ошибка при редактировании сообщения для добавления подписки: {e}")
            query.message.reply_text('📌 <b>Добавление подписки:</b>\nВыберите категорию:', reply_markup=subscription_categories_buttons(), parse_mode=ParseMode.HTML)
        return ADD_SUBSCRIPTION
    elif data.startswith('subscription_'):
        return subscription_category_handler(update, context)
    elif data == 'back':
        return subscriptions_menu(update, context)
    else:
        logger.warning(f"Неизвестные callback_data в добавлении подписки: {data}")
        return SUBSCRIPTION_CATEGORY

def subscription_categories_buttons():
    categories = ['Sport', 'Study', 'Rest', 'Personal']
    keyboard = [[InlineKeyboardButton(cat, callback_data=f'subscription_{cat}')] for cat in categories]
    keyboard.append([InlineKeyboardButton('🔙 Назад', callback_data='back')])
    return InlineKeyboardMarkup(keyboard)

def add_subscription_entry(update: Update, context: CallbackContext):
    category = context.user_data.get('subscription_category')
    user_id = context.user_data.get('user_id')
    user_input = update.message

    if user_input.text:
        content = user_input.text
        logger.info(f"Добавлена подписка в категории {category}: {content}")
    elif user_input.caption:
        content = user_input.caption
        logger.info(f"Добавлена подписка с подписью в категории {category}: {content}")
    elif user_input.photo or user_input.video:
        content = 'Медиа контент'
        logger.info(f"Добавлена медиа подписка в категории {category}.")
    else:
        update.message.reply_text('❌ Не удалось определить контент. Попробуйте еще раз.', reply_markup=back_button())
        logger.warning("Не удалось определить контент для подписки.")
        return ADD_SUBSCRIPTION

    cursor.execute('INSERT INTO subscriptions (user_id, category, content) VALUES (?, ?, ?)', (user_id, category, content))
    conn.commit()
    update.message.reply_text('✅ Подписка добавлена.', reply_markup=back_button())
    logger.info("Подписка успешно добавлена.")
    return subscriptions_menu(update, context)

def send_notification(chat_id, task, attachments):
    notification_text = f'🔔 <b>Напоминание о задаче:</b>\n📝 {task}'
    if attachments:
        notification_text += '\n\n📎 <b>Прикрепленные материалы:</b>\n' + '\n'.join(attachments)
    try:
        updater.bot.send_message(chat_id=chat_id, text=notification_text, parse_mode=ParseMode.HTML)
        logger.info(f"Напоминание отправлено для задачи: {task}")
    except Exception as e:
        logger.error(f"Ошибка при отправке уведомления: {e}")

def back_button():
    keyboard = [[InlineKeyboardButton('🔙 Назад', callback_data='back')]]
    return InlineKeyboardMarkup(keyboard)

def cancel(update: Update, context: CallbackContext):
    update.message.reply_text('🛑 Действие отменено.', reply_markup=back_button())
    logger.info(f"Пользователь {update.message.chat_id} отменил действие.")
    return main_menu(update, context)

def manage_schedule(update: Update, context: CallbackContext):
    """Менеджер расписания: просмотр, добавление, сброс."""
    keyboard = [
        [InlineKeyboardButton('➕ Добавить расписание', callback_data='schedule_add')],
        [InlineKeyboardButton('🗑️ Сбросить расписание', callback_data='schedule_reset')],
        [InlineKeyboardButton('🔙 Назад', callback_data='back')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    try:
        if update.callback_query:
            query = update.callback_query
            query.edit_message_text('📅 <b>Управление расписанием:</b>', reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        else:
            update.message.reply_text('📅 <b>Управление расписанием:</b>', reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Ошибка при редактировании меню управления расписанием: {e}")
        if update.callback_query:
            update.callback_query.message.reply_text('📅 <b>Управление расписанием:</b>', reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        else:
            update.message.reply_text('📅 <b>Управление расписанием:</b>', reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    return SELECT_DAY

def subscriptions_menu(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    user_id = context.user_data.get('user_id')

    keyboard = [
        [InlineKeyboardButton('🏋️‍♂️ Спорт', callback_data='subscription_Sport')],
        [InlineKeyboardButton('📚 Учеба', callback_data='subscription_Study')],
        [InlineKeyboardButton('🎉 Отдых', callback_data='subscription_Rest')],
        [InlineKeyboardButton('💌 Личное', callback_data='subscription_Personal')],
        [InlineKeyboardButton('➕ Добавить подписку', callback_data='add_subscription')],
        [InlineKeyboardButton('🔙 Назад', callback_data='back')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        query.edit_message_text('📌 <b>Подписки:</b>\nВыберите категорию:', reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        logger.info("Отображено меню подписок с категориями.")
    except Exception as e:
        logger.error(f"Ошибка при редактировании меню подписок: {e}")
        query.message.reply_text('📌 <b>Подписки:</b>\nВыберите категорию:', reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    return SUBSCRIPTION_CATEGORY

def add_subscription(update: Update, context: CallbackContext):
    # Эта функция теперь обрабатывает добавление подписок через menu
    return add_subscription_handler(update, context)

def manage_schedule(update: Update, context: CallbackContext):
    """Менеджер расписания: просмотр, добавление, сброс."""
    keyboard = [
        [InlineKeyboardButton('➕ Добавить расписание', callback_data='schedule_add')],
        [InlineKeyboardButton('🗑️ Сбросить расписание', callback_data='schedule_reset')],
        [InlineKeyboardButton('🔙 Назад', callback_data='back')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    try:
        if update.callback_query:
            query = update.callback_query
            query.edit_message_text('📅 <b>Управление расписанием:</b>', reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        else:
            update.message.reply_text('📅 <b>Управление расписанием:</b>', reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Ошибка при редактировании меню управления расписанием: {e}")
        if update.callback_query:
            update.callback_query.message.reply_text('📅 <b>Управление расписанием:</b>', reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        else:
            update.message.reply_text('📅 <b>Управление расписанием:</b>', reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    return SELECT_DAY

def ConversationHandler_states():
    # Обновленный ConversationHandler с добавленными состояниями
    return {
        CHOOSING: [
            CallbackQueryHandler(button_handler, pattern='^(main_add_task|main_weekly_schedule|main_quick_note|main_settings|main_subscriptions|main_my_tasks)$')
        ],
        ADD_TASK_TOPIC: [
            MessageHandler(Filters.text & ~Filters.command, add_task_topic)
        ],
        ADD_TASK_ATTACHMENTS: [
            CallbackQueryHandler(add_task_attachments_handler, pattern='^(attach_yes|attach_no|back)$'),
            MessageHandler(Filters.all & ~Filters.command, received_task_attachment)
        ],
        TYPING_TIME: [
            MessageHandler(Filters.text & ~Filters.command, received_time),
            CallbackQueryHandler(button_handler, pattern='^back$')
        ],
        CONFIRMING: [
            CallbackQueryHandler(confirm_task, pattern='^(conf_confirm_yes|conf_confirm_no|conf_back)$')
        ],
        SELECT_DAY: [
            CallbackQueryHandler(select_schedule_day, pattern='^(schedule_add|schedule_reset|schedule_Monday|schedule_Tuesday|schedule_Wednesday|schedule_Thursday|schedule_Friday|schedule_Saturday|schedule_Sunday|back)$')
        ],
        SELECT_TIME_OF_DAY: [
            CallbackQueryHandler(select_schedule_time_of_day, pattern='^(schedule_time_Morning|schedule_time_Afternoon|schedule_time_Evening|schedule_time_CustomTime|back)$')
        ],
        SET_SCHEDULE_HOUR: [
            MessageHandler(Filters.text & ~Filters.command, set_schedule_hour),
            CallbackQueryHandler(button_handler, pattern='^back$')
        ],
        SAVE_SCHEDULE: [
            CallbackQueryHandler(save_schedule, pattern='^schedule_save$'),
            CallbackQueryHandler(reset_schedule, pattern='^schedule_reset$'),
            CallbackQueryHandler(button_handler, pattern='^back$')
        ],
        QUICK_NOTE: [
            MessageHandler(Filters.text & ~Filters.command, quick_note_handler),
            CallbackQueryHandler(button_handler, pattern='^back$')
        ],
        QUICK_NOTE_CONFIRM: [
            CallbackQueryHandler(handle_quick_note_confirmation, pattern='^(quick_confirm_yes|quick_confirm_no|back)$')
        ],
        QUICK_NOTE_TIME: [
            MessageHandler(Filters.text & ~Filters.command, quick_note_time_handler),
            CallbackQueryHandler(button_handler, pattern='^back$')
        ],
        SETTINGS: [
            CallbackQueryHandler(settings_menu_handler, pattern='^(set_notification_time|back)$')
        ],
        SET_NOTIFICATION_TIME: [
            MessageHandler(Filters.text & ~Filters.command, set_notification_time),
            CallbackQueryHandler(button_handler, pattern='^back$')
        ],
        SUBSCRIPTION_CATEGORY: [
            CallbackQueryHandler(subscription_category_handler, pattern='^(subscription_Sport|subscription_Study|subscription_Rest|subscription_Personal|back)$')
        ],
        VIEW_SUBSCRIPTION: [
            CallbackQueryHandler(view_subscriptions, pattern='^(view_subscriptions|add_subscription|back)$')
        ],
        SUBSCRIPTION_CATEGORY: [
            CallbackQueryHandler(subscription_category_handler, pattern='^(subscription_Sport|subscription_Study|subscription_Rest|subscription_Personal|back)$')
        ],
        ADD_SUBSCRIPTION: [
            MessageHandler(Filters.all & ~Filters.command, add_subscription_entry),
            CallbackQueryHandler(button_handler, pattern='^back$')
        ]
    }

def subscription_category_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    data = query.data
    category = data.split('_')[1]  # 'subscription_Sport' -> 'Sport'
    context.user_data['subscription_category'] = category
    logger.info(f"Выбрана категория подписок: {category}")

    keyboard = [
        [InlineKeyboardButton('📄 Просмотр подписок', callback_data='view_subscriptions')],
        [InlineKeyboardButton('➕ Добавить подписку', callback_data='add_subscription')],
        [InlineKeyboardButton('🔙 Назад', callback_data='back')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        query.edit_message_text(f'📌 <b>Категория:</b> {category}\nВыберите действие:', reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        logger.info(f"Отображено меню действий для категории {category}.")
    except Exception as e:
        logger.error(f"Ошибка при редактировании меню действий для категории {category}: {e}")
        query.message.reply_text(f'📌 <b>Категория:</b> {category}\nВыберите действие:', reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    return VIEW_SUBSCRIPTION

def view_subscriptions(update: Update, context: CallbackContext):
    query = update.callback_query
    category = context.user_data.get('subscription_category')
    user_id = context.user_data.get('user_id')

    cursor.execute('SELECT content FROM subscriptions WHERE user_id = ? AND category = ?', (user_id, category))
    subs = cursor.fetchall()
    if subs:
        message = f'📌 <b>Ваши подписки в категории "{category}":</b>\n\n'
        for sub in subs:
            message += f"• {sub[0]}\n"
    else:
        message = f'📌 У вас нет подписок в категории "{category}".'

    keyboard = [
        [InlineKeyboardButton('➕ Добавить подписку', callback_data='add_subscription')],
        [InlineKeyboardButton('🔙 Назад', callback_data='back')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        query.edit_message_text(text=message, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
        logger.info(f"Отображены подписки в категории {category}.")
    except Exception as e:
        logger.error(f"Ошибка при редактировании сообщения с подписками в категории {category}: {e}")
        query.message.reply_text(text=message, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    return VIEW_SUBSCRIPTION

def settings_menu_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    data = query.data
    if data == 'set_notification_time':
        try:
            query.edit_message_text('⏰ Введите время напоминания в минутах:', reply_markup=back_button())
            logger.info("Запрошено время напоминания.")
        except Exception as e:
            logger.error(f"Ошибка при редактировании сообщения для настройки времени напоминания: {e}")
            query.message.reply_text('⏰ Введите время напоминания в минутах:', reply_markup=back_button())
        return SET_NOTIFICATION_TIME
    elif data == 'back':
        return main_menu(update, context)
    else:
        logger.warning(f"Неизвестные callback_data в настройках: {data}")
        return SETTINGS

def my_tasks(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    user_id = context.user_data.get('user_id')

    cursor.execute('SELECT topic, description, attachments, time FROM tasks WHERE user_id = ? ORDER BY time', (user_id,))
    tasks = cursor.fetchall()
    if tasks:
        message = '📋 <b>Ваши задачи:</b>\n\n'
        for task in tasks:
            topic, description, attachments, time_str = task
            message += f"• 📝 <b>Топик:</b> {topic}\n  ⏰ <b>Время:</b> {time_str}\n"
            if attachments:
                message += f"  📎 <b>Прикрепления:</b> {attachments}\n"
            message += "\n"
    else:
        message = '📋 У вас нет задач.'

    keyboard = [[InlineKeyboardButton('🔙 Назад', callback_data='back')]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        query.edit_message_text(text=message, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
        logger.info("Отображены текущие задачи пользователя.")
    except Exception as e:
        logger.error(f"Ошибка при редактировании сообщения с задачами: {e}")
        query.message.reply_text(text=message, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    return CHOOSING

def schedule_add_handler(update: Update, context: CallbackContext):
    """Обработчик добавления расписания."""
    pass  # Реализовано выше в manage_schedule и связанных функциях

def main():
    # Вставьте свой токен бота здесь
    TOKEN = '8167716193:AAHAYFHZcQ_H8F4mmQazux5nnWWVnv-si3g'  # Замените на ваш реальный токен бота

    global updater
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    # Добавляем обработчик ошибок
    dp.add_error_handler(error_handler)

    # Определяем ConversationHandler
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('start', start),
            CallbackQueryHandler(button_handler, pattern='^(main_add_task|main_weekly_schedule|main_quick_note|main_settings|main_subscriptions|main_my_tasks)$')
        ],
        states={
            CHOOSING: [
                CallbackQueryHandler(button_handler, pattern='^(main_add_task|main_weekly_schedule|main_quick_note|main_settings|main_subscriptions|main_my_tasks)$')
            ],
            ADD_TASK_TOPIC: [
                MessageHandler(Filters.text & ~Filters.command, add_task_topic)
            ],
            ADD_TASK_ATTACHMENTS: [
                CallbackQueryHandler(add_task_attachments_handler, pattern='^(attach_yes|attach_no|back)$'),
                MessageHandler(Filters.all & ~Filters.command, received_task_attachment)
            ],
            TYPING_TIME: [
                MessageHandler(Filters.text & ~Filters.command, received_time),
                CallbackQueryHandler(button_handler, pattern='^back$')
            ],
            CONFIRMING: [
                CallbackQueryHandler(confirm_task, pattern='^(conf_confirm_yes|conf_confirm_no|conf_back)$')
            ],
            SELECT_DAY: [
                CallbackQueryHandler(select_schedule_day, pattern='^(schedule_add|schedule_reset|schedule_Monday|schedule_Tuesday|schedule_Wednesday|schedule_Thursday|schedule_Friday|schedule_Saturday|schedule_Sunday|back)$')
            ],
            SELECT_TIME_OF_DAY: [
                CallbackQueryHandler(select_schedule_time_of_day, pattern='^(schedule_time_Morning|schedule_time_Afternoon|schedule_time_Evening|schedule_time_CustomTime|back)$')
            ],
            SET_SCHEDULE_HOUR: [
                MessageHandler(Filters.text & ~Filters.command, set_schedule_hour),
                CallbackQueryHandler(button_handler, pattern='^back$')
            ],
            SAVE_SCHEDULE: [
                CallbackQueryHandler(save_schedule, pattern='^schedule_save$'),
                CallbackQueryHandler(reset_schedule, pattern='^schedule_reset$'),
                CallbackQueryHandler(button_handler, pattern='^back$')
            ],
            QUICK_NOTE: [
                MessageHandler(Filters.text & ~Filters.command, quick_note_handler),
                CallbackQueryHandler(button_handler, pattern='^back$')
            ],
            QUICK_NOTE_CONFIRM: [
                CallbackQueryHandler(handle_quick_note_confirmation, pattern='^(quick_confirm_yes|quick_confirm_no|back)$')
            ],
            QUICK_NOTE_TIME: [
                MessageHandler(Filters.text & ~Filters.command, quick_note_time_handler),
                CallbackQueryHandler(button_handler, pattern='^back$')
            ],
            SETTINGS: [
                CallbackQueryHandler(settings_menu_handler, pattern='^(set_notification_time|back)$')
            ],
            SET_NOTIFICATION_TIME: [
                MessageHandler(Filters.text & ~Filters.command, set_notification_time),
                CallbackQueryHandler(button_handler, pattern='^back$')
            ],
            SUBSCRIPTION_CATEGORY: [
                CallbackQueryHandler(subscription_category_handler, pattern='^(subscription_Sport|subscription_Study|subscription_Rest|subscription_Personal|back)$')
            ],
            VIEW_SUBSCRIPTION: [
                CallbackQueryHandler(view_subscriptions, pattern='^(view_subscriptions|add_subscription|back)$')
            ],
            ADD_SUBSCRIPTION: [
                MessageHandler(Filters.all & ~Filters.command, add_subscription_entry),
                CallbackQueryHandler(button_handler, pattern='^back$')
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        allow_reentry=True
    )

    dp.add_handler(conv_handler)

    updater.start_polling()
    logger.info("Бот запущен и начал опрос.")
    updater.idle()

if __name__ == '__main__':
    main()
