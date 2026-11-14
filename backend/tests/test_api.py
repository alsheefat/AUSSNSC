from datetime import date

API = "/api/v1"


def test_health_and_public_content(client):
    assert client.get("/health").json()["status"] == "ok"
    assert len(client.get(f"{API}/notices").json()) >= 4
    assert len(client.get(f"{API}/classes").json()) == 10


def test_register_creates_public_account_without_academic_access(client):
    r = client.post(f"{API}/auth/register", json={"full_name": "New Person", "phone": "01822222222", "password": "Password123"})
    assert r.status_code == 201 and r.json()["user"]["role"] == "public"
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get(f"{API}/materials", headers=h).status_code == 403
    assert client.get(f"{API}/channels", headers=h).json() == []
    assert client.post(f"{API}/auth/register", json={"full_name": "Dup", "phone": "+8801822222222", "password": "Password123"}).status_code == 409


def test_bad_login(client):
    r = client.post(f"{API}/auth/login", json={"identifier": "01700000001", "password": "wrong-password"})
    assert r.status_code == 401


def test_admin_routes_are_admin_only(client, student, teacher, admin):
    assert client.get(f"{API}/admin/stats").status_code == 401
    assert client.get(f"{API}/admin/stats", headers=student).status_code == 403
    assert client.get(f"{API}/admin/stats", headers=teacher).status_code == 403
    assert client.get(f"{API}/admin/stats", headers=admin).status_code == 200


def test_results_publish_and_search(client, admin, student):
    body = {"exam": "Annual Examination", "exam_year": 2026, "class_name": "10", "section": "A", "roll": 1,
            "student_name": "Demo Student", "gpa": 4.5, "grade": "A", "status": "passed",
            "subjects": [{"subject": "Bangla", "marks": 85}]}
    assert client.post(f"{API}/admin/results", json=body, headers=admin).status_code == 201
    assert client.get(f"{API}/results/search", params={"roll": 1, "class_name": "10"}).json() == []  # unpublished = hidden
    client.post(f"{API}/admin/results/publish", json={"exam": "Annual Examination", "exam_year": 2026, "published": True}, headers=admin)
    hits = client.get(f"{API}/results/search", params={"roll": 1, "class_name": "10"}).json()
    assert hits and hits[0]["gpa"] == 4.5
    assert client.get(f"{API}/results/search", params={"name": "ab"}).status_code == 422   # too short
    assert client.get(f"{API}/me/results", headers=student).json()[0]["student_name"] == "Demo Student"


def test_attendance_flow_and_privacy(client, teacher, student, parent):
    cls = client.get(f"{API}/teacher/classes", headers=teacher).json()[0]["class_id"]
    roster = client.get(f"{API}/classes/{cls}/students", headers=teacher).json()
    payload = {"class_id": cls, "day": date.today().isoformat(),
               "records": [{"student_id": roster[0]["id"], "status": "present"}, {"student_id": roster[1]["id"], "status": "absent"}]}
    assert client.post(f"{API}/attendance", json=payload, headers=teacher).status_code == 200
    mine = client.get(f"{API}/me/attendance", headers=student).json()
    assert mine["present"] == 1 and mine["rate_percent"] == 100.0
    # student must not read a classmate's attendance; parent may read their linked child's
    assert client.get(f"{API}/students/{roster[1]['id']}/attendance", headers=student).status_code == 403
    assert client.get(f"{API}/students/{roster[0]['id']}/attendance", headers=parent).status_code == 200
    assert client.post(f"{API}/attendance", json=payload, headers=student).status_code == 403


