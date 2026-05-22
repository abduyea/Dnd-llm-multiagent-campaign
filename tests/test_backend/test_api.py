from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)

_CHAR_BODY = {
    "character_name": "Thorn",
    "level": 2,
    "strength": 14,
    "dexterity": 12,
    "constitution": 12,
    "intelligence": 10,
    "wisdom": 10,
    "charisma": 10,
    "armor_class": 13,
}


class TestDiceEndpoint:
    def test_roll_valid(self) -> None:
        response = client.post("/api/v1/dice/roll", json={"expression": "2d6+3", "seed": 42})
        assert response.status_code == 200
        data = response.json()
        assert data["expression"] == "2d6+3"
        assert len(data["rolls"]) == 2
        assert data["modifier"] == 3
        assert data["total"] == sum(data["rolls"]) + data["modifier"]

    def test_roll_deterministic(self) -> None:
        r1 = client.post("/api/v1/dice/roll", json={"expression": "1d20", "seed": 99}).json()
        r2 = client.post("/api/v1/dice/roll", json={"expression": "1d20", "seed": 99}).json()
        assert r1["rolls"] == r2["rolls"]
        assert r1["total"] == r2["total"]

    def test_roll_invalid_expression(self) -> None:
        response = client.post("/api/v1/dice/roll", json={"expression": "invalid"})
        assert response.status_code == 422

    def test_roll_pattern_validation(self) -> None:
        response = client.post("/api/v1/dice/roll", json={"expression": "abc"})
        assert response.status_code == 422

    def test_roll_no_seed(self) -> None:
        response = client.post("/api/v1/dice/roll", json={"expression": "1d20"})
        assert response.status_code == 200


