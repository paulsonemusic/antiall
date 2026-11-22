import os
import re
import time
import unicodedata
import requests

TOKEN = os.environ.get('BOT_TOKEN', '').strip()
if not TOKEN:
    raise SystemExit('Set BOT_TOKEN in hosting environment variables')
API = f'https://api.telegram.org/bot{TOKEN}/'
TEST_MODE = os.getenv('TEST_MODE', 'true').lower() not in ('false', '0', 'no')
WHITELIST = {int(x.strip()) for x in os.getenv('WHITELIST', '').split(',') if x.strip()}
MAT_REPLY = 'Попрошу не использовать ненормативную лексику в переписке со мной'
LAUGH_REPLY = 'нельзя смеяться 👽, только в гс'
MAT = re.compile(r'\b(?:бля(?:д[а-я]*|ть|ха)?|(?:[а-я]*)(?:хуй|ху[еяию]|пизд|еба|ебл|заеб|наеб|уеб|выеб)[а-я]*|сука|суки|сукой|мудак[а-я]*|мудил[а-я]*)\b')
LAUGH = re.compile(r'(?<![а-яa-z])а?х[апсв]+(?:х[апсв]+)*а*(?![а-яa-z])')
REPLACEMENTS = str.maketrans({'a':'а','x':'х','c':'с','e':'е','o':'о','p':'р','y':'у','k':'к','0':'о','ё':'е','3':'з'})
EXCEPTIONS = {'худой','худеть','художник','учеба','учебный','учебник','хлеб','хлеба','хлебом','страхую','страхуем','страхует','страхуешь','бляха','бляхой','гребля','греблей','потребление','колебание'}

def normalize(text):
    text = unicodedata.normalize('NFKC', text).lower().translate(REPLACEMENTS)
    text = re.sub(r'[\u200b-\u200f\ufeff]', '', text)
    return re.sub(r'(.)\1{2,}', r'\1\1', text)

def violation(text):
    text = normalize(text)
    compact = re.sub(r'(?<=[а-я])[*._\-]+(?=[а-я])', '', text)
    for sample in (text, compact):
        if any(m.group() not in EXCEPTIONS and not m.group().startswith(('учеб','страху','колеб','потребл','гребл','хлеб')) for m in MAT.finditer(sample)):
            return MAT_REPLY
    if LAUGH.search(text):
        return LAUGH_REPLY
    return None

def api(method, **data):
    try:
        response = requests.post(API + method, json=data, timeout=45).json()
    except (requests.RequestException, ValueError):
        raise RuntimeError('Network or invalid response') from None
    if not response.get('ok'):
        raise RuntimeError(f'{method}: Telegram error {response.get("error_code")}')
    return response['result']

connections = {}

def handle(message):
    cid = message['business_connection_id']
    sender = message.get('from', {})
    if not sender or sender.get('is_bot') or message.get('sender_business_bot') or message.get('voice'):
        return
    if cid not in connections:
        connections[cid] = api('getBusinessConnection', business_connection_id=cid)
    connection = connections[cid]
    if not connection.get('is_enabled') or sender['id'] == connection['user']['id'] or sender['id'] in WHITELIST:
        return
    reply = violation(message.get('text') or message.get('caption') or '')
    if not reply:
        return
    if TEST_MODE:
        print('TEST: filter matched', flush=True)
        return
    api('deleteBusinessMessages', business_connection_id=cid, message_ids=[message['message_id']])
    api('sendMessage', business_connection_id=cid, chat_id=message['chat']['id'], text=reply)
    print('Message removed', flush=True)

def main():
    offset = 0
    print(f'Bot started. TEST_MODE={TEST_MODE}', flush=True)
    while True:
        try:
            updates = api('getUpdates', offset=offset, timeout=30, allowed_updates=['business_connection','business_message','edited_business_message'])
            for update in updates:
                offset = update['update_id'] + 1
                try:
                    if 'business_connection' in update:
                        c = update['business_connection']; connections[c['id']] = c
                    for key in ('business_message','edited_business_message'):
                        if key in update:
                            handle(update[key])
                except Exception as e:
                    print('Update error:', str(e) if isinstance(e, RuntimeError) else type(e).__name__, flush=True)
        except Exception as e:
            print('Polling error:', str(e) if isinstance(e, RuntimeError) else type(e).__name__, flush=True)
            time.sleep(5)

if __name__ == '__main__':
    main()
