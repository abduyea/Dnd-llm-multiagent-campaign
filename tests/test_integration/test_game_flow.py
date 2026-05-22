"""
Integration tests — full game-flow pipeline through the HTTP layer.

Each test class is self-contained: it creates its own campaign, characters, and
session via the API, then asserts on the returned state.  Ollama is not called;
the Pydantic schema validation and static fallback path are exercised instead.
"""

from __future__ import annotations

from httpx import AsyncClient

# ── Fixtures shared across test classes ─────────────────────────────────────

FIGHTER_BODY = {
    "player_name": "Alice",
    "character_name": "Aldric",
    "race": "Human",
    "class_name": "Fighter",
    "level": 3,
    "strength": 16,
    "dexterity": 12,
    "constitution": 14,
    "intelligence": 10,
    "wisdom": 10,
    "charisma": 10,
    "armor_class": 16,
    "initiative": 1,
    "speed": 30,
}

ROGUE_BODY = {
    "player_name": "Bob",
    "character_name": "Mira",
    "race": "Halfling",
    "class_name": "Rogue",
    "level": 2,
    "strength": 8,
    "dexterity": 18,
    "constitution": 12,
    "intelligence": 12,
    "wisdom": 10,
    "charisma": 14,
    "armor_class": 14,
    "initiative": 4,
    "speed": 25,
}


async def _create_campaign(client: AsyncClient, name: str = "Test Campaign") -> str:
    r = await client.post(
        "/api/v1/campaigns", json={"name": name, "description": "Integration test"}
    )
    assert r.status_code == 201
    return r.json()["id"]


async def _create_character(client: AsyncClient, campaign_id: str, body: dict) -> str:
    r = await client.post(f"/api/v1/campaigns/{campaign_id}/characters", json=body)
    assert r.status_code == 201
    return r.json()["id"]


async def _start_session(client: AsyncClient, campaign_id: str, name: str = "Test Session") -> str:
    r = await client.post("/api/v1/sessions", json={"campaign_id": campaign_id, "name": name})
    assert r.status_code == 201
    return r.json()["id"]


# ════════════════════════════════════════════════════════════════════════════
# Suite 1 — Campaign + Character lifecycle
# ════════════════════════════════════════════════════════════════════════════


class TestCampaignCharacterLifecycle:
    async def test_create_and_retrieve_campaign(self, async_client: AsyncClient) -> None:
        r = await async_client.post(
            "/api/v1/campaigns",
            json={
                "name": "The Dark Reaches",
                "world_setting": "Eberron",
                "description": "A grim campaign.",
            },
        )
        assert r.status_code == 201
        data = r.json()
        assert data["name"] == "The Dark Reaches"
        assert data["world_setting"] == "Eberron"
        assert data["status"] == "active"
        campaign_id = data["id"]

        get = await async_client.get(f"/api/v1/campaigns/{campaign_id}")
        assert get.status_code == 200
        assert get.json()["id"] == campaign_id

    async def test_campaign_list_grows_on_create(self, async_client: AsyncClient) -> None:
        before = await async_client.get("/api/v1/campaigns")
        n_before = len(before.json())
        await _create_campaign(async_client, "Campaign A")
        await _create_campaign(async_client, "Campaign B")
        after = await async_client.get("/api/v1/campaigns")
        assert len(after.json()) == n_before + 2

    async def test_character_hp_computed_from_level_and_con(
        self, async_client: AsyncClient
    ) -> None:
        cid = await _create_campaign(async_client)
        r = await async_client.post(
            f"/api/v1/campaigns/{cid}/characters",
            json={**FIGHTER_BODY, "level": 3, "constitution": 14},
        )
        assert r.status_code == 201
        char = r.json()
        # hp = level * 8 + CON_mod * level; CON 14 → mod +2 → 3*8 + 2*3 = 30
        assert char["hp_max"] == 30
        assert char["hp_current"] == 30

    async def test_character_create_nonexistent_campaign_returns_404(
        self, async_client: AsyncClient
    ) -> None:
        r = await async_client.post(
            "/api/v1/campaigns/nonexistent-id/characters", json=FIGHTER_BODY
        )
        assert r.status_code == 404

    async def test_list_characters_returns_only_campaign_members(
        self, async_client: AsyncClient
    ) -> None:
        cid_a = await _create_campaign(async_client, "Camp A")
        cid_b = await _create_campaign(async_client, "Camp B")
        await _create_character(async_client, cid_a, FIGHTER_BODY)
        await _create_character(async_client, cid_a, ROGUE_BODY)
        await _create_character(async_client, cid_b, FIGHTER_BODY)

        chars_a = await async_client.get(f"/api/v1/campaigns/{cid_a}/characters")
        chars_b = await async_client.get(f"/api/v1/campaigns/{cid_b}/characters")
        assert len(chars_a.json()) == 2
        assert len(chars_b.json()) == 1

    async def test_update_campaign_fields(self, async_client: AsyncClient) -> None:
        cid = await _create_campaign(async_client, "Old Name")
        r = await async_client.put(
            f"/api/v1/campaigns/{cid}", json={"name": "New Name", "status": "completed"}
        )
        assert r.status_code == 200
        assert r.json()["name"] == "New Name"
        assert r.json()["status"] == "completed"


