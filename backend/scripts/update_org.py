import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv

async def main():
    load_dotenv('.env.local')
    uri = os.getenv('MONGODB_URI')
    db_name = os.getenv('MONGODB_DB')
    
    client = AsyncIOMotorClient(uri)
    db = client[db_name]
    
    org_id = '16612688-3635-4101-a28f-3209733a2249'
    result = await db.organizations.update_one(
        {"id": org_id},
        {"$set": {"name": "Hireonomous"}}
    )
    
    print(f"Matched: {result.matched_count}, Modified: {result.modified_count}")
    client.close()

if __name__ == "__main__":
    asyncio.run(main())
