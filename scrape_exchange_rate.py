from dotenv import load_dotenv
load_dotenv()

import gspread
from google.oauth2.service_account import Credentials
import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo
from playwright.async_api import async_playwright
import asyncio
from PIL import Image, ImageDraw, ImageFont
import base64
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders

creds = Credentials.from_service_account_file(
    'credentials.json',
    scopes=['https://www.googleapis.com/auth/spreadsheets']
)

gc = gspread.authorize(creds)
sheet = gc.open_by_key(os.environ.get('SHEET_ID'))

rates = {}

TARGET_CURRENCIES = ['USD (50,100)', 'EUR', 'JPY', 'SGD', 'GBP', 'CNY', 'AUD', 'CAD']
CODE_MAP = {'USD (50,100)': 'USD', 'EUR': 'EUR', 'JPY': 'JPY', 'SGD': 'SGD', 'GBP': 'GBP', 'CNY': 'CNY', 'AUD': 'AUD', 'CAD': 'CAD'}
TARGET_CURRENCIES_VCB = ['USD', 'EUR', 'JPY', 'SGD', 'GBP', 'CNY', 'AUD', 'CAD']

BANKS_ORDER = ['TCB', 'EXIM', 'BIDV', 'VCB', 'AGRI', 'MBB', 'ACB', 'SACOM']
CURRENCIES = ['USD', 'EUR', 'JPY', 'SGD', 'GBP', 'CNY', 'AUD', 'CAD']

# Danh sach mo rong cho bang rieng chi TCB (co ca tien mat)
TCB_EXTRA_LIST = ['USD (50,100)', 'AUD', 'CAD', 'SGD', 'EUR', 'GBP', 'JPY', 'KRW', 'NZD']
TCB_EXTRA_CODE_MAP = {'USD (50,100)': 'USD'}
TCB_EXTRA_DISPLAY_ORDER = ['USD', 'AUD', 'CAD', 'SGD', 'EUR', 'GBP', 'JPY', 'KRW', 'NZD']

tcb_extra_rates = {}


def format_rate_value(code, raw_text):
    cleaned = raw_text.replace(',', '').strip()
    if code == 'JPY':
        value = round(float(cleaned), 2)
        return f"{value:,.2f}"
    value = round(float(cleaned))
    return f"{value:,}"


def parse_vn_style(raw_text):
    return float(raw_text.replace('.', '').replace(',', '.'))


def format_tcb_value(currency, raw):
    if raw == '-' or raw is None or raw == '':
        return '-'
    try:
        val = float(str(raw).replace(',', ''))
    except Exception:
        return str(raw)
    if currency in ('JPY', 'KRW'):
        return f"{val:,.2f}"
    return f"{round(val):,}"


async def scrape_techcombank():
    result = {}
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.goto('https://techcombank.com/cong-cu-tien-ich/ty-gia', timeout=30000)
            await page.wait_for_selector('.data-content__item', state='attached', timeout=15000)
            await page.wait_for_timeout(1500)
            for _ in range(10):
                await page.mouse.wheel(0, 500)
                await page.wait_for_timeout(300)
            await page.wait_for_timeout(1000)
            rows = await page.query_selector_all('.exchange-rate__table-records:not(.table-header)')
            print(f"TCB: tim thay {len(rows)} dong")
            for row in rows:
                code_el = await row.query_selector('.table__first-column.first-column p')
                if not code_el:
                    continue
                code = (await code_el.text_content()).strip()
                if code not in TARGET_CURRENCIES:
                    continue
                items = await row.query_selector_all('.data-content__item p')
                if len(items) >= 4:
                    mua_ck = (await items[1].text_content()).strip()
                    ban_ck = (await items[3].text_content()).strip()
                    final_code = CODE_MAP[code]
                    result[final_code] = {'mua': mua_ck, 'ban': ban_ck}
            await browser.close()
    except Exception as e:
        print(f"TCB Error: {e}")
    rates['TCB'] = result
    print(f"TCB: {result}")


