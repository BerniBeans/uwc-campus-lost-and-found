"""Isolated SQLite regression test for the Step 6 identifier migration.

Run: python -m unittest discover -s tests -v
This exercises the actual Alembic revision files without starting Flask.
"""

import importlib.util
import unittest
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text


VERSIONS = Path(__file__).resolve().parents[1] / "migrations" / "versions"
MIGRATIONS = [
    "1f52ca30bb12_create_initial_lost_and_found_tables.py",
    "301c4ae713c2_add_ownership_claims.py",
    "6a3e9b1c4d20_add_notifications.py",
    "c92410bfc0d1_support_student_and_staff_identifiers.py",
]


def load_migration(filename):
    spec = importlib.util.spec_from_file_location(
        filename.replace(".", "_"), VERSIONS / filename
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def migrate(connection, module, direction="upgrade"):
    context = MigrationContext.configure(connection)
    with Operations.context(context):
        getattr(module, direction)()


class IdentifierMigrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.revisions = [load_migration(path) for path in MIGRATIONS]

    def setUp(self):
        self.engine = create_engine("sqlite://")
        self.connection = self.engine.connect()
        for module in self.revisions[:3]:
            migrate(self.connection, module)

    def tearDown(self):
        self.connection.close()
        self.engine.dispose()

    def test_new_account_schema_can_record_staff(self):
        migrate(self.connection, self.revisions[-1])
        schema = inspect(self.connection)
        columns = {entry["name"]: entry for entry in schema.get_columns("users")}
        self.assertIn("uwc_identifier", columns)
        self.assertIn("identifier_type", columns)
        self.assertNotIn("student_number", columns)
        self.assertFalse(columns["identifier_type"]["nullable"])
        self.assertIn(
            "ix_users_uwc_identifier",
            {entry["name"] for entry in schema.get_indexes("users")},
        )
        self.connection.execute(
            text("""INSERT INTO users
                (uwc_identifier,identifier_type,first_name,surname,email,
                 password_hash,role,is_active,created_at)
                VALUES ('STAFF123','STAFF','Test','Staff',
                 'staff@example.com','dummy','USER',1,CURRENT_TIMESTAMP)""")
        )
        self.assertEqual(
            self.connection.scalar(text("SELECT identifier_type FROM users")),
            "STAFF",
        )

    def test_upgrade_preserves_users_and_related_reports(self):
        self.connection.execute(
            text("""INSERT INTO users
                (id,student_number,first_name,surname,email,
                 password_hash,role,is_active,created_at)
                VALUES (10,'4429947','Test','Student',
                'test@example.com','dummy','USER',1,CURRENT_TIMESTAMP)""")
        )
        self.connection.execute(
            text("""INSERT INTO lost_items
                (id,reporter_id,category,item_name,description,colour,
                 lost_date,location,private_details,status,created_at,updated_at)
                VALUES (20,10,'BAG','Backpack','Test item','Blue',
                '2026-10-11','LIBRARY','Private','REPORTED_LOST',
                CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)""")
        )
        migrate(self.connection, self.revisions[-1])
        self.assertEqual(
            self.connection.execute(
                text("SELECT uwc_identifier,identifier_type FROM users WHERE id=10")
            ).one(),
            ("4429947", "STUDENT"),
        )
        self.assertEqual(
            self.connection.scalar(text("SELECT reporter_id FROM lost_items WHERE id=20")),
            10,
        )
        migrate(self.connection, self.revisions[-1], "downgrade")
        self.assertEqual(
            self.connection.scalar(text("SELECT student_number FROM users WHERE id=10")),
            "4429947",
        )


if __name__ == "__main__":
    unittest.main()