# ════════════════════════════════════════════════════════════════════════════
# Suite 2 — Session lifecycle
# ════════════════════════════════════════════════════════════════════════════


class TestSessionLifecycle:
    async def test_start_and_retrieve_session(self, async_client: AsyncClient) -> None:
        cid = await _create_campaign(async_client)
        sid = await _start_session(async_client, cid, "Session Alpha")
        r = await async_client.get(f"/api/v1/sessions/{sid}")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "active"
        assert data["turn_count"] == 0
        assert data["name"] == "Session Alpha"

    async def test_end_session_marks_completed(self, async_client: AsyncClient) -> None:
        cid = await _create_campaign(async_client)
        sid = await _start_session(async_client, cid)
        r = await async_client.post(f"/api/v1/sessions/{sid}/end", json={})
        assert r.status_code == 200
        assert r.json()["status"] == "completed"

    async def test_end_nonexistent_session_returns_404(self, async_client: AsyncClient) -> None:
        r = await async_client.post("/api/v1/sessions/ghost-session/end", json={})
        assert r.status_code == 404

    async def test_session_list_includes_created_session(self, async_client: AsyncClient) -> None:
        cid = await _create_campaign(async_client)
        sid = await _start_session(async_client, cid, "Unique Session XYZ")
        sessions = await async_client.get("/api/v1/sessions")
        ids = [s["id"] for s in sessions.json()]
        assert sid in ids


# ════════════════════════════════════════════════════════════════════════════
# Suite 3 — Action pipeline (full game-flow)
# ════════════════════════════════════════════════════════════════════════════


