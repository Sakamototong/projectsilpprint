from typing import Optional
from sqlalchemy.orm import Session

from .. import models

# ─── Tier thresholds (accumulated points) ───────────────────────────────────
# general  →  Silver  :    500 pts  (ยอดซื้อรวม  50,000 ฿)
# Silver   →  Gold    :  2,000 pts  (ยอดซื้อรวม 200,000 ฿)
# Gold     →  Platinum:  5,000 pts  (ยอดซื้อรวม 500,000 ฿)
TIER_THRESHOLDS = [
    ("platinum", 5000),
    ("gold",     2000),
    ("silver",    500),
    ("general",     0),
]


def _tier_for_points(points: int) -> str:
    for name, threshold in TIER_THRESHOLDS:
        if points >= threshold:
            return name
    return "general"


class MemberService:
    @staticmethod
    def add_points(db: Session, member_id: int, points: int) -> Optional[models.Member]:
        member = db.query(models.Member).filter(models.Member.id == member_id).first()
        if not member:
            return None
        member.points = max(0, (member.points or 0) + points)
        # Auto-upgrade / downgrade tier based on total points
        member.tier = _tier_for_points(member.points)
        db.add(member)
        db.commit()
        db.refresh(member)
        return member

    @staticmethod
    def points_for_amount(amount: float) -> int:
        """100 บาท = 1 คะแนน"""
        try:
            return int(amount // 100)
        except Exception:
            return 0