def test_assignment_submission_review(client, teacher, student):
    cls = client.get(f"{API}/teacher/classes", headers=teacher).json()[0]["class_id"]
    a = client.post(f"{API}/assignments", json={"class_id": cls, "title": "Chapter 3 exercises"}, headers=teacher)
    assert a.status_code == 201
    aid = a.json()["id"]
    assert any(x["id"] == aid for x in client.get(f"{API}/assignments", headers=student).json())
    s = client.post(f"{API}/assignments/{aid}/submissions", json={"text": "done"}, headers=student)
    assert s.status_code == 200
    r = client.patch(f"{API}/submissions/{s.json()['id']}/review", json={"feedback": "Good", "grade": "A"}, headers=teacher)
    assert r.json()["status"] == "reviewed"
    assert client.post(f"{API}/assignments", json={"class_id": cls, "title": "x"}, headers=student).status_code == 403


def test_parent_link_requires_admin_approval(client, admin):
    r = client.post(f"{API}/auth/register", json={"full_name": "Guardian", "email": "g@example.com", "password": "Password123"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    link = client.post(f"{API}/parent/links", json={"student_name": "Rahim Uddin", "class_name": "10", "roll": 2, "relationship": "Mother"}, headers=h)
    assert link.status_code == 201 and link.json()["status"] == "pending"
    assert client.get(f"{API}/parent/children", headers=h).status_code == 403          # still 'public'
    d = client.post(f"{API}/admin/parent-links/{link.json()['id']}/decision", json={"approve": True}, headers=admin)
    assert d.json()["status"] == "approved"
    h2 = {"Authorization": "Bearer " + client.post(f"{API}/auth/login", json={"identifier": "g@example.com", "password": "Password123"}).json()["access_token"]}
    assert client.get(f"{API}/parent/children", headers=h2).json()[0]["full_name"] == "Rahim Uddin"


def test_community_permissions_and_chat(client, student, teacher, parent):
    chans = client.get(f"{API}/channels", headers=student).json()
    general = next(c for c in chans if c["name"] == "general")
    ann = next(c for c in chans if c["name"] == "announcements")
    assert general["can_post"] and not ann["can_post"]
    m = client.post(f"{API}/channels/{general['id']}/messages", json={"body": "Hello class"}, headers=student)
    assert m.status_code == 201
    assert client.post(f"{API}/channels/{ann['id']}/messages", json={"body": "hi"}, headers=student).status_code == 403
    assert client.post(f"{API}/channels/{general['id']}/messages", json={"body": "hi"}, headers=parent).status_code == 403  # read-only
    assert client.post(f"{API}/messages/{m.json()['id']}/report", json={"reason": "spam"}, headers=teacher).status_code == 201
    assert client.get(f"{API}/moderation/reports", headers=teacher).json()
    assert client.post(f"{API}/messages/{m.json()['id']}/pin", headers=teacher).json()["pinned"] is True
    with client.websocket_connect(f"{API}/ws/channels/{general['id']}?token={student['Authorization'][7:]}") as ws:
        ws.send_json({"body": "live hello"})
        assert ws.receive_json()["message"]["body"] == "live hello"


def test_upload_rules(client, student):
    ok = client.post(f"{API}/uploads", files={"file": ("a.pdf", b"%PDF-1.4 test", "application/pdf")}, headers=student)
    assert ok.status_code == 200 and ok.json()["url"].startswith("/uploads/")
    assert client.get(ok.json()["url"]).status_code == 200
    bad = client.post(f"{API}/uploads", files={"file": ("evil.html", b"<script>", "text/html")}, headers=student)
    assert bad.status_code == 400


def test_google_login_needs_server_config_and_valid_token(client):
    # FIREBASE_PROJECT_ID is not set in the test environment
    r = client.post(f"{API}/auth/google", json={"id_token": "x" * 40})
    assert r.status_code == 503


def test_channel_list_is_role_filtered(client, student, admin):
    s = client.get(f"{API}/channels", headers=student).json()
    a = client.get(f"{API}/channels", headers=admin).json()
    assert 0 < len(s) < len(a)                          # admin sees every class, the student only their own
    assert len({c["class_id"] for c in s} - {None}) == 1  # school-wide channels + exactly one class
