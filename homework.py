import logging
import os
import time
from http import HTTPStatus
import requests
import telegram
from dotenv import load_dotenv
from requests.exceptions import RequestException

from exceptions import (ResponseError, StatusCodeError, TokenError)

load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_TIME = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

TOKENS = ('PRACTICUM_TOKEN', 'TELEGRAM_TOKEN', 'TELEGRAM_CHAT_ID')

# Я подумал, чтобы лучше выглядело, нужно
# вынести сообщения об ошибках в отдельные переменные.
SEND_MESSAGE_INFO = 'Отправлено сообщение: "{}"'
API_ANSWER_ERROR = ('Ошибка подключения к API: {error}. '
                    'endpoint: {url}, headers: {headers}, params: {params}')
RESPONSE_ERROR = ('Отказ от обслуживания: {error}, key {key}. '
                  'endpoint: {url}, headers: {headers}, params: {params}')
STATUS_CODE_ERROR = ('Ошибка при запросе к API: '
                     'status_code: {status_code}, endpoint: {url}, '
                     'headers: {headers}, params: {params}')
UNKNOWN_STATUS_ERROR = 'Неизвестный статус: {}'
CHANGED_STATUS = 'Изменился статус проверки работы "{}". {}'
RESPONSE_NOT_DICT = 'Ответ API не является словарем'
HOMEWORKS_NOT_IN_RESPONSE = 'Отсутствует ключ homeworks'
HOMEWORKS_NOT_LIST = 'Под ключом `homeworks` домашки приходят не в виде списка'
TOKEN_NOT_FOUND = 'Токен {} не найден!'
ERROR_MESSAGE = 'Сбой в работе программы: {}'
HOMEWORK_NAME_NOT_FOUND = 'Не найден ключ `homework_name`!'
SEND_MESSAGE_ERROR = 'Ошибка при отправке сообщения: {}'
TOKEN_ERROR = 'Ошибка в токенах!'


def send_message(bot, message):
    """Отправка сообщения об изменении статуса."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logging.info(SEND_MESSAGE_INFO.format(message))
    except message.FailToSend:
        raise ConnectionError('Ошибка отправки')


def get_api_answer(current_timestamp):
    """Запрос к эндпоинту API-сервиса."""
# Я сделал это словарём, так как в этой функции
# эти параметры много где используются. DRY!
    parameters = dict(
        url=ENDPOINT,
        headers=HEADERS,
        params={'from_date': current_timestamp})
    try:
        response = requests.get(**parameters)
    except RequestException as error:
        raise ConnectionError(
            API_ANSWER_ERROR.format(error=error, **parameters))
    status_code = response.status_code
    if status_code != HTTPStatus.OK:
        raise StatusCodeError(
            STATUS_CODE_ERROR.format(status_code=status_code, **parameters))
    response_json = response.json()
    for key in ('error', 'code'):
        if key in response_json:
            raise ResponseError(
                RESPONSE_ERROR.format(
                    error=response_json[key],
                    key=key,
                    **parameters))
    return response_json


def check_response(response):
    """Проверка ответа API на корректность."""
    if isinstance(response, dict) is not True:
        raise TypeError(RESPONSE_NOT_DICT)
    if response.get('homeworks', None) is None:
        raise KeyError(HOMEWORKS_NOT_IN_RESPONSE)
    if isinstance(response['homeworks'], list) is not True:
        raise TypeError(HOMEWORKS_NOT_LIST)
    return response.get('homeworks')


def parse_status(homework):
    """Извлечение из информации о домашней работе статуса этой работы."""
    if homework.get('homework_name', None) is None:
        raise KeyError(HOMEWORK_NAME_NOT_FOUND)
    if homework['status'] not in VERDICTS:
        raise ValueError(UNKNOWN_STATUS_ERROR.format(homework['status']))
    return (CHANGED_STATUS.format(
        homework['homework_name'],
        VERDICTS.get(homework['status'])))


def check_tokens():
    """Проверка наличия токенов."""
    flag = True
    for name in TOKENS:
        if globals()[name] is None:
            logging.critical(TOKEN_NOT_FOUND.format(name))
            flag = False
    return flag


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        raise TokenError(TOKEN_ERROR)
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)
            if homeworks:
                send_message(bot, parse_status(homeworks[0]))
            timestamp = response.get('current_date', timestamp)
        except Exception as error:
            message = ERROR_MESSAGE.format(error)
            logging.exception(message)
            try:
                bot.send_message(TELEGRAM_CHAT_ID, message)
            except Exception as error:
                logging.exception(SEND_MESSAGE_ERROR.format(error))
        finally:
            time.sleep(RETRY_TIME)


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG,
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(__file__ + '.log', encoding='UTF-8')],
        format=(
            '%(asctime)s, %(levelname)s, %(funcName)s, %(lineno)d, %(message)s'
        ))
    main()
