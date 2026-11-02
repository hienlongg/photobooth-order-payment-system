import asyncio
import uuid

from app.core.security import get_password_hash
from app.db.base import Base
from app.db.session import AsyncSessionLocal, engine
from app.models.machine import Machine
from app.models.package import Package
from app.models.tenant import Tenant
from app.models.user import User


async def seed():
    # 1. Ensure fresh tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        # 2. Create Active Tenant
        tenant = Tenant(
            id=uuid.uuid4(),
            name="Wonderland Photobooth Co.",
            code="WONDERLAND_VN",
            is_active=True,
        )
        db.add(tenant)
        await db.flush()

        # 3. Create Users with Different Roles
        admin_user = User(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            username="admin_user",
            hashed_password=get_password_hash("AdminPass123!"),
            full_name="Alice Admin",
            role="admin",
            is_active=True,
        )
        operator_user = User(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            username="operator_user",
            hashed_password=get_password_hash("OperatorPass123!"),
            full_name="Bob Operator",
            role="operator",
            is_active=True,
        )
        customer_user = User(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            username="customer_user",
            hashed_password=get_password_hash("CustomerPass123!"),
            full_name="Charlie Customer",
            role="customer",
            is_active=True,
        )
        db.add_all([admin_user, operator_user, customer_user])

        # 4. Create Sample Machines
        m1 = Machine(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            machine_code="BOOTH-001",
            name="Vincom Center Booth 1",
            location="Floor 3, Vincom Center, HCMC",
            status="online",
            is_active=True,
        )
        m2 = Machine(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            machine_code="BOOTH-002",
            name="Landmark 81 Booth 2",
            location="B1, Landmark 81, HCMC",
            status="online",
            is_active=True,
        )
        # Deactivated/maintenance machine for testing business logic
        m_offline = Machine(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            machine_code="BOOTH-003",
            name="Crescent Mall Booth 3",
            location="Floor 2, Crescent Mall, HCMC",
            status="maintenance",
            is_active=False,
        )
        db.add_all([m1, m2, m_offline])

        # 5. Create Sample Packages
        p1 = Package(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            name="Standard 4-Cut Print",
            price_vnd=70000,
            duration_seconds=300,
            is_active=True,
        )
        p2 = Package(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            name="Premium Glitter 6-Cut Print",
            price_vnd=100000,
            duration_seconds=420,
            is_active=True,
        )
        db.add_all([p1, p2])

        await db.commit()
        print("Database successfully seeded!")
        print(f"Tenant ID:       {tenant.id}")
        print(f"Machine 1 (online) ID: {m1.id}")
        print(f"Machine 3 (maint) ID:  {m_offline.id}")
        print(f"Package 1 ID:    {p1.id} (Price: {p1.price_vnd} VND)")
        print(f"Package 2 ID:    {p2.id} (Price: {p2.price_vnd} VND)")
        print("Users created: 'admin_user', 'operator_user', 'customer_user'")


if __name__ == "__main__":
    asyncio.run(seed())
