from app.core.database import get_db
import asyncio

async def main():
    db = get_db()
    candidate = await db.candidates.find_one({'name': {'$regex': 'Shivam', '$options': 'i'}})
    if candidate:
        print(f"ID: {candidate['id']}")
    else:
        print("Not found")

if __name__ == "__main__":
    asyncio.run(main())
