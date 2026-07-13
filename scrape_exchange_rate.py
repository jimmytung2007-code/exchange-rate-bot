import gspread
from google.oauth2.service_account import Credentials
import json
import os
from datetime import datetime
from playwright.async_api import async_playwright
import asyncio

# Load GCP credentials từ environment variable
credentials_json = os.environ.get('GCP_CREDENTIALS')
creds = Credentials.from_service_account_info(
    json.loads(credentials_json),
    scopes=['https://www.googleapis.com/auth/spreadsheets']
)

# Connect Google Sheets
gc = gspread.authorize(creds)
sheet = gc.open_by_key(os.environ.get('SHEET_ID'))

# Tỷ giá hiện tại (format: {bank_name: {currency: {mua: value, ban: value}}})
rates = {}

async def scrape_techcombank():
    """Scrape TCB"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto('https://techcombank.com/cong-cu-tien-ich/ty-gia', timeout=30000)
        await page.wait_for_selector('table', timeout=10000)
        
        # Parse table - adjust selector based on actual page
        rows = await page.query_selector_all('table tbody tr')
        
        rates['TCB'] = {}
        for row in rows:
            cells = await row.query_selector_all('td')
            if len(cells) >= 3:
                currency = (await cells[0].text_content()).strip()
                mua = (await cells[1].text_content()).strip()
                ban = (await cells[2].text_content()).strip()
                
                if currency in ['USD', 'EUR', 'JPY', 'SGD', 'GBP', 'CNY']:
                    rates['TCB'][currency] = {'mua': mua, 'ban': ban}
        
        await browser.close()

# Tương tự cho các bank khác (EXIM, BIDV, VCB, VTB, AGR, MBB, ACB, SACOM)
# ... (code tương tự)

async def main():
    # Scrape tất cả banks
    await scrape_techcombank()
    # await scrape_exim()
    # ... etc
    
    # Ghi vào Google Sheet
    mua_sheet = sheet.worksheet('Mua vào')
    ban_sheet = sheet.worksheet('Bán ra')
    
    # Format: [Ngày giờ, TCB, EXIM, BIDV, VCB, VTB, AGR, MBB, ACB, SACOM]
    timestamp = datetime.now().strftime('%d/%m/%Y %H:%M')
    
    currencies = ['USD', 'EUR', 'JPY', 'SGD', 'GBP', 'CNY']
    banks = ['TCB', 'EXIM', 'BIDV', 'VCB', 'VTB', 'AGR', 'MBB', 'ACB', 'SACOM']
    
    for currency in currencies:
        mua_row = [f"{timestamp} {currency}"]
        ban_row = [f"{timestamp} {currency}"]
        
        for bank in banks:
            mua_val = rates.get(bank, {}).get(currency, {}).get('mua', '-')
            ban_val = rates.get(bank, {}).get(currency, {}).get('ban', '-')
            mua_row.append(mua_val)
            ban_row.append(ban_val)
        
        mua_sheet.append_row(mua_row)
        ban_sheet.append_row(ban_row)

if __name__ == '__main__':
    asyncio.run(main())
