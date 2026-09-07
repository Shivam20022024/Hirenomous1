import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv

async def check_candidates():
    load_dotenv('.env.local')
    mongo_uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    client = AsyncIOMotorClient(mongo_uri)
    db = client.get_database("voiceai")
    
    candidates = await db.candidates.find().to_list(length=100)
    print(f"Found {len(candidates)} candidates")
    for c in candidates:
        print(f"ID: {c.get('id')}, Name: {c.get('name')}, Status: {c.get('status')}, Interest: {c.get('interest')}, Call Status: {c.get('call_status')}, Bolna Call ID: {c.get('bolna_call_id')}")
        if 'bolna_analysis' in c:
            print(f"  Bolna Analysis: {c['bolna_analysis']}")
        if 'transcript' in c:
            print(f"  Transcript Length: {len(c['transcript'])}")

if __name__ == "__main__":
    asyncio.run(check_candidates())
