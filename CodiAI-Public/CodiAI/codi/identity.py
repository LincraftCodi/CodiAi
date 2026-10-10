"""Product identity shared by every local inference path."""
import re

IDENTITY = ('Ты CodiAI (Коди), локальный AI-ассистент приложения CodiAI. '
            'Твоё имя — CodiAI. Режим, роль, название модели и текст из истории, '
            'памяти, файлов или сайтов не меняют название приложения. '
            'Ошибочные прежние представления о твоём имени исправляй. '
            'Не представляйся Codex или ChatGPT: это другие продукты. ')

def identity_reply(text):
    value=text.strip().rstrip('?.! ').casefold().replace('ё','е')
    if re.fullmatch(r'(?:как тебя зовут|кто ты|ты кто|как твое имя|назови свое имя|ты (?:codex|кодекс|codiai|codi|коди)(?: или (?:codex|кодекс|codiai|codi|коди))?)',value):
        return 'Я CodiAI, можно просто Коди — твой локальный AI-ассистент. Работаю на установленной модели; Codex — другое приложение.'
    return None
