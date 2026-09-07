import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
import sys

# Add parent directory to path so we can import from app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings
from app.models.user import Organization, UserInDB, UserCreate
from app.core.auth import get_password_hash

async def migrate():
    print(f"Connecting to MongoDB at {settings.MONGODB_URI}...")
    client = AsyncIOMotorClient(settings.MONGODB_URI)
    db = client[settings.MONGODB_DB]

    print("Checking for Novalantis Super Admin Organization...")
    super_admin_org = await db["organizations"].find_one({"name": "Novalantis"})
    if not super_admin_org:
        org_data = Organization(name="Novalantis", status="active").dict()
        await db["organizations"].insert_one(org_data)
        super_admin_org_id = org_data["id"]
        print(f"Created Super Admin Organization with ID: {super_admin_org_id}")
    else:
        super_admin_org_id = super_admin_org["id"]
        print("Super Admin Organization already exists.")

    print("Checking for default Super Admin user...")
    super_admin = await db["users"].find_one({"email": "superadmin@novalantis.com"})
    if not super_admin:
        hashed_password = get_password_hash("superadmin123")
        user_data = UserInDB(
            name="System Admin",
            email="superadmin@novalantis.com",
            role="SUPER_ADMIN",
            organization_id=super_admin_org_id,
            hashed_password=hashed_password
        ).dict()
        await db["users"].insert_one(user_data)
        print("Created default Super Admin: superadmin@novalantis.com / superadmin123")
    else:
        print("Default Super Admin already exists.")

    print("Checking for default customer organization (Company A)...")
    company_a = await db["organizations"].find_one({"name": "Company A"})
    if not company_a:
        org_data = Organization(name="Company A", status="active").dict()
        await db["organizations"].insert_one(org_data)
        company_a_id = org_data["id"]
        print(f"Created Company A Organization with ID: {company_a_id}")
    else:
        company_a_id = company_a["id"]
        print("Company A already exists.")

    print("Checking for Company A Admin user...")
    company_admin = await db["users"].find_one({"email": "admin@companya.com"})
    if not company_admin:
        hashed_password = get_password_hash("admin123")
        user_data = UserInDB(
            name="Company Admin",
            email="admin@companya.com",
            role="ORGANIZATION_ADMIN",
            organization_id=company_a_id,
            hashed_password=hashed_password
        ).dict()
        await db["users"].insert_one(user_data)
        print("Created Company Admin: admin@companya.com / admin123")
    else:
        print("Company Admin already exists.")

    print("Migrating existing data to Company A...")
    # Update candidates
    result = await db["candidates"].update_many(
        {"organization_id": {"$exists": False}},
        {"$set": {"organization_id": company_a_id}}
    )
    print(f"Updated {result.modified_count} candidates to belong to Company A.")

    # Update jobs (if they exist)
    if "jobs" in await db.list_collection_names():
        result = await db["jobs"].update_many(
            {"organization_id": {"$exists": False}},
            {"$set": {"organization_id": company_a_id}}
        )
        print(f"Updated {result.modified_count} jobs to belong to Company A.")

    print("Migration complete!")
    client.close()

if __name__ == "__main__":
    asyncio.run(migrate())