async def scrape_techcombank_extra():
    """Scrape TCB voi danh sach tien te mo rong, co ca 4 cot (mua/ban x tien mat/CK)"""
    result = {}
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.goto('https://techcombank.com/cong-cu-tien-ich/ty-gia', timeout=30000)
            await page.wait_for_selector('.data-content__item', state='attached', timeout=15000)
            await page.wait_for_timeout(1500)
            for _ in range(10):
                await page.mouse.wheel(0, 500)
                await page.wait_for_timeout(300)
            await page.wait_for_timeout(1000)
            rows = await page.query_selector_all('.exchange-rate__table-records:not(.table-header)')
            print(f"TCB EXTRA: tim thay {len(rows)} dong")
            for row in rows:
                code_el = await row.query_selector('.table__first-column.first-column p')
                if not code_el:
                    continue
                code = (await code_el.text_content()).strip()
                if code not in TCB_EXTRA_LIST:
                    continue
                items = await row.query_selector_all('.data-content__item p')
                if len(items) >= 4:
                    mua_tm = (await items[0].text_content()).strip()
                    mua_ck = (await items[1].text_content()).strip()
                    ban_tm = (await items[2].text_content()).strip()
                    ban_ck = (await items[3].text_content()).strip()
                    final_code = TCB_EXTRA_CODE_MAP.get(code, code)
                    result[final_code] = {
                        'mua_ck': mua_ck,
                        'mua_tm': mua_tm,
                        'ban_ck': ban_ck,
                        'ban_tm': ban_tm,
                    }
            await browser.close()
    except Exception as e:
        print(f"TCB EXTRA Error: {e}")
    global tcb_extra_rates
    tcb_extra_rates = result
    print(f"TCB EXTRA: {result}")


async def scrape_eximbank():
    result = {}
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.goto('https://eximbank.com.vn/bang-ty-gia', timeout=30000)
            await page.wait_for_selector('table tbody tr', state='attached', timeout=15000)
            await page.wait_for_timeout(1000)
            try:
                await page.click('text=Xem tất cả', timeout=5000)
                await page.wait_for_timeout(1000)
            except Exception:
                pass
            rows = await page.query_selector_all('table tbody tr')
            print(f"EXIM: tim thay {len(rows)} dong")
            for row in rows:
                name_el = await row.query_selector('td:first-child p.font-bold')
                if not name_el:
                    continue
                name = (await name_el.text_content()).strip()
                cells = await row.query_selector_all('td')
                if len(cells) < 5:
                    continue
                mua_ck_el = await cells[2].query_selector('p')
                ban_ck_el = await cells[4].query_selector('p')
                if not mua_ck_el or not ban_ck_el:
                    continue
                mua_ck = (await mua_ck_el.text_content()).strip()
                ban_ck = (await ban_ck_el.text_content()).strip()
                if name == 'USD (50-100)':
                    result['USD'] = {'mua': mua_ck, 'ban': ban_ck}
                elif name in ('EUR', 'JPY', 'SGD', 'GBP', 'CNY', 'AUD', 'CAD'):
                    result[name] = {'mua': mua_ck, 'ban': ban_ck}
            await browser.close()
    except Exception as e:
        print(f"EXIM Error: {e}")
    rates['EXIM'] = result
    print(f"EXIM: {result}")


async def scrape_bidv():
    result = {}
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.goto('https://bidv.com.vn/vn/ty-gia-ngoai-te', timeout=30000)
            await page.wait_for_selector('table.table-reponsive tbody tr', state='attached', timeout=15000)
            await page.wait_for_timeout(1000)
            rows = await page.query_selector_all('table.table-reponsive tbody tr')
            print(f"BIDV: tim thay {len(rows)} dong")
            for row in rows:
                cells = await row.query_selector_all('td')
                if len(cells) < 5:
                    continue
                code_el = await cells[0].query_selector('span.ng-binding')
                if not code_el:
                    continue
                code = (await code_el.text_content()).strip()
                if code != 'USD' and code not in ('EUR', 'JPY', 'SGD', 'GBP', 'CNY', 'AUD', 'CAD'):
                    continue
                mua_ck_el = await cells[3].query_selector('span.ng-binding')
                ban_el = await cells[4].query_selector('span.ng-binding')
                if not mua_ck_el or not ban_el:
                    continue
                mua_ck = (await mua_ck_el.text_content()).strip()
                ban = (await ban_el.text_content()).strip()
                result[code] = {'mua': mua_ck, 'ban': ban}
            await browser.close()
    except Exception as e:
        print(f"BIDV Error: {e}")
    rates['BIDV'] = result
    print(f"BIDV: {result}")


async def scrape_vcb():
    result = {}
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=False,
                    channel='chrome',
                    args=['--disable-blink-features=AutomationControlled']
                )
                context = await browser.new_context(
                    user_agent=(
                        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                        '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
                    ),
                    viewport={'width': 1366, 'height': 768},
                    locale='vi-VN',
                    extra_http_headers={
                        'Accept-Language': 'vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7'
                    }
                )
                await context.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
                )
                page = await context.new_page()
                await page.goto(
                    'https://vietcombank.com.vn/vi-VN/KHCN/Cong-cu-Tien-ich/Ty-gia',
                    timeout=30000,
                    wait_until='domcontentloaded'
                )
                await page.wait_for_selector('table.table-responsive tbody tr', state='attached', timeout=15000)
                await page.wait_for_timeout(1000)
                rows = await page.query_selector_all('table.table-responsive tbody tr')
                print(f"VCB: tim thay {len(rows)} dong")
                for row in rows:
                    cells = await row.query_selector_all('td')
                    if len(cells) < 5:
                        continue
                    code = (await cells[0].text_content()).strip()
                    if code not in TARGET_CURRENCIES_VCB:
                        continue
                    mua_ck_raw = (await cells[3].text_content()).strip()
                    ban_raw = (await cells[4].text_content()).strip()
                    result[code] = {
                        'mua': format_rate_value(code, mua_ck_raw),
                        'ban': format_rate_value(code, ban_raw)
                    }
                await browser.close()
            break
        except Exception as e:
            print(f"VCB Error (lan {attempt}/{max_retries}): {e}")
            if attempt < max_retries:
                await asyncio.sleep(3)
    rates['VCB'] = result
    print(f"VCB: {result}")