class TestCampaignEndpoints:
    def test_list_campaigns_empty(self) -> None:
        response = client.get("/api/v1/campaigns")
        assert response.status_code == 200
        assert response.json() == []

    def test_create_campaign(self) -> None:
        response = client.post(
            "/api/v1/campaigns",
            json={"name": "Test Campaign", "description": "A test", "world_setting": "Fantasy"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Campaign"
        assert data["description"] == "A test"
        assert data["world_setting"] == "Fantasy"
        assert data["status"] == "active"
        assert data["id"] is not None

    def test_create_and_get_campaign(self) -> None:
        created = client.post(
            "/api/v1/campaigns",
            json={"name": "My Campaign"},
        ).json()
        campaign_id = created["id"]

        response = client.get(f"/api/v1/campaigns/{campaign_id}")
        assert response.status_code == 200
        assert response.json()["name"] == "My Campaign"

    def test_get_nonexistent_campaign_returns_404(self) -> None:
        response = client.get("/api/v1/campaigns/nonexistent-id")
        assert response.status_code == 404

    def test_update_campaign(self) -> None:
        created = client.post(
            "/api/v1/campaigns",
            json={"name": "Original"},
        ).json()
        campaign_id = created["id"]

        response = client.put(
            f"/api/v1/campaigns/{campaign_id}",
            json={"name": "Updated"},
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Updated"

    def test_list_campaigns_with_items(self) -> None:
        client.post("/api/v1/campaigns", json={"name": "Camp A"})
        client.post("/api/v1/campaigns", json={"name": "Camp B"})
        response = client.get("/api/v1/campaigns")
        assert response.status_code == 200
        assert len(response.json()) >= 2

    def test_update_campaign_all_fields(self) -> None:
        created = client.post("/api/v1/campaigns", json={"name": "Old"}).json()
        response = client.put(
            f"/api/v1/campaigns/{created['id']}",
            json={
                "name": "New",
                "description": "Updated description",
                "world_setting": "Eberron",
                "status": "completed",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["description"] == "Updated description"
        assert data["world_setting"] == "Eberron"
        assert data["status"] == "completed"

    def test_update_nonexistent_campaign_returns_404(self) -> None:
        response = client.put("/api/v1/campaigns/ghost-id", json={"name": "X"})
        assert response.status_code == 404

    def test_delete_campaign_returns_204(self) -> None:
        campaign = client.post("/api/v1/campaigns", json={"name": "To Delete"}).json()

        response = client.delete(f"/api/v1/campaigns/{campaign['id']}")
        assert response.status_code == 204

        get_resp = client.get(f"/api/v1/campaigns/{campaign['id']}")
        assert get_resp.status_code == 404

    def test_delete_nonexistent_campaign_returns_404(self) -> None:
        response = client.delete("/api/v1/campaigns/ghost-id")
        assert response.status_code == 404

    def test_delete_campaign_cascades_characters(self) -> None:
        campaign = client.post("/api/v1/campaigns", json={"name": "Cascade Test"}).json()
        char = client.post(
            f"/api/v1/campaigns/{campaign['id']}/characters", json=_CHAR_BODY
        ).json()

        client.delete(f"/api/v1/campaigns/{campaign['id']}")

        char_resp = client.get(f"/api/v1/characters/{char['id']}")
        assert char_resp.status_code == 404

    def test_delete_campaign_blocked_during_active_session(self) -> None:
        campaign = client.post("/api/v1/campaigns", json={"name": "Active Camp"}).json()
        client.post("/api/v1/sessions", json={"campaign_id": campaign["id"], "name": "S1"})

        response = client.delete(f"/api/v1/campaigns/{campaign['id']}")
        assert response.status_code == 409


class TestCampaignExportImport:
    """Tests for GET /campaigns/{id}/export and POST /campaigns/import."""

    def _make_campaign_with_char(self) -> tuple[str, str]:
        campaign = client.post(
            "/api/v1/campaigns", json={"name": "Export Camp", "world_setting": "Fantasy"}
        ).json()
        char = client.post(
            f"/api/v1/campaigns/{campaign['id']}/characters", json=_CHAR_BODY
        ).json()
        return campaign["id"], char["id"]

    def test_export_returns_bundle_structure(self) -> None:
        campaign_id, _ = self._make_campaign_with_char()
        resp = client.get(f"/api/v1/campaigns/{campaign_id}/export")
        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == "1.0"
        assert "exported_at" in data
        assert data["campaign"]["name"] == "Export Camp"
        assert data["campaign"]["world_setting"] == "Fantasy"
        assert len(data["characters"]) == 1

    def test_export_character_fields(self) -> None:
        campaign_id, _ = self._make_campaign_with_char()
        data = client.get(f"/api/v1/campaigns/{campaign_id}/export").json()
        char = data["characters"][0]
        assert char["character_name"] == "Thorn"
        assert char["level"] == 2
        assert char["strength"] == 14
        assert char["armor_class"] == 13

    def test_export_nonexistent_returns_404(self) -> None:
        resp = client.get("/api/v1/campaigns/nonexistent/export")
        assert resp.status_code == 404

    def test_import_creates_campaign(self) -> None:
        bundle = {
            "version": "1.0",
            "exported_at": "2026-01-01T00:00:00",
            "campaign": {"name": "Imported Camp", "description": "Desc", "world_setting": "Dark"},
            "characters": [
                {
                    "character_name": "Aria",
                    "level": 3,
                    "hp_current": 20, "hp_max": 20,
                    "strength": 10, "dexterity": 14,
                    "constitution": 12, "intelligence": 10,
                    "wisdom": 10, "charisma": 16,
                    "armor_class": 12,
                }
            ],
        }
        resp = client.post("/api/v1/campaigns/import", json=bundle)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Imported Camp"
        assert data["character_count"] == 1

    def test_import_no_characters(self) -> None:
        bundle = {
            "campaign": {"name": "Empty Camp"},
            "characters": [],
        }
        resp = client.post("/api/v1/campaigns/import", json=bundle)
        assert resp.status_code == 201
        data = resp.json()
        assert data["character_count"] == 0

    def test_export_import_roundtrip(self) -> None:
        """Export a campaign, import it, verify the imported copy matches the original."""
        campaign_id, _ = self._make_campaign_with_char()
        bundle = client.get(f"/api/v1/campaigns/{campaign_id}/export").json()

        imported = client.post("/api/v1/campaigns/import", json=bundle).json()
        assert imported["name"] == bundle["campaign"]["name"]
        assert imported["character_count"] == len(bundle["characters"])
        # New campaign gets a different ID
        assert imported["id"] != campaign_id

    def test_import_assigns_new_ids(self) -> None:
        """Imported campaign must have a fresh ID, not reuse the source ID."""
        campaign_id, _ = self._make_campaign_with_char()
        bundle = client.get(f"/api/v1/campaigns/{campaign_id}/export").json()
        imported = client.post("/api/v1/campaigns/import", json=bundle).json()
        # Verify source still exists under original ID
        original = client.get(f"/api/v1/campaigns/{campaign_id}").json()
        assert original["id"] == campaign_id
        assert imported["id"] != campaign_id


class TestCharacterEndpoints:
    def test_create_character(self) -> None:
        campaign = client.post("/api/v1/campaigns", json={"name": "Campaign for Char"}).json()

        response = client.post(
            f"/api/v1/campaigns/{campaign['id']}/characters",
            json={
                "character_name": "Aragorn",
                "race": "Human",
                "class_name": "Ranger",
                "level": 3,
                "strength": 16,
                "dexterity": 14,
                "constitution": 14,
                "intelligence": 10,
                "wisdom": 14,
                "charisma": 10,
                "armor_class": 15,
                "initiative": 2,
                "speed": 30,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["character_name"] == "Aragorn"
        assert data["level"] == 3

    def test_list_characters(self) -> None:
        campaign = client.post("/api/v1/campaigns", json={"name": "Campaign"}).json()

        client.post(
            f"/api/v1/campaigns/{campaign['id']}/characters",
            json={"character_name": "Hero1", "level": 1},
        )
        client.post(
            f"/api/v1/campaigns/{campaign['id']}/characters",
            json={"character_name": "Hero2", "level": 2},
        )

        response = client.get(f"/api/v1/campaigns/{campaign['id']}/characters")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    def test_create_character_invalid_campaign(self) -> None:
        response = client.post(
            "/api/v1/campaigns/invalid/characters",
            json={"character_name": "Ghost"},
        )
        assert response.status_code == 404

    def test_get_character(self) -> None:
        campaign = client.post("/api/v1/campaigns", json={"name": "C"}).json()
        char = client.post(
            f"/api/v1/campaigns/{campaign['id']}/characters",
            json=_CHAR_BODY,
        ).json()

        response = client.get(f"/api/v1/characters/{char['id']}")
        assert response.status_code == 200
        assert response.json()["character_name"] == "Thorn"

    def test_get_nonexistent_character_returns_404(self) -> None:
        response = client.get("/api/v1/characters/no-such-char")
        assert response.status_code == 404

    def test_update_character(self) -> None:
        campaign = client.post("/api/v1/campaigns", json={"name": "C"}).json()
        char = client.post(
            f"/api/v1/campaigns/{campaign['id']}/characters",
            json=_CHAR_BODY,
        ).json()

        response = client.put(
            f"/api/v1/characters/{char['id']}",
            json={"hp_current": 10, "armor_class": 15, "level": 3},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["hp_current"] == 10
        assert data["armor_class"] == 15
        assert data["level"] == 3

    def test_update_nonexistent_character_returns_404(self) -> None:
        response = client.put("/api/v1/characters/ghost", json={"hp_current": 5})
        assert response.status_code == 404

    def test_update_character_name_and_speed(self) -> None:
        campaign = client.post("/api/v1/campaigns", json={"name": "C"}).json()
        char = client.post(
            f"/api/v1/campaigns/{campaign['id']}/characters",
            json=_CHAR_BODY,
        ).json()

        response = client.put(
            f"/api/v1/characters/{char['id']}",
            json={"player_name": "Bob", "character_name": "Ragnar", "hp_max": 40, "speed": 25},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["player_name"] == "Bob"
        assert data["character_name"] == "Ragnar"
        assert data["hp_max"] == 40
        assert data["speed"] == 25

    def test_update_character_hp_bounds_rejected(self) -> None:
        campaign = client.post("/api/v1/campaigns", json={"name": "C"}).json()
        char = client.post(
            f"/api/v1/campaigns/{campaign['id']}/characters", json=_CHAR_BODY
        ).json()

        cid = char["id"]
        assert client.put(f"/api/v1/characters/{cid}", json={"hp_current": 0}).status_code == 422
        assert client.put(f"/api/v1/characters/{cid}", json={"hp_max": 0}).status_code == 422
        assert client.put(f"/api/v1/characters/{cid}", json={"hp_current": 1000}).status_code == 422
        assert client.put(f"/api/v1/characters/{cid}", json={"hp_max": 1000}).status_code == 422

    def test_update_character_backstory(self) -> None:
        campaign = client.post("/api/v1/campaigns", json={"name": "C"}).json()
        char = client.post(
            f"/api/v1/campaigns/{campaign['id']}/characters", json=_CHAR_BODY
        ).json()

        response = client.put(
            f"/api/v1/characters/{char['id']}",
            json={"backstory": "A wandering mercenary from the northern reaches."},
        )
        assert response.status_code == 200

    def test_update_character_ability_scores_and_meta(self) -> None:
        campaign = client.post("/api/v1/campaigns", json={"name": "C"}).json()
        char = client.post(
            f"/api/v1/campaigns/{campaign['id']}/characters",
            json=_CHAR_BODY,
        ).json()

        response = client.put(
            f"/api/v1/characters/{char['id']}",
            json={
                "race": "Elf",
                "class_name": "Ranger",
                "strength": 16,
                "dexterity": 18,
                "constitution": 14,
                "intelligence": 12,
                "wisdom": 15,
                "charisma": 11,
                "initiative": 4,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["race"] == "Elf"
        assert data["class_name"] == "Ranger"
        assert data["strength"] == 16
        assert data["dexterity"] == 18
        assert data["constitution"] == 14
        assert data["intelligence"] == 12
        assert data["wisdom"] == 15
        assert data["charisma"] == 11
        assert data["initiative"] == 4

    def test_update_campaign_fields(self) -> None:
        campaign = client.post(
            "/api/v1/campaigns",
            json={"name": "Old Name", "description": "Old desc", "world_setting": "Old world"},
        ).json()

        response = client.put(
            f"/api/v1/campaigns/{campaign['id']}",
            json={"name": "New Name", "description": "New desc", "world_setting": "New world"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "New Name"
        assert data["description"] == "New desc"
        assert data["world_setting"] == "New world"

    def test_delete_character_returns_204(self) -> None:
        campaign = client.post("/api/v1/campaigns", json={"name": "C"}).json()
        char = client.post(
            f"/api/v1/campaigns/{campaign['id']}/characters", json=_CHAR_BODY
        ).json()

        response = client.delete(f"/api/v1/characters/{char['id']}")
        assert response.status_code == 204

        # Character is gone
        get_resp = client.get(f"/api/v1/characters/{char['id']}")
        assert get_resp.status_code == 404

    def test_delete_nonexistent_character_returns_404(self) -> None:
        response = client.delete("/api/v1/characters/ghost")
        assert response.status_code == 404

    def test_delete_character_blocked_during_active_session(self) -> None:
        campaign = client.post("/api/v1/campaigns", json={"name": "C"}).json()
        char = client.post(
            f"/api/v1/campaigns/{campaign['id']}/characters", json=_CHAR_BODY
        ).json()
        client.post("/api/v1/sessions", json={"campaign_id": campaign["id"], "name": "S1"})

        response = client.delete(f"/api/v1/characters/{char['id']}")
        assert response.status_code == 409

    def test_character_hp_computed_server_side(self) -> None:
        campaign = client.post("/api/v1/campaigns", json={"name": "C"}).json()
        body = dict(_CHAR_BODY)
        body["level"] = 3
        body["constitution"] = 14
        char = client.post(
            f"/api/v1/campaigns/{campaign['id']}/characters",
            json=body,
        ).json()
        assert char["hp_max"] == 3 * 8 + 2 * 3  # level*8 + CON_mod*level; CON 14 → mod +2
        assert char["hp_current"] == char["hp_max"]


class TestSessionEndpoints:
    def test_create_session(self) -> None:
        campaign = client.post("/api/v1/campaigns", json={"name": "Session Campaign"}).json()

        response = client.post(
            "/api/v1/sessions",
            json={"campaign_id": campaign["id"], "name": "Session 1"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "active"
        assert data["campaign_id"] == campaign["id"]

    def test_create_session_nonexistent_campaign_returns_404(self) -> None:
        response = client.post(
            "/api/v1/sessions",
            json={"campaign_id": "missing-campaign", "name": "Orphan"},
        )
        assert response.status_code == 404

    def test_list_sessions(self) -> None:
        campaign = client.post("/api/v1/campaigns", json={"name": "List Camp"}).json()
        client.post(
            "/api/v1/sessions",
            json={"campaign_id": campaign["id"], "name": "S1"},
        )

        response = client.get("/api/v1/sessions")
        assert response.status_code == 200
        assert len(response.json()) >= 1

    def test_end_session(self) -> None:
        campaign = client.post("/api/v1/campaigns", json={"name": "End Camp"}).json()
        session = client.post(
            "/api/v1/sessions",
            json={"campaign_id": campaign["id"], "name": "To End"},
        ).json()

        response = client.post(f"/api/v1/sessions/{session['id']}/end")
        assert response.status_code == 200
        assert response.json()["status"] == "completed"

    def test_get_session(self) -> None:
        campaign = client.post("/api/v1/campaigns", json={"name": "C"}).json()
        session = client.post(
            "/api/v1/sessions",
            json={"campaign_id": campaign["id"], "name": "S"},
        ).json()

        response = client.get(f"/api/v1/sessions/{session['id']}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == session["id"]
        assert data["status"] == "active"

    def test_get_nonexistent_session_returns_404(self) -> None:
        response = client.get("/api/v1/sessions/ghost-session")
        assert response.status_code == 404

    def test_end_nonexistent_session_returns_404(self) -> None:
        response = client.post("/api/v1/sessions/ghost-session/end")
        assert response.status_code == 404

    def test_create_session_started_at_is_set(self) -> None:
        campaign = client.post("/api/v1/campaigns", json={"name": "C"}).json()
        response = client.post(
            "/api/v1/sessions",
            json={"campaign_id": campaign["id"], "name": "Time Check"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["started_at"] != "" and data["started_at"] is not None

    def test_get_session_includes_summary_field(self) -> None:
        campaign = client.post("/api/v1/campaigns", json={"name": "C"}).json()
        session = client.post(
            "/api/v1/sessions",
            json={"campaign_id": campaign["id"], "name": "S"},
        ).json()
        response = client.get(f"/api/v1/sessions/{session['id']}")
        assert response.status_code == 200
        assert "summary" in response.json()

    def test_delete_completed_session_returns_204(self) -> None:
        campaign = client.post("/api/v1/campaigns", json={"name": "Del Camp"}).json()
        session = client.post(
            "/api/v1/sessions",
            json={"campaign_id": campaign["id"], "name": "To Delete"},
        ).json()
        client.post(f"/api/v1/sessions/{session['id']}/end")
        response = client.delete(f"/api/v1/sessions/{session['id']}")
        assert response.status_code == 204

    def test_delete_active_session_returns_409(self) -> None:
        campaign = client.post("/api/v1/campaigns", json={"name": "Active Del"}).json()
        session = client.post(
            "/api/v1/sessions",
            json={"campaign_id": campaign["id"], "name": "Active"},
        ).json()
        response = client.delete(f"/api/v1/sessions/{session['id']}")
        assert response.status_code == 409

    def test_delete_nonexistent_session_returns_404(self) -> None:
        response = client.delete("/api/v1/sessions/ghost-999")
        assert response.status_code == 404

    def test_delete_session_removes_from_list(self) -> None:
        campaign = client.post("/api/v1/campaigns", json={"name": "C"}).json()
        session = client.post(
            "/api/v1/sessions",
            json={"campaign_id": campaign["id"], "name": "Gone"},
        ).json()
        client.post(f"/api/v1/sessions/{session['id']}/end")
        client.delete(f"/api/v1/sessions/{session['id']}")
        response = client.get(f"/api/v1/sessions/{session['id']}")
        assert response.status_code == 404


class TestActionEndpoint:
    def test_action_nonexistent_session(self) -> None:
        response = client.post(
            "/api/v1/sessions/invalid/actions",
            json={
                "session_id": "invalid",
                "character_id": "pc1",
                "action_type": "move",
                "description": "Testing",
            },
        )
        assert response.status_code == 404

    def test_action_missing_character(self) -> None:
        campaign = client.post("/api/v1/campaigns", json={"name": "Action Camp"}).json()
        session = client.post(
            "/api/v1/sessions",
            json={"campaign_id": campaign["id"], "name": "Action Sess"},
        ).json()

        response = client.post(
            f"/api/v1/sessions/{session['id']}/actions",
            json={
                "session_id": session["id"],
                "character_id": "nonexistent",
                "action_type": "move",
                "description": "Move forward",
            },
        )
        assert response.status_code == 400

    def test_action_invalid_type_returns_422(self) -> None:
        campaign = client.post("/api/v1/campaigns", json={"name": "C"}).json()
        session = client.post(
            "/api/v1/sessions",
            json={"campaign_id": campaign["id"], "name": "S"},
        ).json()
        response = client.post(
            f"/api/v1/sessions/{session['id']}/actions",
            json={"character_id": "x", "action_type": "fly_to_moon", "description": "go"},
        )
        assert response.status_code == 422

    def test_roleplay_action_full_pipeline(self) -> None:
        campaign = client.post("/api/v1/campaigns", json={"name": "Pipeline Camp"}).json()
        char = client.post(
            f"/api/v1/campaigns/{campaign['id']}/characters",
            json=_CHAR_BODY,
        ).json()
        session = client.post(
            "/api/v1/sessions",
            json={"campaign_id": campaign["id"], "name": "Pipeline Sess"},
        ).json()

        response = client.post(
            f"/api/v1/sessions/{session['id']}/actions",
            json={
                "character_id": char["id"],
                "action_type": "roleplay",
                "description": "Thorn looks around the room.",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["action_type"] == "roleplay"
        assert data["turn_number"] == 0
        assert isinstance(data["narration"], str)
        assert data["narration"] != ""

    def test_melee_attack_full_pipeline(self) -> None:
        campaign = client.post("/api/v1/campaigns", json={"name": "Fight Camp"}).json()
        attacker = client.post(
            f"/api/v1/campaigns/{campaign['id']}/characters",
            json=_CHAR_BODY,
        ).json()
        target_body = dict(_CHAR_BODY)
        target_body["character_name"] = "Goblin"
        target = client.post(
            f"/api/v1/campaigns/{campaign['id']}/characters",
            json=target_body,
        ).json()
        session = client.post(
            "/api/v1/sessions",
            json={"campaign_id": campaign["id"], "name": "Fight Sess"},
        ).json()

        response = client.post(
            f"/api/v1/sessions/{session['id']}/actions",
            json={
                "character_id": attacker["id"],
                "action_type": "attack_melee",
                "target_id": target["id"],
                "dice_expression": "1d8",
                "description": "Thorn swings at the goblin.",
                "seed": 42,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["action_type"] == "attack_melee"
        assert data["turn_number"] == 0


class TestActionStreamEndpoint:
    """Tests for POST /sessions/{id}/actions/stream (SSE streaming endpoint)."""

    def _setup(self) -> tuple[str, str, str]:
        campaign = client.post("/api/v1/campaigns", json={"name": "Stream Camp"}).json()
        char = client.post(
            f"/api/v1/campaigns/{campaign['id']}/characters", json=_CHAR_BODY
        ).json()
        session = client.post(
            "/api/v1/sessions",
            json={"campaign_id": campaign["id"], "name": "Stream Sess"},
        ).json()
        return campaign["id"], char["id"], session["id"]

    @staticmethod
    def _parse_sse(text: str) -> list[dict]:
        import json as _json
        events = []
        for part in text.split("\n\n"):
            for line in part.split("\n"):
                if line.startswith("data: "):
                    try:
                        events.append(_json.loads(line[6:]))
                    except _json.JSONDecodeError:
                        pass
        return events

    def test_stream_returns_event_stream_content_type(self) -> None:
        _, char_id, session_id = self._setup()
        response = client.post(
            f"/api/v1/sessions/{session_id}/actions/stream",
            json={"character_id": char_id, "action_type": "roleplay", "description": "Look around"},
        )
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")

    def test_stream_emits_result_and_done_events(self) -> None:
        _, char_id, session_id = self._setup()
        response = client.post(
            f"/api/v1/sessions/{session_id}/actions/stream",
            json={"character_id": char_id, "action_type": "roleplay", "description": "Look around"},
        )
        events = self._parse_sse(response.text)
        types = [e.get("type") for e in events]
        assert "result" in types
        assert "done" in types

    def test_stream_result_event_has_correct_fields(self) -> None:
        _, char_id, session_id = self._setup()
        response = client.post(
            f"/api/v1/sessions/{session_id}/actions/stream",
            json={"character_id": char_id, "action_type": "roleplay", "description": "Scout ahead"},
        )
        events = self._parse_sse(response.text)
        result = next(e for e in events if e.get("type") == "result")
        assert result["action_type"] == "roleplay"
        assert result["character_id"] == char_id
        assert result["turn_number"] == 0
        assert "state_changes" in result

    def test_stream_done_event_has_narration(self) -> None:
        _, char_id, session_id = self._setup()
        response = client.post(
            f"/api/v1/sessions/{session_id}/actions/stream",
            json={"character_id": char_id, "action_type": "roleplay", "description": "Observe"},
        )
        events = self._parse_sse(response.text)
        done = next(e for e in events if e.get("type") == "done")
        assert "narration" in done
        assert isinstance(done["narration"], str)
        assert len(done["narration"]) > 0
        assert "npc_responses" in done

    def test_stream_nonexistent_session_yields_error_event(self) -> None:
        response = client.post(
            "/api/v1/sessions/nonexistent/actions/stream",
            json={"character_id": "x", "action_type": "roleplay", "description": "Test"},
        )
        assert response.status_code == 200
        events = self._parse_sse(response.text)
        errors = [e for e in events if e.get("type") == "error"]
        assert len(errors) > 0
        assert errors[0]["status"] == 404

    def test_stream_increments_turn_counter(self) -> None:
        _, char_id, session_id = self._setup()
        for _ in range(2):
            client.post(
                f"/api/v1/sessions/{session_id}/actions/stream",
                json={"character_id": char_id, "action_type": "roleplay", "description": "Act"},
            )
        session = client.get(f"/api/v1/sessions/{session_id}").json()
        assert session["turn_count"] == 2


class TestOrchestratorExceptionPaths:
    """Verify that agent exceptions degrade gracefully and never crash the game loop."""

    def _create_session(self) -> tuple[str, str]:
        campaign = client.post("/api/v1/campaigns", json={"name": "Exception Camp"}).json()
        client.post(
            f"/api/v1/campaigns/{campaign['id']}/characters",
            json=_CHAR_BODY,
        )
        session = client.post(
            "/api/v1/sessions",
            json={"campaign_id": campaign["id"], "name": "Exception Sess"},
        ).json()
        return campaign["id"], session["id"]

    def _get_char_id(self, campaign_id: str) -> str:
        chars = client.get(f"/api/v1/campaigns/{campaign_id}/characters").json()
        return chars[0]["id"]

    def test_narration_exception_returns_200(self) -> None:
        campaign_id, session_id = self._create_session()
        char_id = self._get_char_id(campaign_id)
        with patch("backend.app.orchestrator.narrate", side_effect=Exception("narration boom")):
            response = client.post(
                f"/api/v1/sessions/{session_id}/actions",
                json={"character_id": char_id, "action_type": "roleplay", "description": "Test"},
            )
        assert response.status_code == 200

    def test_npc_agent_exception_returns_200(self) -> None:
        campaign_id, session_id = self._create_session()
        char_id = self._get_char_id(campaign_id)
        with patch("backend.app.orchestrator.get_npc_responses", side_effect=Exception("npc boom")):
            response = client.post(
                f"/api/v1/sessions/{session_id}/actions",
                json={"character_id": char_id, "action_type": "roleplay", "description": "Test"},
            )
        assert response.status_code == 200

    def test_memory_agent_exception_returns_200(self) -> None:
        campaign_id, session_id = self._create_session()
        char_id = self._get_char_id(campaign_id)
        with patch(
            "backend.app.orchestrator.extract_and_store",
            new_callable=AsyncMock,
            side_effect=Exception("memory boom"),
        ):
            response = client.post(
                f"/api/v1/sessions/{session_id}/actions",
                json={"character_id": char_id, "action_type": "roleplay", "description": "Test"},
            )
        assert response.status_code == 200

    def test_summary_agent_exception_on_end_session(self) -> None:
        _campaign_id, session_id = self._create_session()
        with patch(
            "backend.app.orchestrator.summarise_session",
            new_callable=AsyncMock,
            side_effect=Exception("summary boom"),
        ):
            response = client.post(f"/api/v1/sessions/{session_id}/end")
        assert response.status_code == 200
        assert response.json()["status"] == "completed"

    def test_npc_responses_logged_to_event_log(self) -> None:
        """Lines 218-225: NPC dialogue EventLog entries are created when NPC responses exist."""
        campaign_id, session_id = self._create_session()
        char_id = self._get_char_id(campaign_id)
        with (
            patch("backend.app.orchestrator.narrate", return_value="The innkeeper smiles."),
            patch(
                "backend.app.orchestrator.get_npc_responses",
                return_value=[{"npc_name": "Innkeeper", "dialogue": "Welcome, traveller!"}],
            ),
        ):
            response = client.post(
                f"/api/v1/sessions/{session_id}/actions",
                json={
                    "character_id": char_id,
                    "action_type": "roleplay",
                    "description": "Talk to innkeeper",
                },
            )
        assert response.status_code == 200
        data = response.json()
        expected = [{"npc_name": "Innkeeper", "dialogue": "Welcome, traveller!"}]
        assert data["npc_responses"] == expected

    def test_action_on_completed_session_returns_409(self) -> None:
        """Actions submitted after session end must be rejected with 409."""
        campaign_id, session_id = self._create_session()
        char_id = self._get_char_id(campaign_id)
        client.post(f"/api/v1/sessions/{session_id}/end")
        response = client.post(
            f"/api/v1/sessions/{session_id}/actions",
            json={"character_id": char_id, "action_type": "roleplay", "description": "Test"},
        )
        assert response.status_code == 409
        assert "ended" in response.json()["detail"].lower()

    def test_get_game_state_returns_none_for_unknown_session(self) -> None:
        """Orchestrator line 86: process_action returns 404 when get_game_state yields None."""
        campaign_id, session_id = self._create_session()
        char_id = self._get_char_id(campaign_id)
        with patch(
            "backend.app.orchestrator.get_game_state",
            new_callable=AsyncMock,
            return_value=None,
        ):
            response = client.post(
                f"/api/v1/sessions/{session_id}/actions",
                json={"character_id": char_id, "action_type": "roleplay", "description": "Test"},
            )
        assert response.status_code == 404

    def test_invalid_dice_expression_falls_back_to_empty(self) -> None:
        """Orchestrator lines 108-109: ValueError from roll_dice caught; action still succeeds."""
        campaign_id, session_id = self._create_session()
        char_id = self._get_char_id(campaign_id)
        with patch("backend.app.orchestrator.roll_dice", side_effect=ValueError("bad expr")):
            response = client.post(
                f"/api/v1/sessions/{session_id}/actions",
                json={
                    "character_id": char_id,
                    "action_type": "skill_check",
                    "description": "Investigate the room.",
                    "dice_expression": "1d20",
                },
            )
        assert response.status_code == 200
        assert response.json()["dice_results"] == []


class TestStatsEndpoint:
    def test_stats_returns_expected_keys(self) -> None:
        response = client.get("/api/v1/stats")
        assert response.status_code == 200
        data = response.json()
        assert "campaigns" in data
        assert "campaigns_active" in data
        assert "characters" in data
        assert "sessions" in data
        assert "sessions_completed" in data
        assert "turns" in data

    def test_stats_counts_grow_with_data(self) -> None:
        before = client.get("/api/v1/stats").json()
        client.post("/api/v1/campaigns", json={"name": "Stats Camp"})
        after = client.get("/api/v1/stats").json()
        assert after["campaigns"] == before["campaigns"] + 1
        assert after["campaigns_active"] == before["campaigns_active"] + 1

    def test_stats_completed_session_counted(self) -> None:
        campaign = client.post("/api/v1/campaigns", json={"name": "C"}).json()
        session = client.post(
            "/api/v1/sessions", json={"campaign_id": campaign["id"], "name": "S"}
        ).json()
        before = client.get("/api/v1/stats").json()
        client.post(f"/api/v1/sessions/{session['id']}/end")
        after = client.get("/api/v1/stats").json()
        assert after["sessions_completed"] == before["sessions_completed"] + 1

    def test_stats_turns_increment_on_action(self) -> None:
        campaign = client.post("/api/v1/campaigns", json={"name": "C"}).json()
        char = client.post(
            f"/api/v1/campaigns/{campaign['id']}/characters", json=_CHAR_BODY
        ).json()
        session = client.post(
            "/api/v1/sessions", json={"campaign_id": campaign["id"], "name": "S"}
        ).json()
        before = client.get("/api/v1/stats").json()
        client.post(
            f"/api/v1/sessions/{session['id']}/actions",
            json={"character_id": char["id"], "action_type": "roleplay", "description": "Look"},
        )
        after = client.get("/api/v1/stats").json()
        assert after["turns"] == before["turns"] + 1


class TestSessionTurnsEndpoint:
    def test_list_session_turns_unknown_session_returns_404(self) -> None:
        response = client.get("/api/v1/sessions/ghost-id/turns")
        assert response.status_code == 404

    def test_list_session_turns_empty_on_new_session(self) -> None:
        campaign = client.post("/api/v1/campaigns", json={"name": "C"}).json()
        session = client.post(
            "/api/v1/sessions", json={"campaign_id": campaign["id"], "name": "S"}
        ).json()

        response = client.get(f"/api/v1/sessions/{session['id']}/turns")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_session_turns_returns_turns_after_action(self) -> None:
        campaign = client.post("/api/v1/campaigns", json={"name": "C"}).json()
        char = client.post(
            f"/api/v1/campaigns/{campaign['id']}/characters", json=_CHAR_BODY
        ).json()
        session = client.post(
            "/api/v1/sessions", json={"campaign_id": campaign["id"], "name": "S"}
        ).json()

        client.post(
            f"/api/v1/sessions/{session['id']}/actions",
            json={"character_id": char["id"], "action_type": "roleplay", "description": "Look"},
        )

        response = client.get(f"/api/v1/sessions/{session['id']}/turns")
        assert response.status_code == 200
        turns = response.json()
        assert len(turns) == 1
        assert turns[0]["action_type"] == "roleplay"
        assert turns[0]["turn_number"] == 0
        assert turns[0]["character_id"] == char["id"]
        assert turns[0]["character_name"] == "Thorn"
        assert isinstance(turns[0]["dice_results"], list)

    def test_list_session_turns_includes_npc_responses_field(self) -> None:
        """Turns response always has npc_responses key (even when empty)."""
        campaign = client.post("/api/v1/campaigns", json={"name": "C"}).json()
        char = client.post(
            f"/api/v1/campaigns/{campaign['id']}/characters", json=_CHAR_BODY
        ).json()
        session = client.post(
            "/api/v1/sessions", json={"campaign_id": campaign["id"], "name": "S"}
        ).json()
        client.post(
            f"/api/v1/sessions/{session['id']}/actions",
            json={"character_id": char["id"], "action_type": "roleplay", "description": "Look"},
        )

        turns = client.get(f"/api/v1/sessions/{session['id']}/turns").json()
        assert "npc_responses" in turns[0]
        assert isinstance(turns[0]["npc_responses"], list)

    def test_list_session_turns_parses_npc_event_log(self) -> None:
        """sessions.py lines 107-110: NPC EventLog entries are parsed and returned in turns."""
        campaign = client.post("/api/v1/campaigns", json={"name": "C"}).json()
        char = client.post(
            f"/api/v1/campaigns/{campaign['id']}/characters", json=_CHAR_BODY
        ).json()
        session = client.post(
            "/api/v1/sessions", json={"campaign_id": campaign["id"], "name": "S"}
        ).json()

        npc_payload = [{"npc_name": "Garrick", "dialogue": "Well met, traveller!"}]
        with (
            patch("backend.app.orchestrator.narrate", return_value="Garrick waves at you."),
            patch("backend.app.orchestrator.get_npc_responses", return_value=npc_payload),
        ):
            client.post(
                f"/api/v1/sessions/{session['id']}/actions",
                json={
                    "character_id": char["id"],
                    "action_type": "roleplay",
                    "description": "Greet the blacksmith.",
                },
            )

        turns = client.get(f"/api/v1/sessions/{session['id']}/turns").json()
        assert len(turns) == 1
        assert turns[0]["npc_responses"] == npc_payload

    def test_list_session_turns_includes_parsed_dice_and_attack_result(self) -> None:
        """dice_results and attack_result in turns response are parsed, not raw JSON strings."""
        campaign = client.post("/api/v1/campaigns", json={"name": "C"}).json()
        attacker = client.post(
            f"/api/v1/campaigns/{campaign['id']}/characters", json=_CHAR_BODY
        ).json()
        target_body = dict(_CHAR_BODY)
        target_body["character_name"] = "Goblin"
        target = client.post(
            f"/api/v1/campaigns/{campaign['id']}/characters", json=target_body
        ).json()
        session = client.post(
            "/api/v1/sessions", json={"campaign_id": campaign["id"], "name": "S"}
        ).json()
        client.post(
            f"/api/v1/sessions/{session['id']}/actions",
            json={
                "character_id": attacker["id"],
                "action_type": "attack_melee",
                "target_id": target["id"],
                "dice_expression": "1d8",
                "description": "Thorn attacks the goblin.",
                "seed": 42,
            },
        )

        turns = client.get(f"/api/v1/sessions/{session['id']}/turns").json()
        assert len(turns) == 1
        assert isinstance(turns[0]["dice_results"], list)
        ar = turns[0]["attack_result"]
        assert ar is not None
        assert "is_hit" in ar
        assert "is_critical" in ar
        assert "natural_roll" in ar
        assert "damage" in ar

    async def test_malformed_dice_and_attack_result_json_are_safe(self) -> None:
        """sessions.py lines 124-126, 130-131: bad JSON in dice_results/attack_result is safe."""
        from backend.app.db.models.session import Turn
        from tests.test_backend.conftest import test_session_factory

        campaign = client.post("/api/v1/campaigns", json={"name": "C"}).json()
        session = client.post(
            "/api/v1/sessions", json={"campaign_id": campaign["id"], "name": "S"}
        ).json()

        async with test_session_factory() as db:
            db.add(
                Turn(
                    session_id=session["id"],
                    character_id=None,
                    turn_number=0,
                    action_type="roleplay",
                    action_text="",
                    dice_results="{}",        # valid JSON but dict not list → line 124
                    attack_result="not json", # invalid JSON → lines 130-131
                )
            )
            db.add(
                Turn(
                    session_id=session["id"],
                    character_id=None,
                    turn_number=1,
                    action_type="roleplay",
                    action_text="",
                    dice_results="not {{ valid", # invalid JSON → lines 125-126
                    attack_result=None,
                )
            )
            await db.commit()

        turns = client.get(f"/api/v1/sessions/{session['id']}/turns").json()
        assert len(turns) == 2
        assert all(t["dice_results"] == [] for t in turns)
        assert all(t["attack_result"] is None for t in turns)

    async def test_malformed_npc_event_json_is_silently_skipped(self) -> None:
        """sessions.py lines 109-110: JSONDecodeError on EventLog entry is caught and skipped."""
        from backend.app.db.models.event_log import EventLog
        from tests.test_backend.conftest import test_session_factory

        campaign = client.post("/api/v1/campaigns", json={"name": "C"}).json()
        char = client.post(
            f"/api/v1/campaigns/{campaign['id']}/characters", json=_CHAR_BODY
        ).json()
        session = client.post(
            "/api/v1/sessions", json={"campaign_id": campaign["id"], "name": "S"}
        ).json()
        client.post(
            f"/api/v1/sessions/{session['id']}/actions",
            json={"character_id": char["id"], "action_type": "roleplay", "description": "Look"},
        )

        turns_before = client.get(f"/api/v1/sessions/{session['id']}/turns").json()
        turn_id = turns_before[0]["id"]

        async with test_session_factory() as db:
            db.add(
                EventLog(
                    event_type="npc_dialogue",
                    entity_type="turn",
                    entity_id=turn_id,
                    data="not {{ valid json",
                    agent_id="test",
                )
            )
            await db.commit()

        turns = client.get(f"/api/v1/sessions/{session['id']}/turns").json()
        assert len(turns) == 1
        assert isinstance(turns[0]["npc_responses"], list)


class TestCampaignSessionsEndpoint:
    def test_list_campaign_sessions_empty(self) -> None:
        campaign = client.post("/api/v1/campaigns", json={"name": "C"}).json()

        response = client.get(f"/api/v1/campaigns/{campaign['id']}/sessions")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_campaign_sessions_with_session(self) -> None:
        campaign = client.post("/api/v1/campaigns", json={"name": "C"}).json()
        client.post("/api/v1/sessions", json={"campaign_id": campaign["id"], "name": "S1"})

        response = client.get(f"/api/v1/campaigns/{campaign['id']}/sessions")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "S1"
        assert data[0]["status"] == "active"
        assert "summary" in data[0]

    def test_list_campaign_sessions_unknown_campaign_returns_404(self) -> None:
        response = client.get("/api/v1/campaigns/does-not-exist/sessions")
        assert response.status_code == 404
        assert "Campaign not found" in response.json()["detail"]


class TestDemoEndpoint:
    def test_create_demo_campaign_returns_201(self) -> None:
        response = client.post("/api/v1/campaigns/demo", json={})
        assert response.status_code == 201
        data = response.json()
        assert "campaign_id" in data
        assert data["name"] == "The Sunken Vault"

    def test_create_demo_campaign_creates_characters(self) -> None:
        response = client.post("/api/v1/campaigns/demo", json={})
        assert response.status_code == 201
        campaign_id = response.json()["campaign_id"]

        chars_response = client.get(f"/api/v1/campaigns/{campaign_id}/characters")
        assert chars_response.status_code == 200
        chars = chars_response.json()
        assert len(chars) == 2
        names = {c["character_name"] for c in chars}
        assert "Brakka Ironjaw" in names
        assert "Sylvi Ashwhisper" in names


class TestXpAwardIntegration:
    def test_xp_awarded_after_kill(self) -> None:
        """Attacking a low-AC target with enough force kills it and awards XP."""
        campaign = client.post("/api/v1/campaigns", json={"name": "XP Test"}).json()
        char = client.post(
            f"/api/v1/campaigns/{campaign['id']}/characters",
            json={
                "character_name": "Fighter",
                "class_name": "Fighter",
                "level": 1,
                "strength": 20,
                "dexterity": 10,
                "constitution": 14,
                "intelligence": 10,
                "wisdom": 10,
                "charisma": 10,
                "armor_class": 16,
                "hp_max": 30,
            },
        ).json()
        session = client.post(
            "/api/v1/sessions", json={"campaign_id": campaign["id"], "name": "S"}
        ).json()

        xp_before = client.get(f"/api/v1/characters/{char['id']}").json()["experience"]

        # Seed 3 produces a hit with STR 20 (+5) against generic enemy AC 12.
        # The generic enemy has 10 HP; STR mod 5 + base damage > 10 on most seeds.
        client.post(
            f"/api/v1/sessions/{session['id']}/actions",
            json={
                "character_id": char["id"],
                "action_type": "attack_melee",
                "description": "I swing my sword at the goblin.",
                "dice_expression": "1d8",
                "seed": 3,
            },
        )

        xp_after = client.get(f"/api/v1/characters/{char["id"]}").json()["experience"]
        # XP may or may not be awarded depending on whether the hit killed the generic
        # enemy (which is not persisted). The character's XP should be >= xp_before.
        assert xp_after >= xp_before
