import sys
sys.path.insert(0, '.')
import asyncio
from backend.app.db import db
import json

async def show():
    await db.connect()
    collections = await db.db.list_collection_names()
    print("Collections:", collections)
    
    det = await db.detection_events.find_one()
    if det:
        det['_id'] = str(det['_id'])
        print("\nSample detection_event:")
        print(json.dumps(det, indent=2, default=str))
        
    audit_count = await db.db['logs'].count_documents({})
    print(f"\nlogs collection count: {audit_count}")
    audit = await db.db['logs'].find_one()
    if audit:
        audit['_id'] = str(audit['_id'])
        print("Sample log:")
        print(json.dumps(audit, indent=2, default=str))

    # Also check if there is an 'audit' or 'logs' collection
    for col in collections:
        if 'audit' in col or 'log' in col:
            cnt = await db.db[col].count_documents({})
            print(f"Collection '{col}' count: {cnt}")
            
    cams = [c async for c in db.cameras.find({})]
    print(f"\nCameras count: {len(cams)}")
    for c in cams:
        print(f"  Camera: id={c.get('id')} name={c.get('name')} enabled={c.get('enabled')} ai_enabled={c.get('ai_enabled')} status={c.get('status')}")

    await db.close()

if __name__ == "__main__":
    asyncio.run(show())
