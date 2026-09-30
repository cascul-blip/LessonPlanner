import pytest

from lessonplanner.db import Database


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "lessonplanner.db")
    yield database
    database.close()
