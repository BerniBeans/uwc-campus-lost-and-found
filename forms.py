from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField

from wtforms import (
    BooleanField,
    DateField,
    PasswordField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
    TimeField,
)

from wtforms.validators import (
    DataRequired,
    Email,
    EqualTo,
    Length,
    Optional,
)


class RegistrationForm(FlaskForm):
    identifier_type = SelectField(
        "Account type",
        choices=[
            ("", "Select an account type"),
            ("STUDENT", "Student"),
            ("STAFF", "Staff member"),
        ],
        validators=[
            DataRequired(message="Choose student or staff member."),
        ],
    )

    uwc_identifier = StringField(
        "UWC student or staff number",
        validators=[
            DataRequired(message="Enter your UWC identifier."),
            Length(
                min=3,
                max=30,
                message=(
                    "UWC identifier must contain "
                    "3 to 30 characters."
                ),
            ),
        ],
    )

    first_name = StringField(
        "First name",
        validators=[
            DataRequired(message="Enter your first name."),
            Length(
                min=2,
                max=100,
                message=(
                    "First name must contain "
                    "2 to 100 characters."
                ),
            ),
        ],
    )

    surname = StringField(
        "Surname",
        validators=[
            DataRequired(message="Enter your surname."),
            Length(
                min=2,
                max=100,
                message=(
                    "Surname must contain "
                    "2 to 100 characters."
                ),
            ),
        ],
    )

    email = StringField(
        "Email address",
        validators=[
            DataRequired(message="Enter your email address."),
            Email(message="Enter a valid email address."),
            Length(max=255),
        ],
    )

    password = PasswordField(
        "Password",
        validators=[
            DataRequired(message="Enter a password."),
            Length(
                min=8,
                max=128,
                message=(
                    "Password must contain at least "
                    "8 characters."
                ),
            ),
        ],
    )

    confirm_password = PasswordField(
        "Confirm password",
        validators=[
            DataRequired(
                message="Enter the password again."
            ),
            EqualTo(
                "password",
                message="The passwords do not match.",
            ),
        ],
    )

    submit = SubmitField("Create account")


class LoginForm(FlaskForm):
    email = StringField(
        "Email address",
        validators=[
            DataRequired(message="Enter your email address."),
            Email(message="Enter a valid email address."),
        ],
    )

    password = PasswordField(
        "Password",
        validators=[
            DataRequired(message="Enter your password."),
        ],
    )

    remember = BooleanField("Remember me")

    submit = SubmitField("Log in")


class LogoutForm(FlaskForm):
    """Secure CSRF-protected logout form."""

    pass


class LostItemForm(FlaskForm):
    category = SelectField(
        "Item category",
        choices=[
            ("", "Select a category"),
            ("BAG", "Bag"),
            ("BOOKS", "Books and stationery"),
            ("CLOTHING", "Clothing"),
            ("ELECTRONICS", "Electronics"),
            (
                "IDENTIFICATION",
                "Identification document",
            ),
            ("JEWELLERY", "Jewellery"),
            ("KEYS", "Keys"),
            ("PHONE", "Mobile phone"),
            ("WALLET", "Money or wallet"),
            ("STUDENT_CARD", "Student card"),
            ("OTHER", "Other"),
        ],
        validators=[
            DataRequired(
                message="Select an item category."
            ),
        ],
    )

    item_name = StringField(
        "Item name",
        validators=[
            DataRequired(
                message="Enter the name of the item."
            ),
            Length(
                min=2,
                max=150,
                message=(
                    "Item name must contain "
                    "2 to 150 characters."
                ),
            ),
        ],
    )

    description = TextAreaField(
        "Public description",
        validators=[
            DataRequired(
                message="Describe the lost item."
            ),
            Length(
                min=10,
                max=1000,
                message=(
                    "Description must contain "
                    "10 to 1000 characters."
                ),
            ),
        ],
    )

    colour = StringField(
        "Colour",
        validators=[
            DataRequired(
                message="Enter the item's colour."
            ),
            Length(max=50),
        ],
    )

    brand = StringField(
        "Brand, if applicable",
        validators=[
            Optional(),
            Length(max=100),
        ],
    )

    lost_date = DateField(
        "Date lost",
        validators=[
            DataRequired(
                message=(
                    "Select the date the item was lost."
                )
            ),
        ],
    )

    lost_time = TimeField(
        "Approximate time lost",
        validators=[
            Optional(),
        ],
    )

    location = SelectField(
        "Last known location",
        choices=[
            ("", "Select a location"),
            ("LIBRARY", "Library"),
            ("LECTURE_HALL", "Lecture hall"),
            (
                "COMPUTER_LAB",
                "Computer laboratory",
            ),
            ("CAFETERIA", "Cafeteria"),
            ("RESIDENCE", "Residence"),
            ("SPORTS_CENTRE", "Sports centre"),
            (
                "ADMIN_BUILDING",
                "Administration building",
            ),
            ("PARKING", "Parking area"),
            ("SHUTTLE", "Campus shuttle"),
            ("OTHER", "Other"),
        ],
        validators=[
            DataRequired(
                message=(
                    "Select the last known location."
                )
            ),
        ],
    )

    image = FileField(
        "Item picture (optional)",
        validators=[
            FileAllowed(
                ["jpg", "jpeg", "png", "webp"],
                "Only JPG, JPEG, PNG and WEBP images are allowed.",
            ),
        ],
    )

    private_details = TextAreaField(
        "Private identifying details",
        validators=[
            DataRequired(
                message=(
                    "Enter identifying details that "
                    "only the owner would know."
                )
            ),
            Length(
                min=5,
                max=1000,
                message=(
                    "Private details must contain "
                    "5 to 1000 characters."
                ),
            ),
        ],
    )

    submit = SubmitField(
        "Submit lost-item report"
    )


