import asyncio, sys
sys.path.insert(0, '.')
from backend.app.db import db
from backend.app.models import User, UserRole
from backend.app.routes.analytics import get_full_analytics
import json

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
    res = await get_full_analytics(current_user=admin)
    data = res.data
    print("Overview:", data.overview.model_dump())
    print("Top 3 Classes:", [c.model_dump() for c in data.classes[:3]])
    print("Top 3 Cameras:", [c.model_dump() for c in data.cameras[:3]])
    print("Duration Stats:", data.duration.model_dump())
    print("Trends count:", len(data.trends.points))
    await db.close()

if __name__ == '__main__':
    asyncio.run(test())