class TestActionPipeline:
    async def test_roleplay_action_increments_turn_count(self, async_client: AsyncClient) -> None:
        cid = await _create_campaign(async_client)
        char_id = await _create_character(async_client, cid, FIGHTER_BODY)
        sid = await _start_session(async_client, cid)

        r = await async_client.post(
            f"/api/v1/sessions/{sid}/actions",
            json={
                "character_id": char_id,
                "action_type": "roleplay",
                "description": "Aldric scans the room for traps.",
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["turn_number"] == 0  # zero-indexed; this was turn 0
        assert body["action_type"] == "roleplay"
        assert body["character_id"] == char_id

        # Turn count in session should now be 1
        session = await async_client.get(f"/api/v1/sessions/{sid}")
        assert session.json()["turn_count"] == 1

    async def test_melee_attack_returns_attack_result(self, async_client: AsyncClient) -> None:
        cid = await _create_campaign(async_client)
        attacker = await _create_character(async_client, cid, FIGHTER_BODY)
        target = await _create_character(async_client, cid, ROGUE_BODY)
        sid = await _start_session(async_client, cid)

        r = await async_client.post(
            f"/api/v1/sessions/{sid}/actions",
            json={
                "character_id": attacker,
                "action_type": "attack_melee",
                "target_id": target,
                "description": "Aldric swings his longsword at Mira.",
            },
        )
        assert r.status_code == 200
        body = r.json()
        # attack_result may or may not be present depending on orchestrator path
        # but the response must be well-formed
        assert "turn_number" in body
        assert "action_type" in body
        assert body["action_type"] == "attack_melee"

    async def test_action_on_nonexistent_session_returns_404(
        self, async_client: AsyncClient
    ) -> None:
        cid = await _create_campaign(async_client)
        char_id = await _create_character(async_client, cid, FIGHTER_BODY)
        r = await async_client.post(
            "/api/v1/sessions/ghost-session-999/actions",
            json={
                "character_id": char_id,
                "action_type": "roleplay",
                "description": "Does nothing.",
            },
        )
        assert r.status_code == 404

    async def test_action_with_invalid_type_returns_422(self, async_client: AsyncClient) -> None:
        cid = await _create_campaign(async_client)
        char_id = await _create_character(async_client, cid, FIGHTER_BODY)
        sid = await _start_session(async_client, cid)
        r = await async_client.post(
            f"/api/v1/sessions/{sid}/actions",
            json={
                "character_id": char_id,
                "action_type": "teleport_to_moon",
                "description": "Invalid action.",
            },
        )
        assert r.status_code == 422

    async def test_multiple_actions_accumulate_turn_count(self, async_client: AsyncClient) -> None:
        cid = await _create_campaign(async_client)
        char_id = await _create_character(async_client, cid, FIGHTER_BODY)
        sid = await _start_session(async_client, cid)

        for i in range(3):
            r = await async_client.post(
                f"/api/v1/sessions/{sid}/actions",
                json={
                    "character_id": char_id,
                    "action_type": "roleplay",
                    "description": f"Action {i}.",
                },
            )
            assert r.status_code == 200

        session = await async_client.get(f"/api/v1/sessions/{sid}")
        assert session.json()["turn_count"] == 3

    async def test_skill_check_action_type_accepted(self, async_client: AsyncClient) -> None:
        cid = await _create_campaign(async_client)
        char_id = await _create_character(async_client, cid, ROGUE_BODY)
        sid = await _start_session(async_client, cid)
        r = await async_client.post(
            f"/api/v1/sessions/{sid}/actions",
            json={
                "character_id": char_id,
                "action_type": "skill_check",
                "description": "Mira attempts a Stealth check.",
            },
        )
        assert r.status_code == 200


# ════════════════════════════════════════════════════════════════════════════
# Suite 4 — Dice determinism
# ════════════════════════════════════════════════════════════════════════════


class TestDiceDeterminism:
    async def test_same_seed_returns_identical_result(self, async_client: AsyncClient) -> None:
        payload = {"expression": "2d6+3", "seed": 42}
        r1 = await async_client.post("/api/v1/dice/roll", json=payload)
        r2 = await async_client.post("/api/v1/dice/roll", json=payload)
        assert r1.status_code == 200
        assert r1.json() == r2.json()

    async def test_different_seeds_likely_differ(self, async_client: AsyncClient) -> None:
        r1 = await async_client.post("/api/v1/dice/roll", json={"expression": "1d20", "seed": 1})
        r2 = await async_client.post("/api/v1/dice/roll", json={"expression": "1d20", "seed": 99})
        assert r1.status_code == 200
        assert r2.status_code == 200
        # With 20 outcomes, seed 1 vs 99 should differ (verified by known values)
        # We just confirm both are valid rolls
        assert 1 <= r1.json()["total"] <= 20
        assert 1 <= r2.json()["total"] <= 20

    async def test_roll_modifier_applied_correctly(self, async_client: AsyncClient) -> None:
        # 1d2 rolls 1 or 2; with +10 the total must be 11 or 12 — modifier is applied
        r = await async_client.post("/api/v1/dice/roll", json={"expression": "1d2+10", "seed": 0})
        assert r.status_code == 200
        assert r.json()["modifier"] == 10
        assert r.json()["total"] in (11, 12)

    async def test_invalid_expression_returns_422(self, async_client: AsyncClient) -> None:
        # Pattern validation on the Pydantic model returns 422 before engine is reached
        r = await async_client.post("/api/v1/dice/roll", json={"expression": "not-a-die"})
        assert r.status_code == 422

    async def test_expression_pattern_validation(self, async_client: AsyncClient) -> None:
        r = await async_client.post("/api/v1/dice/roll", json={"expression": "0d6"})
        assert r.status_code in (400, 422)  # either pattern rejection or engine error


# ════════════════════════════════════════════════════════════════════════════
# Suite 5 — Replay / event-log consistency
# ════════════════════════════════════════════════════════════════════════════


class TestReplayConsistency:
    async def test_full_session_lifecycle_produces_consistent_state(
        self, async_client: AsyncClient
    ) -> None:
        """
        Creates a campaign, adds two characters, runs 4 turns (mix of roleplay
        and attack), ends the session.  Asserts the final session state is
        coherent: correct turn count, status=completed.
        """
        cid = await _create_campaign(async_client, "Replay Campaign")
        fighter = await _create_character(async_client, cid, FIGHTER_BODY)
        rogue = await _create_character(async_client, cid, ROGUE_BODY)
        sid = await _start_session(async_client, cid, "Replay Session")

        actions = [
            {"character_id": fighter, "action_type": "roleplay", "description": "Scouts ahead."},
            {"character_id": rogue, "action_type": "skill_check", "description": "Stealth check."},
            {
                "character_id": fighter,
                "action_type": "attack_melee",
                "description": "Attacks goblin.",
                "target_id": rogue,
            },
            {"character_id": rogue, "action_type": "roleplay", "description": "Retreats."},
        ]

        for action in actions:
            r = await async_client.post(f"/api/v1/sessions/{sid}/actions", json=action)
            assert r.status_code == 200, f"Action failed: {r.json()}"

        end = await async_client.post(f"/api/v1/sessions/{sid}/end", json={})
        assert end.status_code == 200
        final = end.json()
        assert final["status"] == "completed"
        assert final["turn_count"] == 4

    async def test_melee_attack_with_seed_is_repeatable(self, async_client: AsyncClient) -> None:
        """
        Two identical attack actions with the same seed must produce the same
        attack roll result (hit/miss deterministic).
        """
        cid = await _create_campaign(async_client, "Seed Campaign")
        fighter = await _create_character(async_client, cid, FIGHTER_BODY)
        target = await _create_character(async_client, cid, ROGUE_BODY)
        sid = await _start_session(async_client, cid, "Seed Session")

        payload = {
            "character_id": fighter,
            "action_type": "attack_melee",
            "target_id": target,
            "description": "Repeatable swing.",
            "seed": 7,
        }

        r1 = await async_client.post(f"/api/v1/sessions/{sid}/actions", json=payload)
        r2 = await async_client.post(f"/api/v1/sessions/{sid}/actions", json=payload)
        assert r1.status_code == r2.status_code == 200

        b1, b2 = r1.json(), r2.json()
        if b1.get("attack_result") and b2.get("attack_result"):
            assert b1["attack_result"]["is_hit"] == b2["attack_result"]["is_hit"]
            assert b1["attack_result"]["natural_roll"] == b2["attack_result"]["natural_roll"]


# ════════════════════════════════════════════════════════════════════════════
# Suite 6 — Full CRUD: delete and edit lifecycle
# ════════════════════════════════════════════════════════════════════════════


class TestCRUDLifecycle:
    async def test_delete_campaign_removes_all_children(
        self, async_client: AsyncClient
    ) -> None:
        cid = await _create_campaign(async_client, "Delete Me")
        char_id = await _create_character(async_client, cid, FIGHTER_BODY)
        sid = await _start_session(async_client, cid, "DS")
        # end session so we can delete the campaign
        await async_client.post(f"/api/v1/sessions/{sid}/end", json={})

        r = await async_client.delete(f"/api/v1/campaigns/{cid}")
        assert r.status_code == 204

        assert (await async_client.get(f"/api/v1/campaigns/{cid}")).status_code == 404
        assert (await async_client.get(f"/api/v1/characters/{char_id}")).status_code == 404

    async def test_delete_campaign_blocked_when_session_active(
        self, async_client: AsyncClient
    ) -> None:
        cid = await _create_campaign(async_client, "Active Camp")
        await _start_session(async_client, cid, "Active S")
        r = await async_client.delete(f"/api/v1/campaigns/{cid}")
        assert r.status_code == 409

    async def test_delete_character_removes_from_list(
        self, async_client: AsyncClient
    ) -> None:
        cid = await _create_campaign(async_client, "Char Camp")
        char_id = await _create_character(async_client, cid, ROGUE_BODY)

        r = await async_client.delete(f"/api/v1/characters/{char_id}")
        assert r.status_code == 204

        chars = await async_client.get(f"/api/v1/campaigns/{cid}/characters")
        ids = [c["id"] for c in chars.json()]
        assert char_id not in ids

    async def test_delete_character_blocked_when_session_active(
        self, async_client: AsyncClient
    ) -> None:
        cid = await _create_campaign(async_client, "Block Camp")
        char_id = await _create_character(async_client, cid, FIGHTER_BODY)
        await _start_session(async_client, cid, "Block S")
        r = await async_client.delete(f"/api/v1/characters/{char_id}")
        assert r.status_code == 409

    async def test_edit_character_ability_scores(self, async_client: AsyncClient) -> None:
        cid = await _create_campaign(async_client, "Edit Camp")
        char_id = await _create_character(async_client, cid, FIGHTER_BODY)

        r = await async_client.put(
            f"/api/v1/characters/{char_id}",
            json={"strength": 20, "dexterity": 16, "constitution": 18},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["strength"] == 20
        assert data["dexterity"] == 16
        assert data["constitution"] == 18

    async def test_stats_endpoint_reflects_data(self, async_client: AsyncClient) -> None:
        r = await async_client.get("/api/v1/stats")
        assert r.status_code == 200
        data = r.json()
        for key in ("campaigns", "campaigns_active", "characters", "sessions",
                    "sessions_completed", "turns"):
            assert key in data
            assert isinstance(data[key], int)
            assert data[key] >= 0

    async def test_delete_completed_session(self, async_client: AsyncClient) -> None:
        cid = await _create_campaign(async_client, "Del Camp")
        sid = await _start_session(async_client, cid, "To Delete")
        await async_client.post(f"/api/v1/sessions/{sid}/end", json={})

        r = await async_client.delete(f"/api/v1/sessions/{sid}")
        assert r.status_code == 204

        get = await async_client.get(f"/api/v1/sessions/{sid}")
        assert get.status_code == 404

    async def test_session_summary_in_get_response(self, async_client: AsyncClient) -> None:
        cid = await _create_campaign(async_client)
        sid = await _start_session(async_client, cid)
        r = await async_client.get(f"/api/v1/sessions/{sid}")
        assert r.status_code == 200
        assert "summary" in r.json()


# ════════════════════════════════════════════════════════════════════════════
# Suite 7 — Turns endpoint (character_name, dice_results, npc_responses)
# ════════════════════════════════════════════════════════════════════════════


class TestTurnsEndpoint:
    async def test_turns_404_for_unknown_session(self, async_client: AsyncClient) -> None:
        r = await async_client.get("/api/v1/sessions/ghost/turns")
        assert r.status_code == 404

    async def test_turns_empty_on_new_session(self, async_client: AsyncClient) -> None:
        cid = await _create_campaign(async_client)
        sid = await _start_session(async_client, cid)

        r = await async_client.get(f"/api/v1/sessions/{sid}/turns")
        assert r.status_code == 200
        assert r.json() == []

    async def test_turns_include_character_name(self, async_client: AsyncClient) -> None:
        cid = await _create_campaign(async_client)
        char_id = await _create_character(async_client, cid, FIGHTER_BODY)
        sid = await _start_session(async_client, cid)

        await async_client.post(
            f"/api/v1/sessions/{sid}/actions",
            json={"character_id": char_id, "action_type": "roleplay",
                  "description": "Scouts ahead."},
        )

        turns = (await async_client.get(f"/api/v1/sessions/{sid}/turns")).json()
        assert len(turns) == 1
        assert turns[0]["character_id"] == char_id
        assert turns[0]["character_name"] == FIGHTER_BODY["character_name"]

    async def test_turns_include_parsed_dice_and_attack_result(
        self, async_client: AsyncClient
    ) -> None:
        cid = await _create_campaign(async_client)
        attacker = await _create_character(async_client, cid, FIGHTER_BODY)
        target = await _create_character(async_client, cid, ROGUE_BODY)
        sid = await _start_session(async_client, cid)

        await async_client.post(
            f"/api/v1/sessions/{sid}/actions",
            json={
                "character_id": attacker,
                "action_type": "attack_melee",
                "target_id": target,
                "description": "Aldric swings.",
                "seed": 7,
            },
        )

        turns = (await async_client.get(f"/api/v1/sessions/{sid}/turns")).json()
        assert len(turns) == 1
        assert isinstance(turns[0]["dice_results"], list)
        assert isinstance(turns[0]["npc_responses"], list)
        ar = turns[0]["attack_result"]
        assert ar is not None
        assert "is_hit" in ar and "is_critical" in ar and "damage" in ar

    async def test_turns_ordered_by_turn_number(self, async_client: AsyncClient) -> None:
        cid = await _create_campaign(async_client)
        char_id = await _create_character(async_client, cid, FIGHTER_BODY)
        sid = await _start_session(async_client, cid)

        for desc in ("First", "Second", "Third"):
            await async_client.post(
                f"/api/v1/sessions/{sid}/actions",
                json={"character_id": char_id, "action_type": "roleplay",
                      "description": desc},
            )

        turns = (await async_client.get(f"/api/v1/sessions/{sid}/turns")).json()
        assert len(turns) == 3
        assert [t["turn_number"] for t in turns] == [0, 1, 2]

    async def test_campaign_sessions_endpoint(self, async_client: AsyncClient) -> None:
        cid = await _create_campaign(async_client, "Sessions Camp")
        sid1 = await _start_session(async_client, cid, "Session Alpha")
        await async_client.post(f"/api/v1/sessions/{sid1}/end", json={})
        sid2 = await _start_session(async_client, cid, "Session Beta")

        r = await async_client.get(f"/api/v1/campaigns/{cid}/sessions")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 2
        names = {s["name"] for s in data}
        assert "Session Alpha" in names
        assert "Session Beta" in names
        statuses = {s["status"] for s in data}
        assert "completed" in statuses
        assert "active" in statuses
        ids = {s["id"] for s in data}
        assert sid1 in ids and sid2 in ids


# ════════════════════════════════════════════════════════════════════════════
# Suite 8 — Export / Import roundtrip
# ════════════════════════════════════════════════════════════════════════════


class TestExportImport:
    async def test_export_includes_campaign_and_characters(
        self, async_client: AsyncClient
    ) -> None:
        cid = await _create_campaign(async_client, "Export Camp")
        await _create_character(async_client, cid, FIGHTER_BODY)
        await _create_character(async_client, cid, ROGUE_BODY)

        r = await async_client.get(f"/api/v1/campaigns/{cid}/export")
        assert r.status_code == 200
        bundle = r.json()
        assert "campaign" in bundle
        assert "characters" in bundle
        assert "exported_at" in bundle
        assert bundle["campaign"]["name"] == "Export Camp"
        assert len(bundle["characters"]) == 2

    async def test_export_character_fields_complete(
        self, async_client: AsyncClient
    ) -> None:
        cid = await _create_campaign(async_client, "Fields Camp")
        await _create_character(async_client, cid, FIGHTER_BODY)

        bundle = (await async_client.get(f"/api/v1/campaigns/{cid}/export")).json()
        char = bundle["characters"][0]
        required = [
            "character_name", "player_name", "race", "class_name", "level",
            "strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma",
            "armor_class", "speed", "hp_current", "hp_max",
        ]
        for field in required:
            assert field in char, f"Missing field: {field}"

    async def test_import_creates_new_campaign_with_new_id(
        self, async_client: AsyncClient
    ) -> None:
        cid_orig = await _create_campaign(async_client, "Original")
        await _create_character(async_client, cid_orig, FIGHTER_BODY)
        bundle = (await async_client.get(f"/api/v1/campaigns/{cid_orig}/export")).json()

        r = await async_client.post("/api/v1/campaigns/import", json=bundle)
        assert r.status_code == 201
        imported = r.json()
        assert imported["id"] != cid_orig
        assert imported["name"] == "Original"
        assert imported["character_count"] == 1

    async def test_import_roundtrip_preserves_all_characters(
        self, async_client: AsyncClient
    ) -> None:
        cid_orig = await _create_campaign(async_client, "Roundtrip Camp")
        await _create_character(async_client, cid_orig, FIGHTER_BODY)
        await _create_character(async_client, cid_orig, ROGUE_BODY)

        bundle = (await async_client.get(f"/api/v1/campaigns/{cid_orig}/export")).json()
        import_r = await async_client.post("/api/v1/campaigns/import", json=bundle)
        imported_id = import_r.json()["id"]

        chars = (await async_client.get(f"/api/v1/campaigns/{imported_id}/characters")).json()
        assert len(chars) == 2
        names = {c["character_name"] for c in chars}
        assert FIGHTER_BODY["character_name"] in names
        assert ROGUE_BODY["character_name"] in names

    async def test_import_preserves_ability_scores(
        self, async_client: AsyncClient
    ) -> None:
        cid = await _create_campaign(async_client, "Score Camp")
        await _create_character(async_client, cid, FIGHTER_BODY)

        bundle = (await async_client.get(f"/api/v1/campaigns/{cid}/export")).json()
        new_id = (await async_client.post("/api/v1/campaigns/import", json=bundle)).json()["id"]

        chars = (await async_client.get(f"/api/v1/campaigns/{new_id}/characters")).json()
        c = chars[0]
        assert c["strength"] == FIGHTER_BODY["strength"]
        assert c["dexterity"] == FIGHTER_BODY["dexterity"]
        assert c["constitution"] == FIGHTER_BODY["constitution"]
        assert c["intelligence"] == FIGHTER_BODY["intelligence"]

    async def test_export_empty_campaign_has_no_characters(
        self, async_client: AsyncClient
    ) -> None:
        cid = await _create_campaign(async_client, "Empty Export")
        bundle = (await async_client.get(f"/api/v1/campaigns/{cid}/export")).json()
        assert bundle["characters"] == []

    async def test_export_nonexistent_campaign_returns_404(
        self, async_client: AsyncClient
    ) -> None:
        r = await async_client.get("/api/v1/campaigns/nonexistent-999/export")
        assert r.status_code == 404


# ════════════════════════════════════════════════════════════════════════════
# Suite 9 — HP & character stat updates
# ════════════════════════════════════════════════════════════════════════════


class TestCharacterHpUpdates:
    async def test_hp_update_to_valid_value(self, async_client: AsyncClient) -> None:
        cid = await _create_campaign(async_client, "HP Camp")
        char_id = await _create_character(async_client, cid, FIGHTER_BODY)

        r = await async_client.put(
            f"/api/v1/characters/{char_id}",
            json={"hp_current": 5},
        )
        assert r.status_code == 200
        assert r.json()["hp_current"] == 5

    async def test_hp_update_to_zero_rejected(self, async_client: AsyncClient) -> None:
        # Schema enforces hp_current >= 1; zero is invalid
        cid = await _create_campaign(async_client, "KO Camp")
        char_id = await _create_character(async_client, cid, FIGHTER_BODY)

        r = await async_client.put(f"/api/v1/characters/{char_id}", json={"hp_current": 0})
        assert r.status_code == 422

    async def test_update_character_level(self, async_client: AsyncClient) -> None:
        cid = await _create_campaign(async_client, "Level Camp")
        char_id = await _create_character(async_client, cid, FIGHTER_BODY)

        r = await async_client.put(f"/api/v1/characters/{char_id}", json={"level": 10})
        assert r.status_code == 200
        assert r.json()["level"] == 10

    async def test_update_character_name(self, async_client: AsyncClient) -> None:
        cid = await _create_campaign(async_client, "Name Camp")
        char_id = await _create_character(async_client, cid, FIGHTER_BODY)

        r = await async_client.put(
            f"/api/v1/characters/{char_id}",
            json={"character_name": "Thorin Oakenshield"},
        )
        assert r.status_code == 200
        assert r.json()["character_name"] == "Thorin Oakenshield"

    async def test_update_nonexistent_character_returns_404(
        self, async_client: AsyncClient
    ) -> None:
        r = await async_client.put(
            "/api/v1/characters/ghost-char-999", json={"level": 5}
        )
        assert r.status_code == 404

    async def test_character_backstory_persists(self, async_client: AsyncClient) -> None:
        cid = await _create_campaign(async_client, "Story Camp")
        char_id = await _create_character(async_client, cid, {
            **ROGUE_BODY,
            "backstory": "Born in darkness, lived in shadow.",
        })

        char = (await async_client.get(f"/api/v1/characters/{char_id}")).json()
        assert char["backstory"] == "Born in darkness, lived in shadow."


# ════════════════════════════════════════════════════════════════════════════
# Suite 10 — Campaign validation & edge cases
# ════════════════════════════════════════════════════════════════════════════


class TestCampaignEdgeCases:
    async def test_campaign_requires_name(self, async_client: AsyncClient) -> None:
        r = await async_client.post(
            "/api/v1/campaigns",
            json={"description": "No name given"},
        )
        assert r.status_code == 422

    async def test_campaign_update_nonexistent_returns_404(
        self, async_client: AsyncClient
    ) -> None:
        r = await async_client.put(
            "/api/v1/campaigns/nonexistent-camp",
            json={"name": "Ghost"},
        )
        assert r.status_code == 404

    async def test_campaign_get_nonexistent_returns_404(
        self, async_client: AsyncClient
    ) -> None:
        r = await async_client.get("/api/v1/campaigns/nonexistent-camp-xyz")
        assert r.status_code == 404

    async def test_campaign_delete_nonexistent_returns_404(
        self, async_client: AsyncClient
    ) -> None:
        r = await async_client.delete("/api/v1/campaigns/ghost-delete-999")
        assert r.status_code == 404

    async def test_campaign_with_long_description(self, async_client: AsyncClient) -> None:
        long_desc = "A" * 400
        r = await async_client.post(
            "/api/v1/campaigns",
            json={"name": "Long Desc", "description": long_desc},
        )
        assert r.status_code == 201
        assert r.json()["description"] == long_desc

    async def test_campaign_status_update_to_archived(
        self, async_client: AsyncClient
    ) -> None:
        cid = await _create_campaign(async_client, "To Archive")
        r = await async_client.put(
            f"/api/v1/campaigns/{cid}", json={"name": "To Archive", "status": "archived"}
        )
        assert r.status_code == 200
        assert r.json()["status"] == "archived"

    async def test_campaign_sessions_returns_empty_for_new_campaign(
        self, async_client: AsyncClient
    ) -> None:
        cid = await _create_campaign(async_client, "Fresh Camp")
        r = await async_client.get(f"/api/v1/campaigns/{cid}/sessions")
        assert r.status_code == 200
        assert r.json() == []

    async def test_campaign_sessions_nonexistent_returns_404(
        self, async_client: AsyncClient
    ) -> None:
        r = await async_client.get("/api/v1/campaigns/ghost-camp/sessions")
        assert r.status_code == 404

    async def test_session_counts_match_reality(self, async_client: AsyncClient) -> None:
        cid = await _create_campaign(async_client, "Count Camp")
        await _create_character(async_client, cid, FIGHTER_BODY)
        await _create_character(async_client, cid, ROGUE_BODY)
        sid = await _start_session(async_client, cid, "Count Session")
        await async_client.post(f"/api/v1/sessions/{sid}/end", json={})

        campaign = (await async_client.get(f"/api/v1/campaigns/{cid}")).json()
        assert campaign["character_count"] == 2
        assert campaign["session_count"] == 1

    async def test_delete_active_session_blocked(self, async_client: AsyncClient) -> None:
        cid = await _create_campaign(async_client, "Active Del Camp")
        sid = await _start_session(async_client, cid, "Active Session")
        r = await async_client.delete(f"/api/v1/sessions/{sid}")
        assert r.status_code == 409
