from datetime import datetime, timezone
from werkzeug.security import check_password_hash, generate_password_hash
from extensions import db
from flask_login import UserMixin

def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    # An account may belong to a UWC student or a staff member.
    # The identifier is unique across both account types.
    uwc_identifier = db.Column(
        db.String(30),
        unique=True,
        nullable=False,
        index=True,
    )

    identifier_type = db.Column(
        db.String(20),
        nullable=False,
    )

    first_name = db.Column(
        db.String(100),
        nullable=False,
    )

    surname = db.Column(
        db.String(100),
        nullable=False,
    )

    email = db.Column(
        db.String(255),
        unique=True,
        nullable=False,
        index=True,
    )

    password_hash = db.Column(
        db.String(255),
        nullable=False,
    )

    # USER or ADMIN
    role = db.Column(
        db.String(20),
        nullable=False,
        default="USER",
    )

    is_active = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    lost_items = db.relationship(
        "LostItem",
        back_populates="reporter",
        cascade="all, delete-orphan",
    )

    found_items = db.relationship(
        "FoundItem",
        back_populates="finder",
        cascade="all, delete-orphan",
    )

    notifications = db.relationship(
        "Notification",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def __repr__(self) -> str:
        return (
            f"<User id={self.id} "
            f"uwc_identifier={self.uwc_identifier!r}>"
        )


class LostItem(db.Model):
    __tablename__ = "lost_items"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    reporter_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    category = db.Column(
        db.String(100),
        nullable=False,
        index=True,
    )

    item_name = db.Column(
        db.String(150),
        nullable=False,
    )

    description = db.Column(
        db.Text,
        nullable=False,
    )

    colour = db.Column(
        db.String(50),
        nullable=False,
        index=True,
    )

    brand = db.Column(
        db.String(100),
        nullable=True,
    )

    lost_date = db.Column(
        db.Date,
        nullable=False,
        index=True,
    )

    lost_time = db.Column(
        db.Time,
        nullable=True,
    )

    location = db.Column(
        db.String(200),
        nullable=False,
        index=True,
    )

    image_filename = db.Column(
        db.String(255),
        nullable=True,
    )
    private_details = db.Column(
        db.Text,
        nullable=False,
    )
    status = db.Column(
        db.String(40),
        nullable=False,
        default="REPORTED_LOST",
        index=True,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    reporter = db.relationship(
        "User",
        back_populates="lost_items",
    )

    def __repr__(self) -> str:
        return (
            f"<LostItem id={self.id} "
            f"item_name={self.item_name!r}>"
        )


class FoundItem(db.Model):
    __tablename__ = "found_items"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    finder_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    category = db.Column(
        db.String(100),
        nullable=False,
        index=True,
    )

    item_name = db.Column(
        db.String(150),
        nullable=False,
    )

    description = db.Column(
        db.Text,
        nullable=False,
    )

    colour = db.Column(
        db.String(50),
        nullable=False,
        index=True,
    )
    brand = db.Column(
        db.String(100),
        nullable=True,
    )
    found_date = db.Column(
        db.Date,
        nullable=False,
        index=True,
    )

    found_time = db.Column(
        db.Time,
        nullable=True,
    )
    location = db.Column(
        db.String(200),
        nullable=False,
        index=True,
    )
    image_filename = db.Column(
        db.String(255),
        nullable=True,
    )
    private_details = db.Column(
        db.Text,
        nullable=False,
    )
    storage_location = db.Column(
        db.String(200),
        nullable=False,
    )
    status = db.Column(
        db.String(40),
        nullable=False,
        default="REPORTED_FOUND",
        index=True,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    finder = db.relationship(
        "User",
        back_populates="found_items",
    )

    def __repr__(self) -> str:
        return (
            f"<FoundItem id={self.id} "
            f"item_name={self.item_name!r}>"
        )


class OwnershipClaim(db.Model):
    """An ownership claim submitted for a found item."""

    __tablename__ = "ownership_claims"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    claimant_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    found_item_id = db.Column(
        db.Integer,
        db.ForeignKey("found_items.id"),
        nullable=False,
        index=True,
    )

    ownership_details = db.Column(
        db.Text,
        nullable=False,
    )

    status = db.Column(
        db.String(30),
        nullable=False,
        default="PENDING",
    )

    review_notes = db.Column(
        db.Text,
        nullable=True,
    )

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.now(),
    )

    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.now(),
        onupdate=db.func.now(),
    )

    notifications = db.relationship(
        "Notification",
        back_populates="claim",
        cascade="all, delete-orphan",
    )

    claimant = db.relationship(
        "User",
        backref="ownership_claims",
    )

    found_item = db.relationship(
        "FoundItem",
        backref="ownership_claims",
    )

class Notification(db.Model):
    """Persistent in-app notification for a user."""

    __tablename__ = "notifications"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    claim_id = db.Column(
        db.Integer,
        db.ForeignKey("ownership_claims.id"),
        nullable=True,
        index=True,
    )

    title = db.Column(
        db.String(200),
        nullable=False,
    )

    message = db.Column(
        db.Text,
        nullable=False,
    )

    category = db.Column(
        db.String(20),
        nullable=False,
        default="info",
    )

    is_read = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
        index=True,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    user = db.relationship(
        "User",
        back_populates="notifications",
    )

    claim = db.relationship(
        "OwnershipClaim",
        back_populates="notifications",
    )

    def __repr__(self) -> str:
        return (
            f"<Notification id={self.id} "
            f"user_id={self.user_id} is_read={self.is_read}>"
        )
