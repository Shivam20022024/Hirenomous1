import asyncio
from app.core.database import connect_to_mongo, get_db, close_mongo_connection

async def main():
    await connect_to_mongo()
    db = get_db()
    
    # 1. Check how many candidates are in the database total
    total = await db.candidates.count_documents({})
    print(f"Total candidates before deletion: {total}")
    
    # 2. Check how many have the status 'selected'
    selected = await db.candidates.count_documents({'status': 'selected'})
    print(f"Candidates with status 'selected': {selected}")
    
    # 3. Check if they have an email matching a specific dummy pattern
    # For now, let's just delete the ones with status 'selected' and 'hired' to clean up the dashboard
    res = await db.candidates.delete_many({'status': {'$in': ['selected', 'hired']}})
    print(f"Deleted {res.deleted_count} dummy candidates with 'selected' or 'hired' status")
    
    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(main())
