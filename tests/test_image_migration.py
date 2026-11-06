"""Verify the image-persistence Alembic migration and old-row preservation.

Run: python -m unittest discover -s tests -p test_image_migration.py -v
"""
import importlib.util
import unittest
from pathlib import Path
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text

VERSIONS = Path(__file__).resolve().parents[1] / "migrations" / "versions"
REVISIONS = [
    "1f52ca30bb12_create_initial_lost_and_found_tables.py",
    "301c4ae713c2_add_ownership_claims.py",
    "6a3e9b1c4d20_add_notifications.py",
    "c92410bfc0d1_support_student_and_staff_identifiers.py",
    "d3f821bb90e2_persist_item_images.py",
]


def run_revision(connection, filename, direction="upgrade"):
    spec = importlib.util.spec_from_file_location(filename[:-3], VERSIONS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with Operations.context(MigrationContext.configure(connection)):
        getattr(module, direction)()


class ImagePersistenceMigrationTest(unittest.TestCase):
    def test_new_binary_columns_keep_existing_report_data(self):
        engine = create_engine("sqlite://")
        with engine.begin() as connection:
            for revision in REVISIONS[:-1]:
                run_revision(connection, revision)
            connection.execute(text("""INSERT INTO users
                (id, uwc_identifier, identifier_type, first_name, surname, email,
                 password_hash, role, is_active, created_at)
                VALUES (1,'S01','STUDENT','A','B','a@example.com','x','USER',1,CURRENT_TIMESTAMP)"""))
            connection.execute(text("""INSERT INTO lost_items
                (id, reporter_id, category, item_name, description, colour,
                 lost_date, location, image_filename, private_details, status,
                 created_at, updated_at)
                VALUES (10,1,'ELECTRONICS','Calculator','Test','Black',
                 '2026-10-10','LIBRARY','legacy.png','Secret','REPORTED_LOST',
                 CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"""))
            run_revision(connection, REVISIONS[-1])
            for table in ("lost_items", "found_items"):
                self.assertIn("image_data", {
                    entry["name"] for entry in inspect(connection).get_columns(table)
                })
            row = connection.execute(text(
                "SELECT image_filename, image_data FROM lost_items WHERE id=10"
            )).one()
            self.assertEqual(row, ("legacy.png", None))
            image = b"\x89PNG\r\n\x1a\ncustom-test-bytes"
            connection.execute(text(
                "UPDATE lost_items SET image_data=:img WHERE id=10"
            ), {"img": image})
            self.assertEqual(connection.scalar(text(
                "SELECT image_data FROM lost_items WHERE id=10"
            )), image)
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
