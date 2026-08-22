import asyncio
from scrape_exchange_rate import scrape_techcombank_extra, generate_tcb_extra_image

async def test():
    await scrape_techcombank_extra()
    await generate_tcb_extra_image()

asyncio.run(test())