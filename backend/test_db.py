import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def main():
    try:
        client = AsyncIOMotorClient("mongodb+srv://Voice_Ai:Voice_Ai123@cluster0.hsvhojv.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
        db = client["voiceai"]
        
        # Drop the TTL index on the candidates collection
        await db.candidates.drop_index("ttl_created_at_7days")
        print("Successfully removed the TTL index. Candidates will no longer be auto-deleted.")
        
    except Exception as e:
        print(f"Error: {e}")

asyncio.run(main())
