import asyncio
from dotenv import load_dotenv
load_dotenv('.env.local')

from app.db.mongo import connect_to_mongo, get_db

async def main():
    try:
        await connect_to_mongo()
        db = get_db()
        org_id = 'NOVALANTIS'
        rows = await db.interviews.find({'organization_id': org_id}).sort('created_at', -1).to_list(length=10)
        for r in rows:
            cid = r.get('candidate_id')
            print(f"Interview {r.get('id')} candidate_id: '{cid}' created: {r.get('created_at')}")
            c = await db.candidates.find_one({'id': cid})
            print(f"  Candidate: {c.get('name') if c else 'NOT_FOUND'}")
    except Exception as e:
        print(f"Error: {e}")

asyncio.run(main())
