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
    
    # Update the user
    result = await db.users.update_one(
        {"name": "shubam kumar"},
        {"$set": {"organization_name": "Hireonomous"}}
    )
    
    if result.modified_count > 0:
        print("Successfully updated company name to Hireonomous in the database.")
    elif result.matched_count > 0:
        print("User found, but company name was already Hireonomous.")
    else:
        # Try finding by lowercase or similar if exact match fails
        user = await db.users.find_one({"name": {"$regex": "shubam", "$options": "i"}})
        if user:
            print(f"Found user with similar name: {user.get('name')}")
            res = await db.users.update_one({"_id": user["_id"]}, {"$set": {"organization_name": "Hireonomous"}})
            print(f"Updated similar user. Modified: {res.modified_count}")
        else:
            print("Could not find user 'shubam kumar' in the database.")
            
    client.close()

if __name__ == "__main__":
    asyncio.run(main())
