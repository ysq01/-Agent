from sqlalchemy import select

from app.models import PolicyDocument
from app.services.admin_auth import create_admin_user
from app.services.policy_knowledge import search_policy


ADMIN_PASSWORD = "correct-password"


def login_admin(
    tools_client,
    tools_db_session,
    username: str = "stage14-admin",
) -> str:
    create_admin_user(
        tools_db_session,
        username=username,
        password=ADMIN_PASSWORD,
    )
    response = tools_client.post(
        "/api/admin/login",
        json={"username": username, "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200
    return str(response.json()["token"])


def create_draft_policy(
    tools_client,
    token: str,
    title: str = "大件商品上门取件规则",
    content: str = "大件商品支持预约上门取件。",
) -> int:
    response = tools_client.post(
        "/api/admin/policies",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": title, "content": content},
    )
    assert response.status_code == 201
    return int(response.json()["id"])


def test_admin_policy_api_requires_login(tools_client) -> None:
    response = tools_client.get("/api/admin/policies")

    assert response.status_code == 401


def test_admin_can_create_and_edit_draft_policy(
    tools_client,
    tools_db_session,
) -> None:
    token = login_admin(tools_client, tools_db_session)

    created = tools_client.post(
        "/api/admin/policies",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "title": "大件商品上门取件规则",
            "content": "大件商品支持预约上门取件。",
        },
    )
    assert created.status_code == 201
    policy_id = created.json()["id"]
    assert created.json()["status"] == "draft"
    assert created.json()["version"] == 1

    updated = tools_client.patch(
        f"/api/admin/policies/{policy_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "title": "大件商品上门取件规则",
            "content": "大件商品支持预约上门取件，需提前一天。",
        },
    )

    assert updated.status_code == 200
    assert "提前一天" in updated.json()["content"]


def test_publish_and_disable_trigger_rebuild(
    tools_client,
    tools_db_session,
    monkeypatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        "app.services.admin_policies.rebuild_knowledge_base",
        lambda session: calls.append("rebuild"),
    )
    token = login_admin(tools_client, tools_db_session)
    policy_id = create_draft_policy(tools_client, token)

    published = tools_client.post(
        f"/api/admin/policies/{policy_id}/publish",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert published.status_code == 200
    assert published.json()["policy"]["status"] == "published"
    assert calls == ["rebuild"]

    disabled = tools_client.post(
        f"/api/admin/policies/{policy_id}/disable",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert disabled.status_code == 200
    assert disabled.json()["policy"]["status"] == "disabled"
    assert calls == ["rebuild", "rebuild"]


def test_editing_published_policy_creates_replacement_draft(
    tools_client,
    tools_db_session,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.services.admin_policies.rebuild_knowledge_base",
        lambda session: None,
    )
    token = login_admin(tools_client, tools_db_session)
    policy_id = create_draft_policy(tools_client, token)
    tools_client.post(
        f"/api/admin/policies/{policy_id}/publish",
        headers={"Authorization": f"Bearer {token}"},
    )

    response = tools_client.patch(
        f"/api/admin/policies/{policy_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "新版政策", "content": "新版政策内容"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] != policy_id
    assert data["status"] == "draft"
    assert data["version"] == 2
    assert data["supersedes_policy_id"] == policy_id


def test_publishing_replacement_disables_superseded_policy(
    tools_client,
    tools_db_session,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.services.admin_policies.rebuild_knowledge_base",
        lambda session: None,
    )
    token = login_admin(tools_client, tools_db_session)
    policy_id = create_draft_policy(tools_client, token)
    tools_client.post(
        f"/api/admin/policies/{policy_id}/publish",
        headers={"Authorization": f"Bearer {token}"},
    )
    replacement = tools_client.patch(
        f"/api/admin/policies/{policy_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "新版政策", "content": "新版政策内容"},
    ).json()

    published = tools_client.post(
        f"/api/admin/policies/{replacement['id']}/publish",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert published.status_code == 200
    old_policy = tools_db_session.scalar(
        select(PolicyDocument).where(PolicyDocument.id == policy_id)
    )
    new_policy = tools_db_session.scalar(
        select(PolicyDocument).where(PolicyDocument.id == replacement["id"])
    )
    assert old_policy is not None
    assert new_policy is not None
    assert old_policy.status == "disabled"
    assert new_policy.status == "published"


def test_customer_knowledge_documents_show_only_published_admin_policies(
    tools_client,
    tools_db_session,
    monkeypatch,
) -> None:
    token = login_admin(tools_client, tools_db_session)
    draft_id = create_draft_policy(
        tools_client,
        token,
        title="后台草稿政策",
        content="草稿不应展示。",
    )
    monkeypatch.setattr(
        "app.services.admin_policies.rebuild_knowledge_base",
        lambda session: None,
    )

    before = tools_client.get("/api/knowledge/documents").json()
    before_titles = {item["policy_title"] for item in before["documents"]}
    assert "七天无理由退货规则" in before_titles
    assert "后台草稿政策" not in before_titles

    tools_client.post(
        f"/api/admin/policies/{draft_id}/publish",
        headers={"Authorization": f"Bearer {token}"},
    )
    after = tools_client.get("/api/knowledge/documents").json()
    after_titles = {item["policy_title"] for item in after["documents"]}
    assert "七天无理由退货规则" in after_titles
    assert "后台草稿政策" in after_titles


def test_policy_search_uses_published_admin_policies_and_excludes_disabled(
    tools_db_session,
    monkeypatch,
) -> None:
    tools_db_session.add(
        PolicyDocument(
            title="后台赔付政策",
            content="青柠破损可以申请补偿。",
            status="published",
            version=1,
            source="admin",
        )
    )
    tools_db_session.commit()

    monkeypatch.setattr(
        "app.services.policy_knowledge.make_qdrant_client",
        lambda: FakeMissingCollectionClient(),
    )
    matches = search_policy(
        "后台赔付政策 青柠破损怎么补偿",
        session=tools_db_session,
    )
    assert any(match.policy_title == "后台赔付政策" for match in matches)

    policy = tools_db_session.scalar(
        select(PolicyDocument).where(PolicyDocument.title == "后台赔付政策")
    )
    assert policy is not None
    policy.status = "disabled"
    tools_db_session.commit()

    matches = search_policy(
        "后台赔付政策 青柠破损怎么补偿",
        session=tools_db_session,
    )
    assert all(match.policy_title != "后台赔付政策" for match in matches)


class FakeMissingCollectionClient:
    def collection_exists(self, collection_name: str) -> bool:
        del collection_name
        return False
