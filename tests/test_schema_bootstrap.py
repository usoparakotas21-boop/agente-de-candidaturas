import unittest

from app import main


class _Result:
    def __init__(self, values=(), scalar_value=None):
        self._values = tuple(values)
        self._scalar_value = scalar_value

    def scalars(self):
        return iter(self._values)

    def scalar(self):
        return self._scalar_value


class _CatalogSession:
    def __init__(self, *, columns=(), rls_enabled=False):
        self.columns = columns
        self.rls_enabled = rls_enabled
        self.statements = []

    def execute(self, statement, params=None):
        sql = str(statement)
        self.statements.append((sql, params))
        if "information_schema.columns" in sql:
            return _Result(values=self.columns)
        if "pg_class" in sql and "relrowsecurity" in sql:
            return _Result(scalar_value=self.rls_enabled)
        raise AssertionError(f"consulta inesperada: {sql}")


class SchemaBootstrapTests(unittest.TestCase):
    def test_existing_columns_are_read_from_catalog_before_any_ddl(self):
        session = _CatalogSession(columns=("id", "cover_letter_text"))

        self.assertEqual(
            main._postgres_table_columns(session, "applications"),
            {"id", "cover_letter_text"},
        )
        sql, params = session.statements[0]
        self.assertIn("information_schema.columns", sql)
        self.assertEqual(params, {"table_name": "applications"})
        self.assertNotIn("ALTER TABLE", sql)

    def test_rls_state_is_checked_before_enable_ddl(self):
        session = _CatalogSession(rls_enabled=True)

        self.assertTrue(main._postgres_rls_enabled(session, "applications"))
        sql, params = session.statements[0]
        self.assertIn("pg_class", sql)
        self.assertEqual(params, {"table_name": "applications"})
        self.assertNotIn("ALTER TABLE", sql)


if __name__ == "__main__":
    unittest.main()
