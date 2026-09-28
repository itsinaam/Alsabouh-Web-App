from typing import Optional
from sqlalchemy import or_
from sqlalchemy.orm import Session
from app.models.auth import User
from app.models.location import Location
from app.utils.constants import UserRole


def resolve_user_location(user: Optional[User], db: Session) -> Optional[Location]:
    """
    Resolves the operational Hub/Location for a user (Store Manager or Driver).
    Supports numeric ID, exact hub_name, partial hub_name, token search, and fallback.
    Admins return None (representing system-wide global access).
    """
    if not user:
        return None

    if user.role == UserRole.ADMIN:
        return None

    target = user.assigned_warehouse if user.role == UserRole.STORE_MANAGER else user.primary_hub
    if not target or not target.strip():
        # Fallback if user has either field set
        target = user.assigned_warehouse or user.primary_hub

    if not target or not target.strip():
        # If user has no assignment at all, return first active hub as safe operational fallback
        return db.query(Location).filter(or_(Location.status.is_(None), Location.status.ilike("active"))).first()

    clean = target.strip()

    # 1. Numeric ID lookup
    if clean.isdigit():
        loc = db.query(Location).filter(Location.id == int(clean)).first()
        if loc:
            return loc

    # 2. Exact hub_name match
    loc = db.query(Location).filter(Location.hub_name.ilike(clean)).first()
    if loc:
        return loc

    # 3. Partial hub_name match
    loc = db.query(Location).filter(Location.hub_name.ilike(f"%{clean}%")).first()
    if loc:
        return loc

    # 4. Search by individual significant words (e.g. "Dubai" in "Dubai Central Hub")
    tokens = [t for t in clean.replace("-", " ").replace("#", " ").split() if len(t) >= 3 and not t.isdigit()]
    for token in tokens:
        loc = db.query(Location).filter(
            or_(
                Location.hub_name.ilike(f"%{token}%"),
                Location.emirate_jurisdiction.ilike(f"%{token}%"),
            )
        ).first()
        if loc:
            return loc

    # 5. Safe fallback to first available active location
    return db.query(Location).filter(or_(Location.status.is_(None), Location.status.ilike("active"))).first()
