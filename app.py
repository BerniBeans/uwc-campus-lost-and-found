from datetime import date
from email.message import EmailMessage
import os
import secrets
import shutil
import smtplib
import ssl
from pathlib import Path
from functools import wraps
from uuid import uuid4

from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)

from flask_login import (
    current_user,
    login_required,
    login_user,
    logout_user,
)

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.utils import secure_filename

from extensions import (
    csrf,
    db,
    login_manager,
    migrate,
)

from forms import (
    ClaimReviewForm,
    FoundItemForm,
    LoginForm,
    LogoutForm,
    LostItemForm,
    NotificationReadForm,
    OwnershipClaimForm,
    RegistrationForm,
)

from models import (
    FoundItem,
    LostItem,
    Notification,
    OwnershipClaim,
    User,
)


# Do not display ID documents or wallet photographs in the public item feed.
SENSITIVE_IMAGE_CATEGORIES = {"IDENTIFICATION", "STUDENT_CARD", "WALLET"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


# ---------------------------------------------------------
# FLASK-LOGIN USER LOADER
# ---------------------------------------------------------

@login_manager.user_loader
def load_user(user_id: str) -> User | None:
    """Load a user from the database for Flask-Login."""

    try:
        numeric_user_id = int(user_id)
    except (TypeError, ValueError):
        return None

    return db.session.get(User, numeric_user_id)

def admin_required(view_function):

    """Restrict a route to administrator accounts."""

    @wraps(view_function)
    def wrapped_view(*args, **kwargs):
        if current_user.role != "ADMIN":
            abort(403)

        return view_function(*args, **kwargs)

    return wrapped_view

def normalise_text(value: str | None) -> str:
    """Convert optional text into a clean lowercase value."""

    if not value:
        return ""

    return " ".join(
        value.strip().lower().split()
    )


def extract_keywords(value: str | None) -> set[str]:
    """Extract useful words from item names and descriptions."""

    if not value:
        return set()

    cleaned_text = "".join(
        character.lower()
        if character.isalnum()
        else " "
        for character in value
    )

    ignored_words = {
        "and",
        "the",
        "with",
        "this",
        "that",
        "from",
        "item",
        "small",
        "large",
        "found",
        "lost",
        "near",
    }

    return {
        word
        for word in cleaned_text.split()
        if len(word) >= 3
        and word not in ignored_words
    }


def calculate_match_score(
    lost_item: LostItem,
    found_item: FoundItem,
) -> tuple[int, list[str]]:

    score = 0
    reasons = []

    if lost_item.category != found_item.category:
        return 0, []

    score += 40
    reasons.append("Same category")

    lost_colour = normalise_text(lost_item.colour)
    found_colour = normalise_text(found_item.colour)

    if lost_colour and found_colour:
        if lost_colour == found_colour:
            score += 20
            reasons.append("Same colour")

        elif (
            lost_colour in found_colour
            or found_colour in lost_colour
        ):
            score += 10
            reasons.append("Similar colour")

    lost_brand = normalise_text(lost_item.brand)
    found_brand = normalise_text(found_item.brand)

    if lost_brand and found_brand:
        if lost_brand == found_brand:
            score += 15
            reasons.append("Same brand")

        elif (
            lost_brand in found_brand
            or found_brand in lost_brand
        ):
            score += 8
            reasons.append("Similar brand")

    if lost_item.location == found_item.location:
        score += 10
        reasons.append("Same location")

    date_difference = (
        found_item.found_date
        - lost_item.lost_date
    ).days

    if date_difference < 0:
        return 0, []

    if date_difference <= 3:
        score += 15
        reasons.append("Dates are within 3 days")

    elif date_difference <= 7:
        score += 12
        reasons.append("Dates are within 7 days")

    elif date_difference <= 14:
        score += 8
        reasons.append("Dates are within 14 days")

    elif date_difference <= 30:
        score += 4
        reasons.append("Dates are within 30 days")

    lost_keywords = extract_keywords(
        f"{lost_item.item_name} "
        f"{lost_item.description}"
    )

    found_keywords = extract_keywords(
        f"{found_item.item_name} "
        f"{found_item.description}"
    )

    shared_keywords = lost_keywords.intersection(
        found_keywords
    )

    if shared_keywords:
        keyword_score = min(
            len(shared_keywords) * 5,
            15,
        )

        score += keyword_score

        reasons.append(
            "Shared keywords: "
            + ", ".join(
                sorted(shared_keywords)[:3]
            )
        )

    return min(score, 100), reasons
def save_uploaded_image(file_storage, upload_folder: Path) -> str | None:
    """Save verified image bytes outside Flask's public static directory."""
    if file_storage is None or not file_storage.filename:
        return None

    original_filename = secure_filename(file_storage.filename)
    extension = Path(original_filename).suffix.lower()
    if extension not in IMAGE_EXTENSIONS:
        raise ValueError("Only JPG, JPEG, PNG and WEBP images are allowed.")

    # File extension validation alone is not sufficient: verify basic
    # signature bytes without pulling in a separate image library.
    signature = file_storage.stream.read(12)
    file_storage.stream.seek(0)
    valid_image = (
        (extension in {".jpg", ".jpeg"} and signature.startswith(b"\xff\xd8\xff"))
        or (extension == ".png" and signature.startswith(b"\x89PNG\r\n\x1a\n"))
        or (
            extension == ".webp"
            and signature.startswith(b"RIFF")
            and signature[8:12] == b"WEBP"
        )
    )
    if not valid_image:
        raise ValueError("The selected file does not contain a valid image header.")

    unique_filename = f"{uuid4().hex}{extension}"
    file_storage.save(upload_folder / unique_filename)
    return unique_filename


def validate_safe_image_category(form) -> bool:
    """Avoid collecting photographs of identity cards or wallets."""
    image = form.image.data
    if image is not None and image.filename and form.category.data in SENSITIVE_IMAGE_CATEGORIES:
        form.image.errors.append(
            "For privacy, do not upload photos of ID documents, student cards or wallets. "
            "Please submit the report without a photograph."
        )
        return False
    return True


def env_flag(name: str, default: bool = False) -> bool:
    """Read a boolean environment variable."""

    value = os.environ.get(name)

    if value is None:
        return default

    return value.strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def humanise_code(value: str | None) -> str:
    """Convert stored constant-style text into a readable label."""

    if not value:
        return "Not provided"

    return value.replace("_", " ").title()


def build_claim_notification(
    claim: OwnershipClaim,
    decision: str,
) -> Notification:
    """Build the persistent notification for a claim decision."""

    if decision == "APPROVED":
        title = "Ownership claim approved"
        category = "success"
        message = (
            f"Your ownership claim C-{claim.id} for "
            f"F-{claim.found_item_id} "
            f"({claim.found_item.item_name}) was approved. "
            f"The item is recorded at "
            f"{humanise_code(claim.found_item.storage_location)}."
        )
    else:
        title = "Ownership claim rejected"
        category = "error"
        message = (
            f"Your ownership claim C-{claim.id} for "
            f"F-{claim.found_item_id} "
            f"({claim.found_item.item_name}) was not approved."
        )

        if claim.review_notes:
            message += f" Review notes: {claim.review_notes}"

    return Notification(
        user_id=claim.claimant_id,
        claim_id=claim.id,
        title=title,
        message=message,
        category=category,
        is_read=False,
    )


def send_claim_decision_email(
    app: Flask,
    claim: OwnershipClaim,
) -> tuple[bool, str]:
    """Send a claim-result email without changing database state."""

    if not app.config["EMAIL_NOTIFICATIONS_ENABLED"]:
        return False, "Email notifications are disabled."

    smtp_host = app.config["SMTP_HOST"]
    smtp_from = app.config["SMTP_FROM"]

    if not smtp_host or not smtp_from:
        return False, "SMTP settings are incomplete."

    approved = claim.status == "APPROVED"
    decision_word = "Approved" if approved else "Rejected"

    message = EmailMessage()
    message["Subject"] = (
        "UWC Lost-and-Found — "
        f"Ownership Claim {decision_word}"
    )
    message["From"] = smtp_from
    message["To"] = claim.claimant.email

    body_lines = [
        f"Hello {claim.claimant.first_name},",
        "",
        (
            f"Your ownership claim C-{claim.id} for found-item "
            f"report F-{claim.found_item_id} "
            f"({claim.found_item.item_name}) has been "
            f"{claim.status.lower()}."
        ),
    ]

    if approved:
        body_lines.extend(
            [
                "",
                (
                    "Recorded storage location: "
                    f"{humanise_code(claim.found_item.storage_location)}"
                ),
            ]
        )

    if claim.review_notes:
        body_lines.extend(
            [
                "",
                f"Review notes: {claim.review_notes}",
            ]
        )

    body_lines.extend(
        [
            "",
            "You can also view this decision when you log in to the app.",
            "",
            "UWC Campus Lost-and-Found",
            "Software Engineering Student Project",
        ]
    )

    message.set_content("\n".join(body_lines))

    try:
        if app.config["SMTP_USE_SSL"]:
            context = ssl.create_default_context()

            with smtplib.SMTP_SSL(
                smtp_host,
                app.config["SMTP_PORT"],
                context=context,
                timeout=15,
            ) as smtp:
                if app.config["SMTP_USER"]:
                    smtp.login(
                        app.config["SMTP_USER"],
                        app.config["SMTP_PASSWORD"],
                    )

                smtp.send_message(message)

        else:
            with smtplib.SMTP(
                smtp_host,
                app.config["SMTP_PORT"],
                timeout=15,
            ) as smtp:
                smtp.ehlo()

                if app.config["SMTP_USE_STARTTLS"]:
                    context = ssl.create_default_context()
                    smtp.starttls(context=context)
                    smtp.ehlo()

                if app.config["SMTP_USER"]:
                    smtp.login(
                        app.config["SMTP_USER"],
                        app.config["SMTP_PASSWORD"],
                    )

                smtp.send_message(message)

    except Exception as exc:
        app.logger.exception(
            "Claim decision saved, but the result email could not be sent."
        )
        return False, str(exc)

    return True, "Email sent."


# ---------------------------------------------------------
# APPLICATION FACTORY
# ---------------------------------------------------------

def create_app() -> Flask:
    """Create and configure the Flask application."""

    app = Flask(
        __name__,
        instance_relative_config=True,
    )

    # -----------------------------------------------------
    # APPLICATION CONFIGURATION
    # -----------------------------------------------------

    # Never use a known secret for sessions/CSRF. For local development,
    # generate an ephemeral secret when one is not supplied; deployment
    # must explicitly configure SECRET_KEY via its environment settings.
    configured_secret = os.environ.get("SECRET_KEY")
    if configured_secret:
        app.config["SECRET_KEY"] = configured_secret
    elif os.environ.get("DATABASE_URL"):
        raise RuntimeError("Set SECRET_KEY in the deployment environment before starting the application.")
    else:
        app.config["SECRET_KEY"] = secrets.token_urlsafe(32)

    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = env_flag(
        "SESSION_COOKIE_SECURE", env_flag("RENDER", False)
    )

    # -----------------------------------------------------
    # DATABASE CONFIGURATION
    # -----------------------------------------------------

    database_url = os.environ.get("DATABASE_URL")

    if database_url:
        # Use PostgreSQL when DATABASE_URL is supplied
        # by the production environment.
        if database_url.startswith("postgres://"):
            database_url = database_url.replace(
                "postgres://",
                "postgresql+psycopg2://",
                1,
            )

        elif database_url.startswith("postgresql://"):
            database_url = database_url.replace(
                "postgresql://",
                "postgresql+psycopg2://",
                1,
            )

        app.config["SQLALCHEMY_DATABASE_URI"] = database_url

    else:
        # Use SQLite for local development.
        app.config["SQLALCHEMY_DATABASE_URI"] = (
            "sqlite:///lost_found.db"
        )

    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # Ensure the instance folder exists.
    Path(app.instance_path).mkdir(
        parents=True,
        exist_ok=True,
    )

    # -----------------------------------------------------
    # IMAGE UPLOAD CONFIGURATION
    # -----------------------------------------------------

    # New uploads live in a private directory, not at /static/uploads/.
    upload_folder = Path(app.instance_path) / "uploads"
    upload_folder.mkdir(parents=True, exist_ok=True)
    app.config["UPLOAD_FOLDER"] = str(upload_folder)

    # Move older local test photographs out of the publicly served static
    # directory. Keep the static/uploads/.gitkeep placeholder intact.
    legacy_upload_folder = Path(app.static_folder) / "uploads"
    if legacy_upload_folder.exists():
        for previous_image in legacy_upload_folder.iterdir():
            if not previous_image.is_file() or previous_image.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            destination = upload_folder / previous_image.name
            if destination.exists():
                previous_image.unlink()
            else:
                shutil.move(str(previous_image), str(destination))

    @app.after_request
    def add_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.get("/item-images/<string:report_type>/<int:item_id>")
    @login_required
    def item_image(report_type: str, item_id: int):
        """Serve item images through authentication and category access rules."""
        if report_type == "lost":
            item = db.session.get(LostItem, item_id)
            poster_id = item.reporter_id if item else None
        elif report_type == "found":
            item = db.session.get(FoundItem, item_id)
            poster_id = item.finder_id if item else None
        else:
            abort(404)

        if item is None or not item.image_filename:
            abort(404)
        if (
            item.category in SENSITIVE_IMAGE_CATEGORIES
            and current_user.role != "ADMIN"
            and current_user.id != poster_id
        ):
            abort(403)

        response = send_from_directory(app.config["UPLOAD_FOLDER"], item.image_filename)
        response.headers["Cache-Control"] = "private, no-store"
        return response

    # Limit each request to 5 MB.
    app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

    # -----------------------------------------------------
    # OPTIONAL EMAIL NOTIFICATION CONFIGURATION
    # -----------------------------------------------------

    app.config["EMAIL_NOTIFICATIONS_ENABLED"] = env_flag(
        "EMAIL_NOTIFICATIONS_ENABLED",
        False,
    )
    app.config["SMTP_HOST"] = os.environ.get("SMTP_HOST", "")
    app.config["SMTP_PORT"] = int(
        os.environ.get("SMTP_PORT", "465")
    )
    app.config["SMTP_USER"] = os.environ.get("SMTP_USER", "")
    app.config["SMTP_PASSWORD"] = os.environ.get(
        "SMTP_PASSWORD",
        "",
    )
    app.config["SMTP_FROM"] = os.environ.get(
        "SMTP_FROM",
        app.config["SMTP_USER"],
    )
    app.config["SMTP_USE_SSL"] = env_flag(
        "SMTP_USE_SSL",
        True,
    )
    app.config["SMTP_USE_STARTTLS"] = env_flag(
        "SMTP_USE_STARTTLS",
        False,
    )

    # -----------------------------------------------------
    # INITIALISE EXTENSIONS
    # -----------------------------------------------------

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)

    # -----------------------------------------------------
    # FLASK-LOGIN CONFIGURATION
    # -----------------------------------------------------

    login_manager.login_view = "login"

    login_manager.login_message = (
        "Please log in to access this page."
    )

    login_manager.login_message_category = "error"

    # Make small CSRF-protected forms available in templates.
    @app.context_processor
    def provide_global_forms():
        return {
            "logout_form": LogoutForm(),
            "notification_read_form": NotificationReadForm(),
        }

    # -----------------------------------------------------
    # HOME PAGE
    # -----------------------------------------------------

    @app.get("/")
    def home():
        return render_template("home.html")

    # -----------------------------------------------------
    # USER REGISTRATION
    # -----------------------------------------------------

    @app.route(
        "/register",
        methods=["GET", "POST"],
    )
    def register():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard"))

        form = RegistrationForm()

        if form.validate_on_submit():
            uwc_identifier = (
                form.uwc_identifier.data
                .strip()
                .upper()
            )
            identifier_type = form.identifier_type.data

            first_name = (
                form.first_name.data
                .strip()
            )

            surname = (
                form.surname.data
                .strip()
            )

            email = (
                form.email.data
                .strip()
                .lower()
            )

            # Email and identifier may belong to *different* existing
            # accounts. Two separate lookups avoid MultipleResultsFound.
            email_exists = db.session.execute(
                db.select(User.id).where(User.email == email)
            ).scalar_one_or_none() is not None
            identifier_exists = db.session.execute(
                db.select(User.id).where(User.uwc_identifier == uwc_identifier)
            ).scalar_one_or_none() is not None

            if email_exists or identifier_exists:
                if email_exists:
                    flash("An account already uses this email address.", "error")
                if identifier_exists:
                    flash("An account already uses this UWC identifier.", "error")
                return render_template("register.html", form=form)

            user = User(
                uwc_identifier=uwc_identifier,
                identifier_type=identifier_type,
                first_name=first_name,
                surname=surname,
                email=email,
                role="USER",
            )

            user.set_password(form.password.data)

            db.session.add(user)

            try:
                db.session.commit()

            except IntegrityError:
                db.session.rollback()

                flash(
                    "The account could not be created because "
                    "the email or UWC identifier already exists.",
                    "error",
                )

                return render_template(
                    "register.html",
                    form=form,
                )

            except SQLAlchemyError:
                db.session.rollback()

                app.logger.exception(
                    "Unexpected registration database error."
                )

                flash(
                    "The account could not be created. "
                    "Please try again.",
                    "error",
                )

                return render_template(
                    "register.html",
                    form=form,
                )

            flash(
                "Your account was created successfully. "
                "You may now log in.",
                "success",
            )

            return redirect(url_for("login"))

        return render_template(
            "register.html",
            form=form,
        )

    # -----------------------------------------------------
    # USER LOGIN
    # -----------------------------------------------------

    @app.route(
        "/login",
        methods=["GET", "POST"],
    )
    def login():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard"))

        form = LoginForm()

        if form.validate_on_submit():
            email = (
                form.email.data
                .strip()
                .lower()
            )

            user = db.session.execute(
                db.select(User).where(
                    User.email == email
                )
            ).scalar_one_or_none()

            if (
                user is None
                or not user.check_password(
                    form.password.data
                )
            ):
                flash(
                    "Invalid email address or password.",
                    "error",
                )

                return render_template(
                    "login.html",
                    form=form,
                )

            if not user.is_active:
                flash(
                    "This account is currently inactive.",
                    "error",
                )

                return render_template(
                    "login.html",
                    form=form,
                )

            login_user(
                user,
                remember=form.remember.data,
            )

            flash(
                f"Welcome, {user.first_name}.",
                "success",
            )

            return redirect(url_for("dashboard"))

        return render_template(
            "login.html",
            form=form,
        )

    # -----------------------------------------------------
    # STUDENT DASHBOARD
    # -----------------------------------------------------

    @app.get("/dashboard")
    @login_required
    def dashboard():
        unread_notifications = db.session.execute(
            db.select(Notification)
            .where(
                Notification.user_id == current_user.id,
                Notification.is_read.is_(False),
            )
            .order_by(Notification.created_at.desc())
        ).scalars().all()

        return render_template(
            "dashboard.html",
            unread_notifications=unread_notifications,
        )

    # -----------------------------------------------------
    # MARK AN IN-APP NOTIFICATION AS READ
    # -----------------------------------------------------

    @app.post("/notifications/<int:notification_id>/read")
    @login_required
    def mark_notification_read(notification_id: int):
        form = NotificationReadForm()

        if not form.validate_on_submit():
            abort(400)

        notification = db.session.execute(
            db.select(Notification).where(
                Notification.id == notification_id,
                Notification.user_id == current_user.id,
            )
        ).scalar_one_or_none()

        if notification is None:
            abort(404)

        notification.is_read = True

        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception(
                "Failed to mark notification as read."
            )
            flash(
                "The notification could not be updated.",
                "error",
            )

        return redirect(url_for("dashboard"))

    # -----------------------------------------------------
    # REPORT A LOST ITEM
    # -----------------------------------------------------

    @app.route(
        "/lost-items/report",
        methods=["GET", "POST"],
    )
    @login_required
    def report_lost_item():
        form = LostItemForm()

        if form.validate_on_submit():
            brand = None

            if form.brand.data:
                cleaned_brand = form.brand.data.strip()

                if cleaned_brand:
                    brand = cleaned_brand

            if not validate_safe_image_category(form):
                return render_template("report_lost_item.html", form=form)

            try:
                image_filename = save_uploaded_image(
                    form.image.data,
                    Path(app.config["UPLOAD_FOLDER"]),
                )
            except ValueError as exc:
                form.image.errors.append(str(exc))
                return render_template("report_lost_item.html", form=form)

            lost_item = LostItem(
                reporter_id=current_user.id,
                category=form.category.data,
                item_name=form.item_name.data.strip(),
                description=form.description.data.strip(),
                colour=form.colour.data.strip(),
                brand=brand,
                lost_date=form.lost_date.data,
                lost_time=form.lost_time.data,
                location=form.location.data,
                image_filename=image_filename,
                private_details=(
                    form.private_details.data.strip()
                ),
                status="REPORTED_LOST",
            )

            db.session.add(lost_item)

            try:
                db.session.commit()

            except SQLAlchemyError:
                db.session.rollback()

                app.logger.exception(
                    "Failed to save a lost-item report."
                )

                flash(
                    "The lost-item report could not be saved. "
                    "Please try again.",
                    "error",
                )

                return render_template(
                    "report_lost_item.html",
                    form=form,
                )

            flash(
                "Your lost-item report was submitted "
                f"successfully. Report number: {lost_item.id}.",
                "success",
            )

            return redirect(url_for("dashboard"))

        return render_template(
            "report_lost_item.html",
            form=form,
        )

    # -----------------------------------------------------
    # REPORT A FOUND ITEM
    # -----------------------------------------------------

    @app.route(
        "/found-items/report",
        methods=["GET", "POST"],
    )
    @login_required
    def report_found_item():
        form = FoundItemForm()

        if form.validate_on_submit():
            brand = None

            if form.brand.data:
                cleaned_brand = form.brand.data.strip()

                if cleaned_brand:
                    brand = cleaned_brand

            if not validate_safe_image_category(form):
                return render_template("report_found_item.html", form=form)

            try:
                image_filename = save_uploaded_image(
                    form.image.data,
                    Path(app.config["UPLOAD_FOLDER"]),
                )
            except ValueError as exc:
                form.image.errors.append(str(exc))
                return render_template("report_found_item.html", form=form)


            found_item = FoundItem(
                finder_id=current_user.id,
                category=form.category.data,
                item_name=form.item_name.data.strip(),
                description=form.description.data.strip(),
                colour=form.colour.data.strip(),
                brand=brand,
                found_date=form.found_date.data,
                found_time=form.found_time.data,
                location=form.location.data,
                image_filename=image_filename,
                private_details=(
                    form.private_details.data.strip()
                ),
                storage_location=(
                    form.storage_location.data
                ),
                status="REPORTED_FOUND",
            )

            db.session.add(found_item)

            try:
                db.session.commit()

            except SQLAlchemyError:
                db.session.rollback()

                app.logger.exception(
                    "Failed to save a found-item report."
                )

                flash(
                    "The found-item report could not be saved. "
                    "Please try again.",
                    "error",
                )

                return render_template(
                    "report_found_item.html",
                    form=form,
                )

            flash(
                "Your found-item report was submitted "
                f"successfully. Report number: {found_item.id}.",
                "success",
            )

            return redirect(url_for("dashboard"))

        return render_template(
            "report_found_item.html",
            form=form,
        )


    # -----------------------------------------------------
    # SEARCH REPORTED ITEMS
    # -----------------------------------------------------

    @app.get("/items/search")
    @login_required
    def search_items():
        report_type = (
            request.args.get("report_type", "all")
            .strip()
            .lower()
        )

        category = (
            request.args.get("category", "")
            .strip()
            .upper()
        )

        colour = (
            request.args.get("colour", "")
            .strip()
        )

        location = (
            request.args.get("location", "")
            .strip()
            .upper()
        )

        keyword = (
            request.args.get("keyword", "")
            .strip()
        )

        date_from_text = (
            request.args.get("date_from", "")
            .strip()
        )

        date_to_text = (
            request.args.get("date_to", "")
            .strip()
        )

        if report_type not in {
            "all",
            "lost",
            "found",
        }:
            report_type = "all"

        date_from = None
        date_to = None

        try:
            if date_from_text:
                date_from = date.fromisoformat(
                    date_from_text
                )

            if date_to_text:
                date_to = date.fromisoformat(
                    date_to_text
                )

        except ValueError:
            flash(
                "Please enter valid search dates.",
                "error",
            )

            return redirect(
                url_for("search_items")
            )

        if (
            date_from is not None
            and date_to is not None
            and date_from > date_to
        ):
            flash(
                "The starting date cannot be after "
                "the ending date.",
                "error",
            )

            return redirect(
                url_for("search_items")
            )

        lost_items = []
        found_items = []

        # -------------------------------------------------
        # LOST-ITEM QUERY
        # -------------------------------------------------

        if report_type in {"all", "lost"}:
            lost_query = db.select(LostItem)

            if category:
                lost_query = lost_query.where(
                    LostItem.category == category
                )

            if colour:
                colour_pattern = f"%{colour}%"

                lost_query = lost_query.where(
                    LostItem.colour.ilike(
                        colour_pattern
                    )
                )

            if location:
                lost_query = lost_query.where(
                    LostItem.location == location
                )

            if keyword:
                keyword_pattern = f"%{keyword}%"

                lost_query = lost_query.where(
                    or_(
                        LostItem.item_name.ilike(
                            keyword_pattern
                        ),
                        LostItem.description.ilike(
                            keyword_pattern
                        ),
                        LostItem.brand.ilike(
                            keyword_pattern
                        ),
                    )
                )

            if date_from is not None:
                lost_query = lost_query.where(
                    LostItem.lost_date >= date_from
                )

            if date_to is not None:
                lost_query = lost_query.where(
                    LostItem.lost_date <= date_to
                )

            lost_query = (
                lost_query
                .order_by(
                    LostItem.created_at.desc()
                )
                .limit(100)
            )

            lost_items = db.session.execute(
                lost_query
            ).scalars().all()

        # -------------------------------------------------
        # FOUND-ITEM QUERY
        # -------------------------------------------------

        if report_type in {"all", "found"}:
            found_query = db.select(FoundItem)

            if category:
                found_query = found_query.where(
                    FoundItem.category == category
                )

            if colour:
                colour_pattern = f"%{colour}%"

                found_query = found_query.where(
                    FoundItem.colour.ilike(
                        colour_pattern
                    )
                )

            if location:
                found_query = found_query.where(
                    FoundItem.location == location
                )

            if keyword:
                keyword_pattern = f"%{keyword}%"

                found_query = found_query.where(
                    or_(
                        FoundItem.item_name.ilike(
                            keyword_pattern
                        ),
                        FoundItem.description.ilike(
                            keyword_pattern
                        ),
                        FoundItem.brand.ilike(
                            keyword_pattern
                        ),
                    )
                )

            if date_from is not None:
                found_query = found_query.where(
                    FoundItem.found_date >= date_from
                )

            if date_to is not None:
                found_query = found_query.where(
                    FoundItem.found_date <= date_to
                )

            found_query = (
                found_query
                .order_by(
                    FoundItem.created_at.desc()
                )
                .limit(100)
            )

            found_items = db.session.execute(
                found_query
            ).scalars().all()

        categories = [
            ("", "All categories"),
            ("BAG", "Bag"),
            ("BOOKS", "Books"),
            ("CLOTHING", "Clothing"),
            ("ELECTRONICS", "Electronics"),
            ("IDENTIFICATION", "Identification document"),
            ("JEWELLERY", "Jewellery"),
            ("KEYS", "Keys"),
            ("PHONE", "Mobile phone"),
            ("WALLET", "Money or wallet"),
            ("STUDENT_CARD", "Student card"),
            ("OTHER", "Other"),
        ]

        locations = [
            ("", "All locations"),
            ("LIBRARY", "Library"),
            ("LECTURE_HALL", "Lecture hall"),
            ("COMPUTER_LAB", "Computer laboratory"),
            ("CAFETERIA", "Cafeteria"),
            ("RESIDENCE", "Residence"),
            ("SPORTS_CENTRE", "Sports centre"),
            ("ADMIN_BUILDING", "Administration building"),
            ("PARKING", "Parking area"),
            ("SHUTTLE", "Campus shuttle"),
            ("OTHER", "Other"),
        ]

        filters = {
            "report_type": report_type,
            "category": category,
            "colour": colour,
            "location": location,
            "keyword": keyword,
            "date_from": date_from_text,
            "date_to": date_to_text,
        }

        return render_template(
            "search_items.html",
            lost_items=lost_items,
            found_items=found_items,
            categories=categories,
            locations=locations,
            filters=filters,
        )


    # -----------------------------------------------------
    # VIEW POSSIBLE MATCHES
    # -----------------------------------------------------

    @app.get("/matches")
    @login_required
    def possible_matches():
        lost_items = db.session.execute(
            db.select(LostItem)
            .where(
                LostItem.reporter_id
                == current_user.id,
                LostItem.status
                == "REPORTED_LOST",
            )
            .order_by(
                LostItem.created_at.desc()
            )
        ).scalars().all()

        found_items = db.session.execute(
            db.select(FoundItem)
            .where(
                FoundItem.status
                == "REPORTED_FOUND",
                FoundItem.finder_id != current_user.id,
            )
            .order_by(
                FoundItem.created_at.desc()
            )
        ).scalars().all()

        matches = []

        for lost_item in lost_items:
            for found_item in found_items:
                score, reasons = (
                    calculate_match_score(
                        lost_item,
                        found_item,
                    )
                )

                # A date and broad category alone should not be treated
                # as evidence that two items are alike. Require at least
                # one identifying attribute or shared descriptive keyword.
                has_identifying_evidence = any(
                    reason in {
                        "Same colour", "Similar colour", "Same brand", "Similar brand"
                    } or reason.startswith("Shared keywords:")
                    for reason in reasons
                )
                if score >= 55 and has_identifying_evidence:
                    matches.append(
                        {
                            "lost_item": lost_item,
                            "found_item": found_item,
                            "score": score,
                            "reasons": reasons,
                        }
                    )

        matches.sort(
            key=lambda match: (
                match["score"],
                match["found_item"].created_at,
            ),
            reverse=True,
        )

        return render_template(
            "possible_matches.html",
            lost_items=lost_items,
            matches=matches,
        )


    # -----------------------------------------------------
    # SUBMIT AN OWNERSHIP CLAIM
    # -----------------------------------------------------

    @app.route(
        "/claims/new",
        methods=["GET", "POST"],
    )
    @login_required
    def submit_claim():
        form = OwnershipClaimForm()

        available_items = db.session.execute(
            db.select(FoundItem)
            .where(
                FoundItem.status == "REPORTED_FOUND",
                FoundItem.finder_id != current_user.id,
            )
            .order_by(
                FoundItem.created_at.desc()
            )
        ).scalars().all()

        form.found_item_id.choices = [
            (
                item.id,
                (
                    f"F-{item.id}: {item.item_name} | "
                    f"{item.colour} | "
                    f"{item.location.replace('_', ' ').title()} | "
                    f"{item.found_date.strftime('%d %b %Y')}"
                ),
            )
            for item in available_items
        ]

        selected_item_id = request.args.get(
            "found_item_id",
            type=int,
        )

        available_item_ids = {
            item.id
            for item in available_items
        }

        if (
            request.method == "GET"
            and selected_item_id in available_item_ids
        ):
            form.found_item_id.data = selected_item_id

        if form.validate_on_submit():
            found_item = db.session.execute(
                db.select(FoundItem).where(
                    FoundItem.id
                    == form.found_item_id.data,
                    FoundItem.status
                    == "REPORTED_FOUND",
                    FoundItem.finder_id
                    != current_user.id,
                )
            ).scalar_one_or_none()

            if found_item is None:
                flash(
                    "The selected found item is no longer "
                    "available for an ownership claim.",
                    "error",
                )

                return redirect(
                    url_for("submit_claim")
                )

            existing_claim = db.session.execute(
                db.select(OwnershipClaim).where(
                    OwnershipClaim.claimant_id
                    == current_user.id,
                    OwnershipClaim.found_item_id
                    == found_item.id,
                    OwnershipClaim.status.in_(
                        [
                            "PENDING",
                            "APPROVED",
                        ]
                    ),
                )
            ).scalar_one_or_none()

            if existing_claim is not None:
                flash(
                    "You already have an active ownership "
                    "claim for this found item.",
                    "warning",
                )

                return redirect(
                    url_for("submit_claim")
                )

            claim = OwnershipClaim(
                claimant_id=current_user.id,
                found_item_id=found_item.id,
                ownership_details=(
                    form.ownership_details.data.strip()
                ),
                status="PENDING",
            )

            db.session.add(claim)

            try:
                db.session.commit()

            except SQLAlchemyError:
                db.session.rollback()

                app.logger.exception(
                    "Failed to save an ownership claim."
                )

                flash(
                    "The ownership claim could not be saved. "
                    "Please try again.",
                    "error",
                )

                return render_template(
                    "submit_claim.html",
                    form=form,
                    available_items=available_items,
                )

            flash(
                "Your ownership claim was submitted "
                f"successfully. Claim number: C-{claim.id}.",
                "success",
            )

            return redirect(
                url_for("dashboard")
            )

        return render_template(
            "submit_claim.html",
            form=form,
            available_items=available_items,
        )

    # -----------------------------------------------------
    # ADMINISTRATOR: VIEW OWNERSHIP CLAIMS
    # -----------------------------------------------------

    @app.get("/admin/claims")
    @login_required
    @admin_required
    def admin_claims():
        pending_claims = db.session.execute(
            db.select(OwnershipClaim)
            .where(
                OwnershipClaim.status == "PENDING"
            )
            .order_by(
                OwnershipClaim.created_at.asc()
            )
        ).scalars().all()

        reviewed_claims = db.session.execute(
            db.select(OwnershipClaim)
            .where(
                OwnershipClaim.status.in_(
                    [
                        "APPROVED",
                        "REJECTED",
                    ]
                )
            )
            .order_by(
                OwnershipClaim.updated_at.desc()
            )
            .limit(50)
        ).scalars().all()

        return render_template(
            "admin_claims.html",
            pending_claims=pending_claims,
            reviewed_claims=reviewed_claims,
        )

    # -----------------------------------------------------
    # ADMINISTRATOR: REVIEW ONE OWNERSHIP CLAIM
    # -----------------------------------------------------

    @app.route(
        "/admin/claims/<int:claim_id>",
        methods=["GET", "POST"],
    )
    @login_required
    @admin_required
    def review_claim(claim_id: int):
        claim = db.session.get(
            OwnershipClaim,
            claim_id,
        )

        if claim is None:
            abort(404)

        form = ClaimReviewForm()

        if form.validate_on_submit():
            if claim.status != "PENDING":
                flash(
                    "This claim has already been reviewed.",
                    "warning",
                )

                return redirect(
                    url_for("admin_claims")
                )

            decision = form.decision.data
            review_notes = None

            if form.review_notes.data:
                cleaned_notes = (
                    form.review_notes.data.strip()
                )

                if cleaned_notes:
                    review_notes = cleaned_notes

            if (
                decision == "REJECTED"
                and review_notes is None
            ):
                form.review_notes.errors = [
                    *form.review_notes.errors,
                    (
                        "Review notes are required when "
                        "rejecting a claim."
                    ),
                ]

                return render_template(
                    "admin_review_claim.html",
                    claim=claim,
                    form=form,
                )

            claim.status = decision
            claim.review_notes = review_notes

            affected_claims = [claim]

            if decision == "APPROVED":
                claim.found_item.status = "CLAIMED"

                competing_claims = db.session.execute(
                    db.select(OwnershipClaim).where(
                        OwnershipClaim.found_item_id
                        == claim.found_item_id,
                        OwnershipClaim.id != claim.id,
                        OwnershipClaim.status == "PENDING",
                    )
                ).scalars().all()

                for competing_claim in competing_claims:
                    competing_claim.status = "REJECTED"
                    competing_claim.review_notes = (
                        "Automatically rejected because "
                        "another ownership claim for this "
                        "item was approved."
                    )
                    affected_claims.append(competing_claim)

            for affected_claim in affected_claims:
                db.session.add(
                    build_claim_notification(
                        affected_claim,
                        affected_claim.status,
                    )
                )

            try:
                db.session.commit()

            except SQLAlchemyError:
                db.session.rollback()

                app.logger.exception(
                    "Failed to review ownership claim."
                )

                flash(
                    "The claim decision could not be saved. "
                    "Please try again.",
                    "error",
                )

                return render_template(
                    "admin_review_claim.html",
                    claim=claim,
                    form=form,
                )

            email_failures = []

            for affected_claim in affected_claims:
                email_sent, email_result = (
                    send_claim_decision_email(
                        app,
                        affected_claim,
                    )
                )

                if (
                    app.config["EMAIL_NOTIFICATIONS_ENABLED"]
                    and not email_sent
                ):
                    email_failures.append(
                        f"C-{affected_claim.id}: {email_result}"
                    )

            if decision == "APPROVED":
                flash(
                    f"Claim C-{claim.id} was approved.",
                    "success",
                )
            else:
                flash(
                    f"Claim C-{claim.id} was rejected.",
                    "success",
                )

            if email_failures:
                flash(
                    "The claim decision was saved and the "
                    "in-app notification was created, but "
                    "one or more emails could not be sent.",
                    "warning",
                )

            return redirect(
                url_for("admin_claims")
            )

        return render_template(
            "admin_review_claim.html",
            claim=claim,
            form=form,
        )

    # -----------------------------------------------------
    # LOGOUT
    # -----------------------------------------------------

    @app.post("/logout")
    @login_required
    def logout():
        logout_user()

        flash(
            "You have logged out successfully.",
            "success",
        )

        return redirect(url_for("home"))

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)