import pytest
import jwt
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import json
import time
import os

from app.main import app
from app.models import Base, NotificationTemplate, TemplateVersion
from app.database import get_db
from app.redis_client import get_redis_client
from app.dependencies.prompt_admin_authorization import require_prompt_admin

os.environ["JWT_SECRET"] = "test_secret"
os.environ["JWT_ALGORITHM"] = "HS256"

# Test DB Setup
engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class FakeRedis:
    def __init__(self):
        self.data = {}
        self.fail_mode = False
    def get(self, key):
        if self.fail_mode: raise Exception("Redis down")
        return self.data.get(key)
    def setex(self, key, ttl, value):
        if self.fail_mode: raise Exception("Redis down")
        self.data[key] = value
    def incr(self, key, amount=1):
        if self.fail_mode: raise Exception("Redis down")
        v = int(self.data.get(key, 0)) + amount
        self.data[key] = v
        return v
    def delete(self, key):
        if self.fail_mode: raise Exception("Redis down")
        self.data.pop(key, None)

def create_test_token(actor_id="test_admin", tenant_id="tenant-1", roles=["super_admin"]):
    token = jwt.encode(
        {"sub": actor_id, "tenant_id": tenant_id, "roles": roles, "exp": 9999999999},
        "test_secret",
        algorithm="HS256"
    )
    return token

@pytest.fixture(scope="function")
def db():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)

@pytest.fixture(scope="function")
def fake_redis():
    return FakeRedis()

@pytest.fixture(scope="function")
def client(db, fake_redis):
    def override_get_db():
        try:
            yield db
        finally:
            pass
    
    def override_get_redis_client():
        return fake_redis
    
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis_client] = override_get_redis_client
    
    # We do NOT override require_prompt_admin globally. We test with real JWTs.
    
    with TestClient(app) as c:
        yield c
        
    app.dependency_overrides.clear()


# Helper to create a prompt
def create_prompt(client, token, payload=None):
    if not payload:
        payload = {
            "name": "Test Prompt",
            "agent_type": "CommsAgent",
            "channel": "sms",
            "language": "en",
            "status": "assigned",
            "body": "Body {{ var }}",
            "variables": ["var"]
        }
    return client.post("/admin/prompts", json=payload, headers={"Authorization": f"Bearer {token}"})


def test_initial_complete_snapshot(client, db):
    token = create_test_token()
    res = create_prompt(client, token)
    assert res.status_code == 201
    data = res.json()
    
    # Check version snapshot
    version = db.query(TemplateVersion).filter_by(template_id=data["id"]).first()
    assert version is not None
    assert version.version_number == 1
    assert version.name == "Test Prompt"
    assert version.agent_type == "CommsAgent"
    assert version.channel == "sms"
    assert version.locale == "en"
    assert version.format == "text"
    assert version.variables == ["var"]
    assert version.body_template == "Body {{ var }}"
    assert version.created_by == "test_admin"
    assert version.is_active is True
    assert version.is_deleted is False

