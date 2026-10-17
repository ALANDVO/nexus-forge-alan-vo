import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(db_path=str(tmp_path / "test.sqlite"))
    with TestClient(app) as c:
        yield c
    app.state.storage.close()


@pytest.fixture
def plan_text():
    return (
        "# Ship log\n\n"
        "- [ ] Parse the monolithic plan into tasks\n"
        "- [x] Classify task outcomes from captured logs\n"
        "- [ ] Export the ledger to CSV\n"
    )