async def scrape_vietinbank():
    result = {}
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=False,
                    channel='chrome',
                    args=['--disable-blink-features=AutomationControlled']
                )
                context = await browser.new_context(
                    user_agent=(
                        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                        '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
                    ),
                    viewport={'width': 1366, 'height': 768},
                    locale='vi-VN',
                    extra_http_headers={
                        'Accept-Language': 'vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7'
                    }
                )
                await context.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
                )
                page = await context.new_page()
                await page.goto(
                    'https://vietinbank.vn/vi/ca-nhan/ty-gia-khcn',
                    timeout=30000,
                    wait_until='domcontentloaded'
                )
                await page.wait_for_selector('table tbody tr td img', state='attached', timeout=20000)
                await page.wait_for_timeout(1500)
                tables = await page.query_selector_all('table')
                if not tables:
                    raise Exception("Khong tim thay table nao tren trang")
                main_table = tables[0]
                rows = await main_table.query_selector_all('tbody tr')
                print(f"VTB: tim thay {len(rows)} dong")
                for row in rows:
                    flag_el = await row.query_selector('td:first-child img')
                    if not flag_el:
                        continue
                    code_el = await row.query_selector('td:first-child')
                    code = (await code_el.text_content()).strip()
                    if code not in TARGET_CURRENCIES_VCB:
                        continue
                    cells = await row.query_selector_all('td')
                    if len(cells) < 4:
                        continue
                    mua_ck_raw = (await cells[2].text_content()).strip()
                    ban_raw = (await cells[3].text_content()).strip()
                    mua_val = parse_vn_style(mua_ck_raw)
                    ban_val = parse_vn_style(ban_raw)
                    if code == 'JPY':
                        result[code] = {'mua': f"{mua_val:,.2f}", 'ban': f"{ban_val:,.2f}"}
                    else:
                        result[code] = {'mua': f"{round(mua_val):,}", 'ban': f"{round(ban_val):,}"}
                await browser.close()
            break
        except Exception as e:
            print(f"VTB Error (lan {attempt}/{max_retries}): {e}")
            if attempt < max_retries:
                await asyncio.sleep(10)
    rates['VTB'] = result
    print(f"VTB: {result}")


async def scrape_agribank():
    result = {}
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.goto('https://agribank.com.vn/vn/ty-gia', timeout=30000)
            await page.wait_for_selector('table.table-bordered tbody tr', state='attached', timeout=15000)
            await page.wait_for_timeout(1000)
            rows = await page.query_selector_all('table.table-bordered tbody tr')
            print(f"AGRI: tim thay {len(rows)} dong")
            for row in rows:
                cells = await row.query_selector_all('td')
                if len(cells) < 4:
                    continue
                code = (await cells[0].text_content()).strip()
                if code not in TARGET_CURRENCIES_VCB:
                    continue
                mua_ck_raw = (await cells[2].text_content()).strip()
                ban_raw = (await cells[3].text_content()).strip()
                result[code] = {
                    'mua': format_rate_value(code, mua_ck_raw),
                    'ban': format_rate_value(code, ban_raw)
                }
            await browser.close()
    except Exception as e:
        print(f"AGRI Error: {e}")
    rates['AGRI'] = result
    print(f"AGRI: {result}")


