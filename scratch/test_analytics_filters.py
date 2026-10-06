import asyncio, sys
sys.path.insert(0, '.')
from backend.app.db import db
from backend.app.models import User, UserRole
from backend.app.routes.detections import build_detection_filter

async def test():
    await db.connect()
    admin = User(
        id="test",
        email="admin@test.com",
        name="Admin",
        role=UserRole.SUPER_ADMIN,
        password_hash="dummy",
        organization_id="85dcc187-c43f-44af-974f-bc7fec85b088"
    )
    
    # Test with camera filter
    f_cam = build_detection_filter(admin, camera_id="ffc38562-f242-48a0-9a8a-b567c5f826cf")
    c_cam = await db.detection_events.count_documents(f_cam)
    print("Camera filter count:", c_cam)
    
    # Test with class filter
    f_cls = build_detection_filter(admin, class_name="person")
    c_cls = await db.detection_events.count_documents(f_cls)
    print("Class filter 'person' count:", c_cls)
    
    # Test with date filter
    f_date = build_detection_filter(admin, date_from="2026-10-05", date_to="2026-10-06")
    c_date = await db.detection_events.count_documents(f_date)
    print("Date filter '2026-10-05' to '2026-10-06' count:", c_date)
    
    await db.close()

if __name__ == '__main__':
    asyncio.run(test())
