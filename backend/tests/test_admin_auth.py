from datetime import UTC, datetime

from sqlalchemy import select

from app.models import AdminSession
from app.services.admin_auth import (
    authenticate_admin,
    create_admin_user,
    get_admin_by_token,
    revoke_admin_session,
    verify_password,
)


def test_admin_password_is_hashed_and_login_returns_plain_token(
    tools_db_session,
) -> None:
    admin = create_admin_user(
        tools_db_session,
        username="stage14-admin",
        password="correct-password",
    )

    assert admin.password_hash != "correct-password"
    assert admin.password_salt != "correct-password"
    assert verify_password(
        "correct-password",
        admin.password_hash,
        admin.password_salt,
    )

    login = authenticate_admin(
        tools_db_session,
        username="stage14-admin",
        password="correct-password",
    )

    assert login is not None
    assert login.token
    assert login.role == "admin"
    assert login.expires_at > datetime.now(UTC)

    stored_session = tools_db_session.scalar(select(AdminSession))
    assert stored_session is not None
    assert stored_session.token_hash != login.token

    current_admin = get_admin_by_token(tools_db_session, login.token)
    assert current_admin is not None
    assert current_admin.username == "stage14-admin"


def test_admin_login_rejects_wrong_password(tools_db_session) -> None:
    create_admin_user(
        tools_db_session,
        username="stage14-admin",
        password="correct-password",
    )

    assert (
        authenticate_admin(
            tools_db_session,
            username="stage14-admin",
            password="wrong-password",
        )
        is None
    )


def test_inactive_admin_cannot_login(tools_db_session) -> None:
    admin = create_admin_user(
        tools_db_session,
        username="stage14-admin",
        password="correct-password",
    )
    admin.is_active = False
    tools_db_session.commit()

    assert (
        authenticate_admin(
            tools_db_session,
            username="stage14-admin",
            password="correct-password",
        )
        is None
    )


def test_logout_revokes_admin_session(tools_db_session) -> None:
    create_admin_user(
        tools_db_session,
        username="stage14-admin",
        password="correct-password",
    )
    login = authenticate_admin(
        tools_db_session,
        username="stage14-admin",
        password="correct-password",
    )
    assert login is not None

    assert revoke_admin_session(tools_db_session, login.token) is True
    assert get_admin_by_token(tools_db_session, login.token) is None


def test_admin_login_api_returns_session_token(
    tools_client,
    tools_db_session,
) -> None:
    create_admin_user(
        tools_db_session,
        username="stage14-admin",
        password="correct-password",
    )

    response = tools_client.post(
        "/api/admin/login",
        json={"username": "stage14-admin", "password": "correct-password"},
    )

    assert response.status_code == 200
    data = response.json()
    assert set(data) == {"token", "role", "expires_at"}
    assert data["role"] == "admin"
    assert data["token"]


def test_admin_login_api_rejects_bad_credentials(
    tools_client,
    tools_db_session,
) -> None:
    create_admin_user(
        tools_db_session,
        username="stage14-admin",
        password="correct-password",
    )

    response = tools_client.post(
        "/api/admin/login",
        json={"username": "stage14-admin", "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert "账号或密码" in response.json()["detail"]


def test_admin_logout_api_revokes_token(
    tools_client,
    tools_db_session,
) -> None:
    create_admin_user(
        tools_db_session,
        username="stage14-admin",
        password="correct-password",
    )
    login = authenticate_admin(
        tools_db_session,
        username="stage14-admin",
        password="correct-password",
    )
    assert login is not None

    response = tools_client.post(
        "/api/admin/logout",
        headers={"Authorization": f"Bearer {login.token}"},
    )

    assert response.status_code == 200
    assert get_admin_by_token(tools_db_session, login.token) is None