async def scrape_mbbank():
    result = {}
    max_retries = 2
    for attempt in range(1, max_retries + 1):
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=False,
                    channel='chrome',
                    args=['--disable-blink-features=AutomationControlled']
                )
                context = await browser.new_context(
                    user_agent=(
                        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                        '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
                    ),
                    viewport={'width': 1366, 'height': 768},
                    locale='vi-VN',
                    extra_http_headers={
                        'Accept-Language': 'vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7'
                    }
                )
                await context.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
                )
                page = await context.new_page()
                await page.goto(
                    'https://www.mbbank.com.vn/ExchangeRate',
                    timeout=30000,
                    wait_until='domcontentloaded'
                )
                await page.wait_for_selector('table.table-fee tbody tr td', state='attached', timeout=20000)
                await page.wait_for_timeout(1500)
                rows = await page.query_selector_all('table.table-fee tbody tr')
                print(f"MBB: tim thay {len(rows)} dong")
                for row in rows:
                    cells = await row.query_selector_all('td')
                    if len(cells) < 5:
                        continue
                    name = (await cells[0].text_content()).strip()
                    if name == 'USD (USD 50-100)':
                        code = 'USD'
                    elif name in ('EUR', 'JPY', 'SGD', 'GBP', 'CNY', 'AUD', 'CAD'):
                        code = name
                    else:
                        continue
                    mua_ck_raw = (await cells[2].text_content()).strip()
                    ban_ck_raw = (await cells[4].text_content()).strip()
                    if mua_ck_raw == '-' or ban_ck_raw == '-':
                        continue
                    result[code] = {
                        'mua': format_rate_value(code, mua_ck_raw),
                        'ban': format_rate_value(code, ban_ck_raw)
                    }
                await browser.close()
            break
        except Exception as e:
            print(f"MBB Error (lan {attempt}/{max_retries}): {e}")
            if attempt < max_retries:
                await asyncio.sleep(3)
    rates['MBB'] = result
    print(f"MBB: {result}")


async def scrape_acb():
    result = {}
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.goto('https://acb.com.vn/ty-gia-hoi-doai', timeout=30000)
            await page.wait_for_selector(
                '.list-ty-gia.hide-mb .item.dl-grid-md-5:not(.item-heading)',
                state='attached',
                timeout=15000
            )
            await page.wait_for_timeout(1000)
            try:
                cookie_btn = await page.query_selector(
                    '.cookie-container button, .cookie-container a.btn, '
                    '.cookie-container [class*="accept"], .cookie-container [class*="close"]'
                )
                if cookie_btn:
                    await cookie_btn.evaluate('el => el.click()')
                    await page.wait_for_timeout(500)
            except Exception:
                pass
            for _ in range(8):
                names_now = await page.eval_on_selector_all(
                    '.list-ty-gia.hide-mb .item.dl-grid-md-5:not(.item-heading) h4.title',
                    'els => els.map(e => e.textContent.trim())'
                )
                if all(code in names_now for code in ['EUR', 'GBP', 'JPY', 'SGD', 'CNY', 'AUD', 'CAD']):
                    break
                more_btn = await page.query_selector('a.btn:has-text("Xem thêm")')
                if not more_btn:
                    break
                await more_btn.evaluate('el => el.click()')
                await page.wait_for_timeout(800)
            rows = await page.query_selector_all(
                '.list-ty-gia.hide-mb .item.dl-grid-md-5:not(.item-heading)'
            )
            print(f"ACB: tim thay {len(rows)} dong")
            for row in rows:
                cols = await row.query_selector_all('.item-col')
                if len(cols) < 5:
                    continue
                name_el = await cols[0].query_selector('h4.title')
                if not name_el:
                    continue
                name = (await name_el.text_content()).strip()
                if name == 'USD (50,100)':
                    code = 'USD'
                elif name in ('EUR', 'GBP', 'JPY', 'SGD', 'CNY', 'AUD', 'CAD'):
                    code = name
                else:
                    continue
                mua_ck_raw = (await cols[2].text_content()).strip()
                ban_ck_raw = (await cols[4].text_content()).strip()
                if not mua_ck_raw or not ban_ck_raw:
                    continue
                result[code] = {
                    'mua': format_rate_value(code, mua_ck_raw),
                    'ban': format_rate_value(code, ban_ck_raw)
                }
            await browser.close()
    except Exception as e:
        print(f"ACB Error: {e}")
    rates['ACB'] = result
    print(f"ACB: {result}")


