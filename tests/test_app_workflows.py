"""Isolated Flask workflow checks (no network, no production database).

Run: python -m unittest discover -s tests -v
"""
from io import BytesIO
import os
from pathlib import Path
import tempfile
import unittest

# app.py constructs a Flask app at import time. Point it at a temporary
# database *before* importing it; never use the user's local/Render database.
_TEST_TEMP = tempfile.TemporaryDirectory(prefix="pirates_workflow_")
os.environ["DATABASE_URL"] = "sqlite:///" + str(Path(_TEST_TEMP.name) / "workflows.sqlite")
os.environ["SECRET_KEY"] = "local-automated-test-secret-not-for-production"
os.environ["EMAIL_NOTIFICATIONS_ENABLED"] = "false"

from app import app, db  # noqa: E402
from models import User, LostItem, FoundItem, OwnershipClaim, Notification  # noqa: E402


PNG_BYTES = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
             b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
             b"\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00"
             b"\x03\x01\x01\x00\xc9\xfe\x92\xef\x00\x00\x00\x00IEND\xaeB`\x82")


def registration(identifier, email, kind="STUDENT"):
    return dict(identifier_type=kind, uwc_identifier=identifier,
                first_name="Test", surname="Person", email=email,
                password="StrongPass123!", confirm_password="StrongPass123!")


def lost_form():
    return dict(category="ELECTRONICS", item_name="Macbook Pro",
                description="Black laptop with distinctive silver star sticker",
                colour="Black", brand="Apple", lost_date="2026-10-10",
                location="LIBRARY", private_details="Small dent next to left USB port")


def found_form():
    return dict(category="ELECTRONICS", item_name="Macbook Pro",
                description="Black laptop with distinctive silver star sticker",
                colour="Black", brand="Apple", found_date="2026-10-11",
                location="LIBRARY", storage_location="CAMPUS_SECURITY",
                private_details="Small dent next to left USB port")


class ApplicationWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config.update(TESTING=True, WTF_CSRF_ENABLED=False,
                          UPLOAD_FOLDER=str(Path(_TEST_TEMP.name) / "uploads"))
        Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
        with app.app_context():
            db.create_all()

    @classmethod
    def tearDownClass(cls):
        with app.app_context():
            db.session.remove()
            db.drop_all()
        _TEST_TEMP.cleanup()

    def test_registration_duplicates_and_full_claim_workflow(self):
        student = app.test_client()
        staff = app.test_client()
        competitor = app.test_client()
        admin = app.test_client()
        public = app.test_client()

        self.assertEqual(student.post("/register", data=registration("STD001", "student@example.com")).status_code, 302)
        self.assertEqual(staff.post("/register", data=registration("STAFF001", "staff@example.com", "STAFF")).status_code, 302)
        self.assertEqual(competitor.post("/register", data=registration("STD002", "competitor@example.com")).status_code, 302)
        # One email and one identifier belong to *different* existing users.
        conflict = public.post("/register", data=registration("STAFF001", "student@example.com"))
        self.assertEqual(conflict.status_code, 200)
        self.assertIn(b"already uses this email", conflict.data)
        self.assertIn(b"already uses this UWC identifier", conflict.data)

        for c, email in ((student, "student@example.com"), (staff, "staff@example.com"),
                         (competitor, "competitor@example.com")):
            result = c.post("/login", data={"email": email, "password": "StrongPass123!"})
            self.assertEqual(result.status_code, 302)

        self.assertEqual(student.post("/lost-items/report", data={**lost_form(),
            "image": (BytesIO(PNG_BYTES), "laptop.png")}, content_type="multipart/form-data").status_code, 302)
        with app.app_context():
            lost_id = LostItem.query.one().id
            image_name = LostItem.query.one().image_filename
        self.assertTrue(image_name)
        image_response = student.get(f"/item-images/lost/{lost_id}")
        self.assertEqual(image_response.status_code, 200)
        image_response.close()
        self.assertEqual(public.get(f"/item-images/lost/{lost_id}").status_code, 302)
        self.assertEqual(public.get(f"/static/uploads/{image_name}").status_code, 404)

        self.assertEqual(staff.post("/found-items/report", data=found_form()).status_code, 302)
        with app.app_context():
            staff_item_id = FoundItem.query.one().id
        self.assertIn(b"Macbook Pro", student.get("/items/search").data)
        self.assertIn(b"Score:", student.get("/matches").data)

        # A broad category plus a close date must not be treated as enough
        # evidence for a possible match when the descriptions differ.
        weak_found = found_form()
        weak_found.update(item_name="Unrelated tablet", colour="Red",
                          brand="Samsung", description="Red tablet in blue case with green tag",
                          location="PARKING")
        self.assertEqual(staff.post("/found-items/report", data=weak_found).status_code, 302)
        with app.app_context():
            weak_item_id = db.session.query(FoundItem).filter_by(item_name="Unrelated tablet").one().id
        self.assertNotIn(f"F-{weak_item_id}".encode(), student.get("/matches").data)

        # Staff finder cannot claim their own found item.
        blocked_self = staff.post("/claims/new", data=dict(
            found_item_id=str(staff_item_id), ownership_details="This is definitely my laptop and here is my proof",
            declaration="y"))
        self.assertEqual(blocked_self.status_code, 200)
        with app.app_context():
            self.assertEqual(db.session.query(OwnershipClaim).count(), 0)

        self.assertEqual(student.post("/claims/new", data=dict(
            found_item_id=str(staff_item_id), ownership_details="This is my laptop with a silver star sticker",
            declaration="y")).status_code, 302)
        duplicate = student.post("/claims/new", data=dict(
            found_item_id=str(staff_item_id), ownership_details="This is my laptop with a silver star sticker",
            declaration="y"))
        self.assertEqual(duplicate.status_code, 302)
        with app.app_context():
            self.assertEqual(db.session.query(OwnershipClaim).count(), 1)
        self.assertEqual(competitor.post("/claims/new", data=dict(
            found_item_id=str(staff_item_id), ownership_details="I have documents and proof for ownership too",
            declaration="y")).status_code, 302)

        # User's own found report must not generate a claimable match.
        self.assertEqual(student.post("/found-items/report", data=found_form()).status_code, 302)
        with app.app_context():
            self_found_id = db.session.query(FoundItem).filter_by(finder_id=1).one().id
        self.assertNotIn(f"F-{self_found_id}".encode(), student.get("/matches").data)

        self.assertEqual(student.get("/admin/claims").status_code, 403)
        with app.app_context():
            admin_user = User(uwc_identifier="ADMIN01", identifier_type="STAFF",
                              first_name="Admin", surname="Test", email="admin@example.com", role="ADMIN")
            admin_user.set_password("StrongPass123!")
            db.session.add(admin_user)
            db.session.commit()
            original_claim_id = db.session.query(OwnershipClaim).filter_by(claimant_id=1).one().id
        self.assertEqual(admin.post("/login", data={"email": "admin@example.com", "password": "StrongPass123!"}).status_code, 302)
        self.assertEqual(admin.get("/admin/claims").status_code, 200)
        self.assertEqual(admin.post(f"/admin/claims/{original_claim_id}", data={
            "decision": "APPROVED", "review_notes": "Details confirmed"}).status_code, 302)
        with app.app_context():
            claims = db.session.query(OwnershipClaim).order_by(OwnershipClaim.id).all()
            self.assertEqual([c.status for c in claims], ["APPROVED", "REJECTED"])
            self.assertEqual(db.session.get(FoundItem, staff_item_id).status, "CLAIMED")
            self.assertEqual(db.session.query(Notification).count(), 2)
        self.assertIn(b"Ownership claim approved", student.get("/dashboard").data)
        self.assertIn(b"Ownership claim rejected", competitor.get("/dashboard").data)

        # A legacy sensitive photo is viewable by the reporter/admin only,
        # not by other signed-in users who know its URL.
        with app.app_context():
            staff_user = db.session.query(User).filter_by(email="staff@example.com").one()
            sensitive_report = FoundItem(
                finder_id=staff_user.id, category="STUDENT_CARD", item_name="UWC card",
                description="A found card with a distinctive blue lanyard",
                colour="Blue", brand=None, found_date=__import__("datetime").date(2026, 10, 11),
                location="LIBRARY", image_filename=image_name,
                private_details="Card back has a small scratch",
                storage_location="CAMPUS_SECURITY", status="REPORTED_FOUND"
            )
            db.session.add(sensitive_report)
            db.session.commit()
            sensitive_id = sensitive_report.id
        self.assertEqual(student.get(f"/item-images/found/{sensitive_id}").status_code, 403)
        self.assertEqual(public.get(f"/item-images/found/{sensitive_id}").status_code, 302)
        sensitive_owner_response = staff.get(f"/item-images/found/{sensitive_id}")
        self.assertEqual(sensitive_owner_response.status_code, 200)
        sensitive_owner_response.close()

        # Image content and privacy validation, without adding an item.
        bad_image = student.post("/lost-items/report", data={**lost_form(),
            "image": (BytesIO(b"<script>fake</script>"), "fake.png")}, content_type="multipart/form-data")
        self.assertEqual(bad_image.status_code, 200)
        self.assertIn(b"valid image header", bad_image.data)
        sensitive = student.post("/lost-items/report", data={**lost_form(),
            "category": "STUDENT_CARD", "image": (BytesIO(PNG_BYTES), "studentcard.png")},
            content_type="multipart/form-data")
        self.assertEqual(sensitive.status_code, 200)
        self.assertIn(b"For privacy, do not upload", sensitive.data)

    def test_csrf_rejects_missing_token(self):
        app.config["WTF_CSRF_ENABLED"] = True
        try:
            response = app.test_client().post("/register", data=registration("CSRF002", "csrf@example.com"))
            self.assertEqual(response.status_code, 400)
        finally:
            app.config["WTF_CSRF_ENABLED"] = False


if __name__ == "__main__":
    unittest.main()