def test_author_cannot_be_spoofed(client, db):
    token = create_test_token(actor_id="real_actor")
    payload = {
        "name": "Test Prompt",
        "agent_type": "CommsAgent",
        "channel": "sms",
        "language": "en",
        "status": "assigned",
        "body": "Body",
        "variables": [],
        "created_by": "hacker" # Attempt to spoof
    }
    res = client.post("/admin/prompts", json=payload, headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 400 # Forbid extra fields

def test_cache_invalidation_lifecycle(client, fake_redis, db):
    token = create_test_token()
    
    def get_gen():
        import hashlib
        tenant_hash = hashlib.sha256("tenant-1".encode('utf-8')).hexdigest()
        val = fake_redis.get(f"prompt_gen:{tenant_hash}")
        return int(val) if val else 0
        
    gen_initial = get_gen()
    
    # 1. Create
    res = create_prompt(client, token)
    assert res.status_code == 201
    t_id = res.json()["id"]
    gen_after_create = get_gen()
    assert gen_after_create > gen_initial
    
    # 2. Update
    res2 = client.patch(f"/admin/prompts/{t_id}", json={"body": "New Body", "variables": []}, headers={"Authorization": f"Bearer {token}"})
    assert res2.status_code == 200
    gen_after_update = get_gen()
    assert gen_after_update > gen_after_create
    
    # 3. Rollback
    rb_res = client.post(f"/admin/prompts/{t_id}/versions/1/rollback", json={}, headers={"Authorization": f"Bearer {token}"})
    assert rb_res.status_code == 200
    gen_after_rollback = get_gen()
    assert gen_after_rollback > gen_after_update
    
    # 4. Delete version
    del_res = client.delete(f"/admin/prompts/{t_id}/versions/2", headers={"Authorization": f"Bearer {token}"})
    assert del_res.status_code == 200
    gen_after_delete = get_gen()
    assert gen_after_delete > gen_after_rollback

def test_noop_update(client, db):
    token = create_test_token()
    res = create_prompt(client, token)
    t_id = res.json()["id"]
    
    # Exact same payload
    update_payload = {"body": "Body {{ var }}"}
    res2 = client.patch(f"/admin/prompts/{t_id}", json=update_payload, headers={"Authorization": f"Bearer {token}"})
    assert res2.status_code == 200
    
    versions = db.query(TemplateVersion).filter_by(template_id=t_id).all()
    assert len(versions) == 1 # No new version created!



def test_history_pagination(client):
    token = create_test_token()
    res = create_prompt(client, token)
    t_id = res.json()["id"]
    
    for i in range(5):
        client.patch(f"/admin/prompts/{t_id}", json={"body": f"Body {i}", "variables": []}, headers={"Authorization": f"Bearer {token}"})
        
    hist_res = client.get(f"/admin/prompts/{t_id}/versions?limit=2&offset=2", headers={"Authorization": f"Bearer {token}"})
    assert hist_res.status_code == 200
    data = hist_res.json()
    assert len(data["versions"]) == 2
    assert data["versions"][0]["version_number"] == 4
    assert data["versions"][1]["version_number"] == 3
    assert data["current_version"] == 6

def test_structured_field_changes(client):
    token = create_test_token()
    res = create_prompt(client, token)
    t_id = res.json()["id"]
    
    client.patch(f"/admin/prompts/{t_id}", json={"body": "New Body", "name": "New Name", "variables": []}, headers={"Authorization": f"Bearer {token}"})
    
    cmp_res = client.get(f"/admin/prompts/{t_id}/versions/compare?old_version=1&new_version=2", headers={"Authorization": f"Bearer {token}"})
    assert cmp_res.status_code == 200
    changes = cmp_res.json()["changes"]
    assert "body_template" in changes
    assert changes["body_template"]["old"] == "Body {{ var }}"
    assert changes["body_template"]["new"] == "New Body"
    assert "name" in changes
    assert changes["name"]["new"] == "New Name"
    assert "type" not in changes # Unchanged

def test_identical_comparison_returns_empty(client):
    token = create_test_token()
    res = create_prompt(client, token)
    t_id = res.json()["id"]
    
    cmp_res = client.get(f"/admin/prompts/{t_id}/versions/compare?old_version=1&new_version=1", headers={"Authorization": f"Bearer {token}"})
    assert cmp_res.status_code == 200
    assert cmp_res.json()["changes"] == {}

def test_rollback_persistence_and_response(client, db):
    token = create_test_token()
    res = create_prompt(client, token)
    t_id = res.json()["id"]
    
    client.patch(f"/admin/prompts/{t_id}", json={"body": "V2", "variables": []}, headers={"Authorization": f"Bearer {token}"})
    client.patch(f"/admin/prompts/{t_id}", json={"body": "V3", "variables": []}, headers={"Authorization": f"Bearer {token}"})
    
    # Rollback 3 to 1
    rb_res = client.post(f"/admin/prompts/{t_id}/versions/1/rollback", json={}, headers={"Authorization": f"Bearer {token}"})
    assert rb_res.status_code == 200
    rb_data = rb_res.json()
    assert rb_data["previous_version"] == 3
    assert rb_data["restored_version"] == 1
    assert rb_data["new_active_version"] == 4
    
    v4 = db.query(TemplateVersion).filter_by(template_id=t_id, version_number=4).first()
    assert v4.restored_from_version == 1
    assert v4.body_template == "Body {{ var }}"
    
    # Immutable old history - v1 is untouched
    v1 = db.query(TemplateVersion).filter_by(template_id=t_id, version_number=1).first()
    assert v1.is_active is False

def test_cross_tenant_denial(client):
    token1 = create_test_token(tenant_id="tenant-1")
    res = create_prompt(client, token1)
    t_id = res.json()["id"]
    
    token2 = create_test_token(tenant_id="tenant-2")
    # Try to retrieve
    res_get = client.get(f"/admin/prompts/{t_id}/versions", headers={"Authorization": f"Bearer {token2}"})
    assert res_get.status_code == 404
    
    # Try to rollback
    res_rb = client.post(f"/admin/prompts/{t_id}/versions/1/rollback", json={}, headers={"Authorization": f"Bearer {token2}"})
    assert res_rb.status_code == 404

def test_unauthorized_role_denial(client):
    token = create_test_token(roles=["technician"])
    res = client.post("/admin/prompts", json={"name": "x", "body": "x", "channel": "sms", "agent_type": "CommsAgent", "language": "en", "status": "assigned"}, headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 403

def test_redis_failure_fail_open(client, fake_redis, db):
    token = create_test_token()
    res = create_prompt(client, token)
    t_id = res.json()["id"]
    
    fake_redis.fail_mode = True
    
    res2 = client.patch(f"/admin/prompts/{t_id}", json={"body": "New", "variables": []}, headers={"Authorization": f"Bearer {token}"})
    assert res2.status_code == 200
    
    versions = db.query(TemplateVersion).filter_by(template_id=t_id).all()
    assert len(versions) == 2
    
    live = db.query(NotificationTemplate).filter_by(id=t_id).first()
    assert live.body_template == "New"

def test_platform_prompt_super_admin(client, db):
    # Setup a platform prompt manually since API rejects tenant_id in request body
    token = create_test_token(tenant_id="**platform**", roles=["super_admin"])
    payload = {
        "name": "Super Admin Custom Platform Prompt",
        "agent_type": "SentimentAgent",
        "channel": "sms",
        "language": "en",
        "status": "assigned",
        "body": "Body {{ var }}",
        "variables": ["var"],
    }
    res = create_prompt(client, token, payload=payload) # Create as super_admin, tenant=**platform** defaults to **platform**
    t_id = res.json()["id"]
    
    # Attempt to manage as tenant_admin
    tenant_token = create_test_token(tenant_id="tenant-1", roles=["tenant_admin"])
    res_tenant = client.get(f"/admin/prompts/{t_id}/versions", headers={"Authorization": f"Bearer {tenant_token}"})
    assert res_tenant.status_code == 404
    
    res_tenant2 = client.patch(f"/admin/prompts/{t_id}", json={"body": "tenant attempt"}, headers={"Authorization": f"Bearer {tenant_token}"})
    assert res_tenant2.status_code == 404
    
    # Super admin can manage it
    res_super = client.patch(f"/admin/prompts/{t_id}", json={"body": "super success", "variables": []}, headers={"Authorization": f"Bearer {token}"})
    assert res_super.status_code == 200

def test_active_version_deletion_conflict(client):
    token = create_test_token()
    res = create_prompt(client, token)
    t_id = res.json()["id"]
    
    del_res = client.delete(f"/admin/prompts/{t_id}/versions/1", headers={"Authorization": f"Bearer {token}"})
    assert del_res.status_code == 409

def test_deleted_version_inaccessible(client, db):
    token = create_test_token()
    res = create_prompt(client, token)
    t_id = res.json()["id"]
    
    client.patch(f"/admin/prompts/{t_id}", json={"body": "V2", "variables": []}, headers={"Authorization": f"Bearer {token}"})
    
    # Delete V1
    del_res = client.delete(f"/admin/prompts/{t_id}/versions/1", headers={"Authorization": f"Bearer {token}"})
    assert del_res.status_code == 200
    
    # Ensure it's deleted
    v1 = db.query(TemplateVersion).filter_by(template_id=t_id, version_number=1).first()
    assert v1.is_deleted is True
    
    # Cannot retrieve
    get_res = client.get(f"/admin/prompts/{t_id}/versions/1", headers={"Authorization": f"Bearer {token}"})
    assert get_res.status_code == 404
    
    # Cannot compare
    cmp_res = client.get(f"/admin/prompts/{t_id}/versions/compare?old_version=1&new_version=2", headers={"Authorization": f"Bearer {token}"})
    assert cmp_res.status_code == 404
    
    # Cannot rollback
    rb_res = client.post(f"/admin/prompts/{t_id}/versions/1/rollback", json={}, headers={"Authorization": f"Bearer {token}"})
    assert rb_res.status_code == 404

def test_unique_constraint(db):
    from sqlalchemy.exc import IntegrityError
    v1 = TemplateVersion(template_id=1, version_number=1, body_template="1", created_by="1", is_active=False)
    v2 = TemplateVersion(template_id=1, version_number=1, body_template="2", created_by="2", is_active=True)
    db.add(v1)
    db.commit()
    db.add(v2)
    with pytest.raises(IntegrityError):
        db.commit()

def test_partial_index_one_active_version(db):
    from sqlalchemy.exc import IntegrityError
    v1 = TemplateVersion(template_id=2, version_number=1, body_template="1", created_by="1", is_active=True, is_deleted=False)
    v2 = TemplateVersion(template_id=2, version_number=2, body_template="2", created_by="2", is_active=True, is_deleted=False)
    db.add(v1)
    db.commit()
    db.add(v2)
    with pytest.raises(IntegrityError):
        db.commit()

def test_transaction_rollback_on_failure(client, db):
    token = create_test_token()
    res = create_prompt(client, token)
    t_id = res.json()["id"]
    
    from unittest.mock import patch
    with patch('sqlalchemy.orm.Session.flush') as mock_flush:
        from sqlalchemy.exc import IntegrityError
        mock_flush.side_effect = IntegrityError("mock error", params={}, orig=Exception())
        
        # Cause a genuine database integrity failure
        res2 = client.patch(f"/admin/prompts/{t_id}", json={"body": "Fail", "variables": []}, headers={"Authorization": f"Bearer {token}"})
        assert res2.status_code == 409
    
    db.expire_all()
    
    live = db.query(NotificationTemplate).filter_by(id=t_id).first()
    assert live.body_template == "Body {{ var }}"
    assert live.version == 1
    
    v1 = db.query(TemplateVersion).filter_by(template_id=t_id, version_number=1).first()
    assert v1.is_active is True
    
    versions = db.query(TemplateVersion).filter_by(template_id=t_id).all()
    assert len(versions) == 1
    
    get_res = client.get(f"/admin/prompts/{t_id}/versions/1", headers={"Authorization": f"Bearer {token}"})
    assert get_res.status_code == 200