async def scrape_sacombank():
    result = {}
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch()
                page = await browser.new_page()
                await page.goto(
                    'https://www.sacombank.com.vn/cong-cu/ty-gia.html',
                    timeout=40000,
                    wait_until='domcontentloaded'
                )
                await page.wait_for_selector('table.exchange-rate__body-table tbody tr.body-row', state='attached', timeout=15000)
                await page.wait_for_timeout(1000)
                try:
                    load_all_btn = await page.query_selector('.exchange-rate__body-load-all-btn')
                    if load_all_btn:
                        await load_all_btn.evaluate('el => el.click()')
                        await page.wait_for_timeout(1000)
                except Exception:
                    pass
                rows = await page.query_selector_all(
                    'table.exchange-rate__body-table[data-type="currency"] tbody tr.body-row'
                )
                print(f"SACOM: tim thay {len(rows)} dong")
                for row in rows:
                    cells = await row.query_selector_all('td.body-col')
                    if len(cells) < 5:
                        continue
                    code_el = await cells[0].query_selector('span')
                    if not code_el:
                        continue
                    code = (await code_el.text_content()).strip()
                    if code not in ('USD', 'EUR', 'JPY', 'SGD', 'GBP', 'CNY', 'AUD', 'CAD'):
                        continue
                    mua_ck_raw = (await cells[2].text_content()).strip()
                    ban_ck_raw = (await cells[4].text_content()).strip()
                    if not mua_ck_raw or not ban_ck_raw:
                        continue
                    mua_val = parse_vn_style(mua_ck_raw)
                    ban_val = parse_vn_style(ban_ck_raw)
                    if code == 'JPY':
                        result[code] = {'mua': f"{mua_val:,.2f}", 'ban': f"{ban_val:,.2f}"}
                    else:
                        result[code] = {'mua': f"{round(mua_val):,}", 'ban': f"{round(ban_val):,}"}
                await browser.close()
            break
        except Exception as e:
            print(f"SACOM Error (lan {attempt}/{max_retries}): {e}")
            if attempt < max_retries:
                await asyncio.sleep(5)
    rates['SACOM'] = result
    print(f"SACOM: {result}")


def get_rate(bank, currency, side):
    return rates.get(bank, {}).get(currency, {}).get(side, '-')


def to_float(bank, currency, side):
    raw = get_rate(bank, currency, side)
    if raw in ('-', ''):
        return None
    try:
        return float(raw.replace(',', ''))
    except Exception:
        return None


def get_ranking(currency, side):
    vals = []
    for bank in BANKS_ORDER:
        v = to_float(bank, currency, side)
        if v is not None:
            vals.append((bank, v))
    if not vals:
        return None, None, None
    reverse = (side == 'mua')
    vals_sorted = sorted(vals, key=lambda x: x[1], reverse=reverse)
    best_bank, best_value = vals_sorted[0]
    tcb_rank = None
    for i, (b, v) in enumerate(vals_sorted, start=1):
        if b == 'TCB':
            tcb_rank = i
            break
    return tcb_rank, best_bank, best_value


def format_display(currency, value):
    if currency == 'JPY':
        return f"{value:,.2f}"
    return f"{round(value):,}"


async def write_to_sheets():
    mua_sheet = sheet.worksheet('Mua vào')
    ban_sheet = sheet.worksheet('Bán ra')
    timestamp = datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).strftime('%d/%m/%Y %H:%M')

    mua_rows = []
    ban_rows = []
    for currency in CURRENCIES:
        tcb_rank_mua, _, _ = get_ranking(currency, 'mua')
        tcb_rank_ban, _, _ = get_ranking(currency, 'ban')

        mua_row = [timestamp, currency] + [get_rate(b, currency, 'mua') for b in BANKS_ORDER]
        mua_row.append(f"#{tcb_rank_mua}" if tcb_rank_mua else '-')
        mua_rows.append(mua_row)

        ban_row = [timestamp, currency] + [get_rate(b, currency, 'ban') for b in BANKS_ORDER]
        ban_row.append(f"#{tcb_rank_ban}" if tcb_rank_ban else '-')
        ban_rows.append(ban_row)

    empty_row = [''] * (3 + len(BANKS_ORDER))
    mua_rows.append(empty_row)
    ban_rows.append(empty_row)

    mua_sheet.insert_rows(mua_rows, row=2)
    ban_sheet.insert_rows(ban_rows, row=2)

    print("Da ghi vao Google Sheets thanh cong (moi nhat len dau, co TCB Rating)!")


