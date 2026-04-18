import os
import pytest


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "d3s_system.settings")
os.environ.setdefault("SECRET_KEY", "test-secret-key-only-for-testing")
os.environ.setdefault("DEBUG", "1")


@pytest.fixture
def usuario(db):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    return User.objects.create_user(
        username="testuser",
        password="testpass123",
        first_name="Test",
        last_name="User",
    )


@pytest.fixture
def admin_user(db):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    return User.objects.create_superuser(
        username="admin",
        password="adminpass123",
        email="admin@d3s.com",
    )


@pytest.fixture
def client_autenticado(client, usuario):
    client.login(username="testuser", password="testpass123")
    return client
