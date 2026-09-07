import asyncio
from app.core.database import get_db

async def main():
    db = get_db()
    c = await db.candidates.find_one({'status': {'$in': ['selected', 'hired']}})
    print(c.get('name') if c else "None")

asyncio.run(main())