def load_font(size, bold=False):
    candidates = (
        [
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/seguisb.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        ] if bold
        else [
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/segoeui.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ]
    )
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def generate_image(side):
    label = "Mua vào" if side == 'mua' else "Bán ra"
    cols = ['Loại tiền'] + BANKS_ORDER + ['TCB Rating']
    col_widths = [95] + [100] * len(BANKS_ORDER) + [95]

    row_height = 48
    header_height = 55
    title_height = 80
    footer_height = 110
    padding = 25

    width = sum(col_widths) + padding * 2
    height = title_height + header_height + row_height * len(CURRENCIES) + footer_height + padding * 2

    img = Image.new('RGB', (width, height), 'white')
    draw = ImageDraw.Draw(img)

    font_title = load_font(24, bold=True)
    font_time = load_font(13)
    font_header = load_font(14, bold=True)
    font_cell = load_font(14)
    font_cell_bold = load_font(14, bold=True)
    font_box_label = load_font(12, bold=True)
    font_box_value = load_font(13, bold=True)

    timestamp = datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).strftime('%H:%M - %d/%m/%Y')

    draw.text((padding, 15), f"So sánh tỷ giá {label.lower()} giữa các ngân hàng", font=font_title, fill=(25, 25, 60))
    draw.text((padding, 48), timestamp, font=font_time, fill=(130, 130, 130))

    y = title_height
    x = padding

    draw.rectangle([x, y, x + sum(col_widths), y + header_height], fill=(230, 232, 245))
    cx = x
    for i, col_name in enumerate(cols):
        draw.text((cx + 8, y + 17), col_name, font=font_header, fill=(30, 30, 90))
        cx += col_widths[i]
    y += header_height

    for currency in CURRENCIES:
        tcb_rank, best_bank, best_value = get_ranking(currency, side)
        cx = x
        draw.line([(x, y), (x + sum(col_widths), y)], fill=(225, 225, 225))

        draw.text((cx + 8, y + 14), currency, font=font_cell_bold, fill=(20, 20, 20))
        cx += col_widths[0]

        for i, bank in enumerate(BANKS_ORDER):
            val = get_rate(bank, currency, side)
            is_best = (bank == best_bank)
            color = (0, 110, 200) if is_best else (40, 40, 40)
            font = font_cell_bold if is_best else font_cell
            draw.text((cx + 8, y + 14), str(val), font=font, fill=color)
            cx += col_widths[i + 1]

        rank_text = f"#{tcb_rank}" if tcb_rank else '-'
        rank_color = (0, 150, 60) if tcb_rank == 1 else (200, 60, 60) if tcb_rank else (150, 150, 150)
        draw.text((cx + 8, y + 14), rank_text, font=font_cell_bold, fill=rank_color)

        y += row_height

    y += 15
    draw.text((padding, y), f"Tỷ giá {label.lower()} tốt nhất:", font=load_font(15, bold=True), fill=(200, 40, 40))
    y += 28

    box_gap = 12
    box_w = (sum(col_widths) - box_gap * (len(CURRENCIES) - 1)) // len(CURRENCIES)
    box_h = footer_height - 45
    bx = padding

    for currency in CURRENCIES:
        tcb_rank, best_bank, best_value = get_ranking(currency, side)
        draw.rounded_rectangle([bx, y, bx + box_w, y + box_h], radius=8, outline=(200, 60, 60), width=2)
        draw.text((bx + 8, y + 8), currency, font=font_box_label, fill=(200, 60, 60))
        if best_bank:
            value_str = format_display(currency, best_value)
            draw.text((bx + 8, y + 28), f"{best_bank}", font=font_box_value, fill=(30, 30, 30))
            draw.text((bx + 8, y + 46), value_str, font=font_cell, fill=(80, 80, 80))
        bx += box_w + box_gap

    filename = f"ty_gia_{side}.png"
    img.save(filename)

    logo_path = 'logo.jpg'
    if os.path.exists(logo_path):
        try:
            logo = Image.open(logo_path).convert('RGBA')
            logo_height = 40
            ratio = logo_height / logo.height
            logo_resized = logo.resize((int(logo.width * ratio), logo_height))
            logo_x = width - logo_resized.width - 20
            logo_y = 15
            img.paste(logo_resized, (logo_x, logo_y), logo_resized)
        except Exception as e:
            print(f"Khong the chen logo: {e}")

    os.makedirs('outputs', exist_ok=True)
    ts = datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).strftime('%Y%m%d_%H%M')
    filename = f"outputs/ty_gia_{side}_{ts}.jpg"
    img.save(filename, 'JPEG', quality=92)

    latest_filename = f"outputs/latest_{side}.jpg"
    img.save(latest_filename, 'JPEG', quality=92)

    print(f"Da tao anh: {filename}")
    return filename


async def generate_tcb_extra_image():
    today_str = datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).strftime('%d/%m/%Y')
    time_str = datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).strftime('%H:%M')

    logo_uri = ''
    logo_path = os.path.abspath('logo.jpg')
    if os.path.exists(logo_path):
        with open(logo_path, 'rb') as f:
            logo_b64 = base64.b64encode(f.read()).decode('utf-8')
        logo_uri = f"data:image/jpeg;base64,{logo_b64}"

    rows_html = ""
    for i, currency in enumerate(TCB_EXTRA_DISPLAY_ORDER):
        data = tcb_extra_rates.get(currency, {})
        mua_ck = format_tcb_value(currency, data.get('mua_ck', '-'))
        mua_tm = format_tcb_value(currency, data.get('mua_tm', '-'))
        ban_ck = format_tcb_value(currency, data.get('ban_ck', '-'))
        ban_tm = format_tcb_value(currency, data.get('ban_tm', '-'))
        alt_class = 'alt' if i % 2 == 1 else ''
        rows_html += f"""
        <div class="row {alt_class}">
          <div class="currency-tag"><span>{currency}</span></div>
          <div class="value blue">{mua_ck}</div>
          <div class="value dark">{mua_tm if mua_tm != '-' else ''}</div>
          <div class="value blue">{ban_ck}</div>
          <div class="value dark">{ban_tm if ban_tm != '-' else ''}</div>
        </div>
        """

    buildings_html = "".join(
        f'<div class="bld" style="left:{x}px;width:{w}px;height:{h}px;"></div>'
        for x, w, h in [
            (10, 34, 90), (50, 26, 130), (82, 40, 75), (128, 30, 150),
            (164, 22, 100), (192, 46, 120), (244, 28, 85), (278, 36, 145),
            (320, 24, 95), (350, 42, 115),
        ]
    )

    html_content = f"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@400;600;700;800&display=swap" rel="stylesheet">
