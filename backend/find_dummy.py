import asyncio
from app.core.database import get_db

async def main():
    try:
        from app.core.database import client
        if not client:
            from app.core.database import connect_to_mongo
            await connect_to_mongo()
            
        db = get_db()
        # Find the selected one
        c = await db.candidates.find_one({'status': {'$in': ['selected', 'hired']}})
        print("Selected candidate:", c.get('name') if c else "None")
        
        # Check if there are a lot of candidates
        total = await db.candidates.count_documents({})
        print("Total candidates:", total)
        
        # Look at one dummy candidate to see how to identify them
        dummy = await db.candidates.find_one({"name": {"$ne": "Shivam Kumar"}})
        print("Example candidate name:", dummy.get('name') if dummy else "None")
        print("Example candidate email:", dummy.get('email') if dummy else "None")
        
    except Exception as e:
        print("Error:", e)

asyncio.run(main())
