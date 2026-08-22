import asyncio
from scrape_exchange_rate import scrape_techcombank_extra, tcb_extra_rates

async def test():
    await scrape_techcombank_extra()

asyncio.run(test())