<style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; font-family: 'Be Vietnam Pro', Arial, sans-serif; }}
    body {{ width: 900px; background: #ffffff; }}

    .header {{ position: relative; height: 190px; overflow: hidden; background: #1a1a1a; }}
    .skyline {{
        position: absolute; left: 0; bottom: 0; width: 420px; height: 190px;
        background: linear-gradient(180deg, #6b6b6b 0%, #2e2e2e 100%); overflow: hidden;
    }}
    .bld {{ position: absolute; bottom: 0; background: rgba(0,0,0,0.35); }}
    .tagline {{
        position: absolute; top: 24px; left: 24px; z-index: 3; color: white;
        font-size: 20px; font-weight: 800; letter-spacing: 1px;
        display: flex; align-items: center; gap: 8px;
    }}
    .tagline .arrow {{
        width: 0; height: 0; border-top: 11px solid transparent;
        border-bottom: 11px solid transparent; border-left: 16px solid #e11d2e;
    }}
    .header-red {{
        position: absolute; right: 0; top: 0; bottom: 0; left: 380px;
        background: linear-gradient(135deg, #e11d2e 0%, #a30d1c 100%);
        clip-path: polygon(12% 0, 100% 0, 100% 100%, 0% 100%);
        display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center;
    }}
    .header-red h1 {{ color: white; font-size: 32px; font-weight: 800; }}
    .header-red .date {{ color: rgba(255,255,255,0.92); font-size: 20px; font-weight: 700; margin-top: 6px; }}

    .subheader {{
        display: flex; align-items: center; justify-content: space-between;
        background: linear-gradient(100deg, #e11d2e 0 46%, #ffffff 46%); padding: 20px 32px;
    }}
    .subheader .label {{ color: white; font-size: 17px; font-weight: 800; line-height: 1.35; }}
    .subheader img {{ height: 40px; }}

    .col-group-header {{ display: flex; }}
    .col-group-header .spacer {{ flex: 0 0 15%; }}
    .col-group-header .grp {{ flex: 1; text-align: center; padding: 12px 0; font-size: 17px; font-weight: 800; color: white; }}
    .col-group-header .grp small {{ display: block; font-size: 12px; font-weight: 600; margin-top: 2px; opacity: 0.9; }}
    .col-group-header .grp.mua {{ background: #1a56db; }}
    .col-group-header .grp.ban {{ background: #e11d2e; }}

    .col-sub-header {{ display: flex; background: #f2f2f2; font-size: 12.5px; font-weight: 700; color: #555; }}
    .col-sub-header .spacer {{ flex: 0 0 15%; }}
    .col-sub-header .c {{ flex: 1; text-align: center; padding: 9px 0; letter-spacing: 0.3px; }}

    .row {{ display: flex; align-items: stretch; height: 60px; border-bottom: 2px solid #ffffff; }}
    .currency-tag {{
        flex: 0 0 15%; background: linear-gradient(120deg, #e11d2e, #c41828);
        display: flex; align-items: center; padding-left: 18px; position: relative;
    }}
    .currency-tag::after {{
        content: ''; position: absolute; right: -22px; top: 0;
        border-top: 30px solid transparent; border-bottom: 30px solid transparent; border-left: 22px solid #e11d2e;
    }}
    .row.alt .currency-tag {{ background: #c7c7c7; }}
    .row.alt .currency-tag::after {{ border-left-color: #c7c7c7; }}
    .currency-tag span {{ color: white; font-size: 18px; font-weight: 800; }}

    .value {{ flex: 1; display: flex; align-items: center; justify-content: center; font-size: 21px; font-weight: 800; background: #ececec; }}
    .row.alt .value {{ background: #dcdcdc; }}
    .value.blue {{ color: #1a56db; }}
    .value.dark {{ color: #1a1a1a; }}

    .footer-note {{
        margin: 18px 32px; padding: 12px 16px; border: 2px solid #e11d2e; border-radius: 6px;
        font-size: 12.5px; color: #333; font-weight: 600; line-height: 1.5;
    }}
    .footer-time {{
        display: flex; justify-content: space-between; align-items: center;
        padding: 0 32px 20px; font-size: 12.5px; color: #888; font-weight: 700;
    }}
</style>
</head>
<body>
    <div class="header">
        <div class="skyline">{buildings_html}</div>
        <div class="tagline"><span class="arrow"></span>BE GREATER</div>
        <div class="header-red">
            <h1>TỶ GIÁ NGOẠI TỆ</h1>
            <div class="date">NGÀY {today_str}</div>
        </div>
    </div>

    <div class="subheader">
        <div class="label">Tỉ giá TCB<br>Ngoại tệ</div>
        <img src="{logo_uri}" />
    </div>

    <div class="col-group-header">
        <div class="spacer"></div>
        <div class="grp mua">TỶ GIÁ MUA<small>(Từ khách hàng)</small></div>
        <div class="grp ban">TỶ GIÁ BÁN<small>(Cho khách hàng)</small></div>
    </div>
    <div class="col-sub-header">
        <div class="spacer"></div>
        <div class="c">MUA CHUYỂN KHOẢN</div>
        <div class="c">MUA TIỀN MẶT</div>
        <div class="c">BÁN CHUYỂN KHOẢN</div>
        <div class="c">BÁN TIỀN MẶT</div>
    </div>

    {rows_html}

    <div class="footer-note">
        LƯU Ý: Tỷ giá có thể thay đổi theo thời điểm giao dịch. Vui lòng liên hệ điểm giao dịch Techcombank gần nhất hoặc tổng đài để được hỗ trợ.
    </div>
    <div class="footer-time">
        <span>Dữ liệu tổng hợp tự động</span>
        <span>Thời gian cập nhật: {time_str} - {today_str}</span>
    </div>
</body>
</html>"""

    html_path = os.path.abspath('tcb_only_temp.html').replace(os.sep, '/')
    with open('tcb_only_temp.html', 'w', encoding='utf-8') as f:
        f.write(html_content)

    os.makedirs('outputs', exist_ok=True)
    ts = datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).strftime('%Y%m%d_%H%M')
    filename = f"outputs/tcb_only_{ts}.jpg"
    latest_filename = "outputs/latest_tcb_only.jpg"

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={'width': 900, 'height': 200})
        await page.goto(f'file:///{html_path}')
        await page.wait_for_timeout(600)
        body = await page.query_selector('body')
        await body.screenshot(path=filename, type='jpeg', quality=92)
        await body.screenshot(path=latest_filename, type='jpeg', quality=92)
        await browser.close()

    try:
        os.remove('tcb_only_temp.html')
    except Exception:
        pass

    print(f"Da tao anh TCB rieng (HTML): {filename}")
    return filename


def send_email_report(attachments):
    email_username = os.environ.get('EMAIL_USERNAME')
    email_password = os.environ.get('EMAIL_PASSWORD')
    email_to = os.environ.get('EMAIL_TO')

    if not email_username or not email_password or not email_to:
        print("Thieu thong tin email trong .env, bo qua buoc gui mail.")
        return

    email_to_list = [e.strip() for e in email_to.split(',') if e.strip()]

    msg = MIMEMultipart()
    msg['From'] = email_username
    msg['To'] = ', '.join(email_to_list)
    msg['Subject'] = f"Ty gia hoi doai cap nhat - {datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).strftime('%H:%M %d/%m/%Y')}"
    msg.attach(MIMEText("Dinh kem la bang ty gia mua vao, ban ra va bang rieng TCB, cap nhat tu dong.", 'plain'))

    for filepath in attachments:
        if not os.path.exists(filepath):
            continue
        with open(filepath, 'rb') as f:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f'attachment; filename={os.path.basename(filepath)}')
        msg.attach(part)

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(email_username, email_password)
        server.sendmail(email_username, email_to_list, msg.as_string())
        server.quit()
        print("Da gui email thanh cong!")
    except Exception as e:
        print(f"Loi gui email: {e}")


async def main():
    await scrape_techcombank()
    await scrape_eximbank()
    await scrape_bidv()
    await scrape_vcb()
    # await scrape_vietinbank()
    await scrape_agribank()
    await scrape_mbbank()
    await scrape_acb()
    await scrape_sacombank()
    await scrape_techcombank_extra()
    print("=== KET QUA ===")
    print(rates)
    await write_to_sheets()
    generate_image('mua')
    generate_image('ban')
    await generate_tcb_extra_image()
    send_email_report([
        'outputs/latest_mua.jpg',
        'outputs/latest_ban.jpg',
        'outputs/latest_tcb_only.jpg',
    ])


if __name__ == '__main__':
    asyncio.run(main())