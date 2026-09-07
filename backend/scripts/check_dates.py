import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

async def main():
    load_dotenv('.env.local')
    client = AsyncIOMotorClient(os.getenv('MONGODB_URI'))
    db = client[os.getenv('MONGODB_DB')]
    
    cursor = db.candidates.aggregate([
        {'$group': {'_id': {'$dateToString': {'format': '%Y-%m-%d', 'date': '$created_at'}}, 'count': {'$sum': 1}}}
    ])
    results = await cursor.to_list(None)
    print("Candidates by date:", results)
    
    org_cursor = db.organizations.find({})
    orgs = await org_cursor.to_list(None)
    print("Orgs:", orgs)
    client.close()

if __name__ == "__main__":
    asyncio.run(main())
