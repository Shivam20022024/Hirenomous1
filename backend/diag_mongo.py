import asyncio
from app.core.database import connect_to_mongo, close_mongo_connection, get_db
import sys

async def main():
    try:
        await connect_to_mongo()
        db = get_db()
        if db is not None:
            await db.command("ping")
            print("Ping successful!")
            sys.exit(0)
        else:
            print("Database instance is None")
            sys.exit(1)
    except Exception as e:
        print(f"Ping failed: {e}")
        sys.exit(1)
    finally:
        await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(main())
