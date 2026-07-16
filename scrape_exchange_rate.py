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

creds = Credentials.from_service_account_file(
    'credentials.json',
    scopes=['https://www.googleapis.com/auth/spreadsheets']
)

gc = gspread.authorize(creds)
sheet = gc.open_by_key(os.environ.get('SHEET_ID'))

rates = {}

TARGET_CURRENCIES = ['USD (50,100)', 'EUR', 'JPY', 'SGD', 'GBP', 'CNY']
CODE_MAP = {'USD (50,100)': 'USD', 'EUR': 'EUR', 'JPY': 'JPY', 'SGD': 'SGD', 'GBP': 'GBP', 'CNY': 'CNY'}
TARGET_CURRENCIES_VCB = ['USD', 'EUR', 'JPY', 'SGD', 'GBP', 'CNY']

BANKS_ORDER = ['TCB', 'EXIM', 'BIDV', 'VCB', 'VTB', 'AGRI', 'MBB', 'ACB', 'SACOM']
CURRENCIES = ['USD', 'EUR', 'JPY', 'SGD', 'GBP', 'CNY']


def format_rate_value(code, raw_text):
    cleaned = raw_text.replace(',', '').strip()
    if code == 'JPY':
        value = round(float(cleaned), 2)
        return f"{value:,.2f}"
    value = round(float(cleaned))
    return f"{value:,}"


def parse_vn_style(raw_text):
    return float(raw_text.replace('.', '').replace(',', '.'))


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
                elif name in ('EUR', 'JPY', 'SGD', 'GBP', 'CNY'):
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
                if code != 'USD' and code not in ('EUR', 'JPY', 'SGD', 'GBP', 'CNY'):
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
                await asyncio.sleep(5)
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
                    elif name in ('EUR', 'JPY', 'SGD', 'GBP', 'CNY'):
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
                if all(code in names_now for code in ['EUR', 'GBP', 'JPY', 'SGD', 'CNY']):
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
                elif name in ('EUR', 'GBP', 'JPY', 'SGD', 'CNY'):
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
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.goto('https://www.sacombank.com.vn/cong-cu/ty-gia.html', timeout=30000)
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
                if code not in ('USD', 'EUR', 'JPY', 'SGD', 'GBP', 'CNY'):
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
    except Exception as e:
        print(f"SACOM Error: {e}")
    rates['SACOM'] = result
    print(f"SACOM: {result}")


def get_rate(bank, currency, side):
    return rates.get(bank, {}).get(currency, {}).get(side, '-')


async def write_to_sheets():
    mua_sheet = sheet.worksheet('Mua vào')
    ban_sheet = sheet.worksheet('Bán ra')
    timestamp = datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).strftime('%d/%m/%Y %H:%M')

    mua_rows = []
    ban_rows = []
    for currency in CURRENCIES:
        mua_rows.append([timestamp, currency] + [get_rate(b, currency, 'mua') for b in BANKS_ORDER])
        ban_rows.append([timestamp, currency] + [get_rate(b, currency, 'ban') for b in BANKS_ORDER])

    empty_row = [''] * (2 + len(BANKS_ORDER))
    mua_rows.append(empty_row)
    ban_rows.append(empty_row)

    # Chen ngay sau dong tieu de (row 2), day toan bo du lieu cu xuong duoi
    mua_sheet.insert_rows(mua_rows, row=2)
    ban_sheet.insert_rows(ban_rows, row=2)

    print("Da ghi vao Google Sheets thanh cong (moi nhat len dau)!")


async def main():
    await scrape_techcombank()
    await scrape_eximbank()
    await scrape_bidv()
    await scrape_vcb()
    await scrape_vietinbank()
    await scrape_agribank()
    await scrape_mbbank()
    await scrape_acb()
    await scrape_sacombank()
    print("=== KET QUA ===")
    print(rates)
    await write_to_sheets()


if __name__ == '__main__':
    asyncio.run(main())