class FoundItemForm(FlaskForm):
    category = SelectField(
        "Item category",
        choices=[
            ("", "Select a category"),
            ("BAG", "Bag"),
            ("BOOKS", "Books and stationery"),
            ("CLOTHING", "Clothing"),
            ("ELECTRONICS", "Electronics"),
            (
                "IDENTIFICATION",
                "Identification document",
            ),
            ("JEWELLERY", "Jewellery"),
            ("KEYS", "Keys"),
            ("PHONE", "Mobile phone"),
            ("WALLET", "Money or wallet"),
            ("STUDENT_CARD", "Student card"),
            ("OTHER", "Other"),
        ],
        validators=[
            DataRequired(
                message="Select an item category."
            ),
        ],
    )

    item_name = StringField(
        "Item name",
        validators=[
            DataRequired(
                message="Enter the name of the item."
            ),
            Length(
                min=2,
                max=150,
                message=(
                    "Item name must contain "
                    "2 to 150 characters."
                ),
            ),
        ],
    )

    description = TextAreaField(
        "Public description",
        validators=[
            DataRequired(
                message="Describe the found item."
            ),
            Length(
                min=10,
                max=1000,
                message=(
                    "Description must contain "
                    "10 to 1000 characters."
                ),
            ),
        ],
    )

    colour = StringField(
        "Colour",
        validators=[
            DataRequired(
                message="Enter the item's colour."
            ),
            Length(max=50),
        ],
    )

    brand = StringField(
        "Brand, if applicable",
        validators=[
            Optional(),
            Length(max=100),
        ],
    )

    found_date = DateField(
        "Date found",
        validators=[
            DataRequired(
                message=(
                    "Select the date the item was found."
                )
            ),
        ],
    )

    found_time = TimeField(
        "Approximate time found",
        validators=[
            Optional(),
        ],
    )

    location = SelectField(
        "Location where the item was found",
        choices=[
            ("", "Select a location"),
            ("LIBRARY", "Library"),
            ("LECTURE_HALL", "Lecture hall"),
            (
                "COMPUTER_LAB",
                "Computer laboratory",
            ),
            ("CAFETERIA", "Cafeteria"),
            ("RESIDENCE", "Residence"),
            ("SPORTS_CENTRE", "Sports centre"),
            (
                "ADMIN_BUILDING",
                "Administration building",
            ),
            ("PARKING", "Parking area"),
            ("SHUTTLE", "Campus shuttle"),
            ("OTHER", "Other"),
        ],
        validators=[
            DataRequired(
                message=(
                    "Select where the item was found."
                )
            ),
        ],
    )

    image = FileField(
        "Item picture (optional)",
        validators=[
            FileAllowed(
                ["jpg", "jpeg", "png", "webp"],
                "Only JPG, JPEG, PNG and WEBP images are allowed.",
            ),
        ],
    )

    private_details = TextAreaField(
        "Private identifying details",
        validators=[
            DataRequired(
                message=(
                    "Enter hidden details that can "
                    "help verify the correct owner."
                )
            ),
            Length(
                min=5,
                max=1000,
                message=(
                    "Private details must contain "
                    "5 to 1000 characters."
                ),
            ),
        ],
    )

    storage_location = SelectField(
        "Current storage location",
        choices=[
            ("", "Select a storage location"),
            (
                "CAMPUS_SECURITY",
                "Campus security office",
            ),
            (
                "LIBRARY_DESK",
                "Library information desk",
            ),
            (
                "FACULTY_OFFICE",
                "Faculty office",
            ),
            (
                "RESIDENCE_RECEPTION",
                "Residence reception",
            ),
            (
                "OTHER",
                "Other secure location",
            ),
        ],
        validators=[
            DataRequired(
                message=(
                    "Select where the item is "
                    "currently stored."
                )
            ),
        ],
    )

    submit = SubmitField(
        "Submit found-item report"
    )


class OwnershipClaimForm(FlaskForm):
    """Form for claiming ownership of a found item."""

    found_item_id = SelectField(
        "Found-item report",
        coerce=int,
        validators=[
            DataRequired(),
        ],
    )

    ownership_details = TextAreaField(
        "Private ownership details",
        validators=[
            DataRequired(),
            Length(
                min=20,
                max=1000,
            ),
        ],
    )

    declaration = BooleanField(
        (
            "I confirm that I honestly believe this item "
            "belongs to me."
        ),
        validators=[
            DataRequired(
                message=(
                    "You must confirm the ownership "
                    "declaration."
                )
            ),
        ],
    )

    submit = SubmitField(
        "Submit ownership claim"
    )  

#
class ClaimReviewForm(FlaskForm):
    """Form used by an administrator to review a claim."""

    decision = SelectField(
        "Decision",
        choices=[
            ("", "Select a decision"),
            ("APPROVED", "Approve claim"),
            ("REJECTED", "Reject claim"),
        ],
        validators=[
            DataRequired(
                message="Please select a decision."
            ),
        ],
    )

    review_notes = TextAreaField(
        "Administrator review notes",
        validators=[
            Optional(),
            Length(max=1000),
        ],
    )

    submit = SubmitField("Save decision")

class NotificationReadForm(FlaskForm):
    """CSRF-protected form for marking a notification as read."""

    pass
