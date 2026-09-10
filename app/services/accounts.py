from sqlalchemy.orm import Session

from app.models.profile import Profile
from app.models.user import User


def add_user_with_profile(db: Session, **user_fields) -> User:
    """Stage a user and its required empty profile in the current transaction."""
    user = User(**user_fields)
    db.add(user)
    db.flush()
    db.add(Profile(user_id=user.id))
    return user
