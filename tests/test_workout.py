"""Tests for workout recording, PR detection, training detail, and exercise progression."""

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import (
    Exercise,
    ExerciseAlias,
    ExerciseMuscle,
    MuscleGroup,
    MuscleGroupAlias,
    User,
)
from src.services.workout import (
    get_exercise_catalog,
    get_exercise_progression,
    get_or_create_session,
    get_personal_records,
    get_training_detail,
    get_training_history,
    record_exercises,
    resolve_exercise,
    save_raw_record,
    search_exercises,
)


async def test_get_or_create_session(db: AsyncSession, user: User):
    training_date = date(2026, 3, 12)

    session1, is_new1 = await get_or_create_session(db, user.id, training_date, "self_training")
    assert is_new1 is True
    assert session1.date == training_date

    session2, is_new2 = await get_or_create_session(db, user.id, training_date, "coach")
    assert is_new2 is False
    assert session2.id == session1.id


async def test_resolve_exercise_by_alias(db: AsyncSession, seed_exercises: dict[str, Exercise]):
    exercise = await resolve_exercise(db, "深蹲")
    assert exercise is not None
    assert exercise.name_zh == "槓鈴背蹲"


async def test_resolve_exercise_by_name_zh(db: AsyncSession, seed_exercises: dict[str, Exercise]):
    exercise = await resolve_exercise(db, "槓鈴背蹲")
    assert exercise is not None
    assert exercise.name == "Barbell Back Squat"


async def test_resolve_exercise_not_found(db: AsyncSession, seed_exercises: dict[str, Exercise]):
    exercise = await resolve_exercise(db, "不存在的動作")
    assert exercise is None


async def test_record_exercises_with_pr(
    db: AsyncSession, user: User, seed_exercises: dict[str, Exercise]
):
    training_date = date(2026, 3, 12)
    session, _ = await get_or_create_session(db, user.id, training_date, "self_training")

    exercises_data = [
        {
            "exercise_name": "深蹲",
            "sets": [
                {
                    "weight_value": 40,
                    "weight_type": "total",
                    "weight_unit": "kg",
                    "reps_min": 10,
                    "num_sets": 4,
                },
            ],
        },
    ]
    results = await record_exercises(db, user.id, session.id, exercises_data)

    assert len(results) == 1
    assert results[0]["exercise_name"] == "槓鈴背蹲"
    assert results[0]["matched"] is True
    assert results[0]["pr"] is not None
    assert results[0]["pr"]["is_first"] is True


async def test_record_unmatched_exercise(db: AsyncSession, user: User, seed_exercises: dict):
    training_date = date(2026, 3, 12)
    session, _ = await get_or_create_session(db, user.id, training_date, "self_training")

    exercises_data = [
        {
            "exercise_name": "自創動作",
            "sets": [{"reps_min": 15, "num_sets": 3}],
        },
    ]
    results = await record_exercises(db, user.id, session.id, exercises_data)

    assert results[0]["exercise_name"] == "自創動作"
    assert results[0]["matched"] is False
    assert results[0]["pr"] is None


async def test_pr_updates_on_heavier_weight(
    db: AsyncSession, user: User, seed_exercises: dict[str, Exercise]
):
    d1 = date(2026, 3, 10)
    s1, _ = await get_or_create_session(db, user.id, d1, "self_training")
    await record_exercises(
        db,
        user.id,
        s1.id,
        [
            {
                "exercise_name": "深蹲",
                "sets": [
                    {
                        "weight_value": 40,
                        "weight_type": "total",
                        "weight_unit": "kg",
                        "reps_min": 10,
                        "num_sets": 4,
                    }
                ],
            },
        ],
    )

    d2 = date(2026, 3, 12)
    s2, _ = await get_or_create_session(db, user.id, d2, "self_training")
    results = await record_exercises(
        db,
        user.id,
        s2.id,
        [
            {
                "exercise_name": "深蹲",
                "sets": [
                    {
                        "weight_value": 50,
                        "weight_type": "total",
                        "weight_unit": "kg",
                        "reps_min": 8,
                        "num_sets": 3,
                    }
                ],
            },
        ],
    )

    assert results[0]["pr"] is not None
    assert results[0]["pr"]["is_first"] is False
    assert results[0]["pr"]["new_best"] == "50kg"

    prs = await get_personal_records(db, user.id)
    assert len(prs) == 1
    assert prs[0]["best"] == "50kg"


async def test_assisted_pr_lower_is_better(
    db: AsyncSession, user: User, seed_exercises: dict[str, Exercise]
):
    d1 = date(2026, 3, 10)
    s1, _ = await get_or_create_session(db, user.id, d1, "self_training")
    await record_exercises(
        db,
        user.id,
        s1.id,
        [
            {
                "exercise_name": "dip",
                "sets": [
                    {
                        "weight_value": 20,
                        "weight_type": "counterweight",
                        "weight_unit": "kg",
                        "reps_min": 8,
                        "num_sets": 3,
                    }
                ],
            },
        ],
    )

    d2 = date(2026, 3, 12)
    s2, _ = await get_or_create_session(db, user.id, d2, "self_training")
    results = await record_exercises(
        db,
        user.id,
        s2.id,
        [
            {
                "exercise_name": "dip",
                "sets": [
                    {
                        "weight_value": 15,
                        "weight_type": "counterweight",
                        "weight_unit": "kg",
                        "reps_min": 8,
                        "num_sets": 3,
                    }
                ],
            },
        ],
    )

    assert results[0]["pr"] is not None
    assert results[0]["pr"]["new_best"] == "15kg counterweight"


async def test_get_training_history(
    db: AsyncSession, user: User, seed_exercises: dict, today: date
):
    d = today
    s, _ = await get_or_create_session(db, user.id, d, "coach")
    await record_exercises(
        db,
        user.id,
        s.id,
        [
            {
                "exercise_name": "深蹲",
                "sets": [{"weight_value": 40, "reps_min": 10, "num_sets": 4}],
            },
        ],
    )

    history = await get_training_history(db, user.id, days=7)
    assert len(history) == 1
    assert history[0]["session_type"] == "coach"
    assert "槓鈴背蹲" in history[0]["exercises"]


async def test_get_training_detail(db: AsyncSession, user: User, seed_exercises: dict):
    d = date(2026, 3, 12)
    s, _ = await get_or_create_session(db, user.id, d, "self_training")
    await record_exercises(
        db,
        user.id,
        s.id,
        [
            {
                "exercise_name": "深蹲",
                "sets": [
                    {
                        "weight_value": 40,
                        "weight_type": "total",
                        "weight_unit": "kg",
                        "reps_min": 10,
                        "num_sets": 4,
                    }
                ],
            },
        ],
    )

    detail = await get_training_detail(db, user.id, target_date=d)
    assert len(detail) == 1
    assert detail[0]["exercises"][0]["name"] == "槓鈴背蹲"
    assert len(detail[0]["exercises"][0]["sets"]) == 1
    assert "40" in detail[0]["exercises"][0]["sets"][0]


async def test_get_exercise_progression(
    db: AsyncSession, user: User, seed_exercises: dict, today: date
):
    for i, weight in enumerate([40, 42.5, 45]):
        d = today - timedelta(days=6 - i * 3)
        s, _ = await get_or_create_session(db, user.id, d, "self_training")
        await record_exercises(
            db,
            user.id,
            s.id,
            [
                {
                    "exercise_name": "深蹲",
                    "sets": [
                        {
                            "weight_value": weight,
                            "weight_type": "total",
                            "weight_unit": "kg",
                            "reps_min": 10,
                            "num_sets": 4,
                        }
                    ],
                },
            ],
        )

    prog = await get_exercise_progression(db, user.id, "深蹲", days=30)
    assert prog["exercise"] == "槓鈴背蹲"
    assert prog["total_sessions"] == 3
    assert len(prog["progression"]) == 3


async def test_save_raw_record(db: AsyncSession, user: User):
    await save_raw_record(db, user.id, "test content", "workout")
    await db.flush()


# ---------------------------------------------------------------------------
# spec-004: fuzzy / muscle-group / catalog / session_type on records
# ---------------------------------------------------------------------------


async def _add_deadlift_family(db: AsyncSession) -> dict[str, Exercise]:
    """Seed a hinge-family (槓鈴硬舉, 相撲硬舉, 槓鈴RDL) to exercise the broadening."""
    hams_result = await db.execute(
        select(MuscleGroup).where(MuscleGroup.name == "Hamstrings")
    )
    hams = hams_result.scalar_one_or_none()
    if hams is None:
        hams = MuscleGroup(name="Hamstrings", name_zh="膕繩肌", category="lower_body")
        db.add(hams)
        await db.flush()

    bb_dl = Exercise(
        name="Barbell Deadlift",
        name_zh="槓鈴硬舉",
        type="strength",
        equipment="barbell",
        movement_pattern="hinge",
        is_assisted=False,
    )
    sumo = Exercise(
        name="Sumo Deadlift",
        name_zh="相撲硬舉",
        type="strength",
        equipment="barbell",
        movement_pattern="hinge",
        is_assisted=False,
    )
    rdl = Exercise(
        name="Barbell RDL",
        name_zh="槓鈴RDL",
        type="strength",
        equipment="barbell",
        movement_pattern="hinge",
        is_assisted=False,
    )
    db.add_all([bb_dl, sumo, rdl])
    await db.flush()
    db.add_all(
        [
            ExerciseAlias(exercise_id=bb_dl.id, alias="硬舉"),
            ExerciseAlias(exercise_id=sumo.id, alias="史密斯相撲硬舉"),
            ExerciseAlias(exercise_id=rdl.id, alias="RDL"),
            ExerciseMuscle(exercise_id=bb_dl.id, muscle_group_id=hams.id, is_primary=True),
            ExerciseMuscle(exercise_id=sumo.id, muscle_group_id=hams.id, is_primary=True),
            ExerciseMuscle(exercise_id=rdl.id, muscle_group_id=hams.id, is_primary=True),
        ]
    )
    await db.flush()
    return {"bb_dl": bb_dl, "sumo": sumo, "rdl": rdl}


async def test_search_exercises_by_alias_substring(
    db: AsyncSession, seed_exercises: dict[str, Exercise]
):
    family = await _add_deadlift_family(db)
    matches = await search_exercises(db, query="硬舉")
    matched_ids = {ex.id for ex in matches}
    assert family["bb_dl"].id in matched_ids
    assert family["sumo"].id in matched_ids
    # RDL only has 'RDL' alias and English 'Barbell RDL' name — should NOT
    # match '硬舉' (since 硬舉 is not a substring of any RDL field).
    assert family["rdl"].id not in matched_ids


async def test_search_exercises_by_muscle_group_groups_family(
    db: AsyncSession, seed_exercises: dict[str, Exercise]
):
    family = await _add_deadlift_family(db)
    matches = await search_exercises(db, muscle_group="膕繩肌")
    matched_ids = {ex.id for ex in matches}
    # All three hinge exercises share Hamstrings — broad muscle search picks
    # up all of them, including RDL which doesn't have 硬舉 in its name.
    assert {family["bb_dl"].id, family["sumo"].id, family["rdl"].id} <= matched_ids

    # English muscle name should work the same.
    matches_en = await search_exercises(db, muscle_group="Hamstrings")
    assert {ex.id for ex in matches_en} == matched_ids


async def test_search_exercises_muscle_group_via_alias_fan_out(
    db: AsyncSession, seed_exercises: dict[str, Exercise]
):
    """'肩' should fan out to all 3 deltoid muscle groups via the alias table.

    This is the case substring match alone CANNOT solve, since 三角肌 doesn't
    contain the character 肩. Curated MuscleGroupAlias rows are required.
    """
    # Seed deltoid muscle groups + alias rows.
    ant = MuscleGroup(name="Anterior Deltoids", name_zh="前三角肌", category="upper_push")
    lat = MuscleGroup(name="Lateral Deltoids", name_zh="中三角肌", category="upper_push")
    rear = MuscleGroup(name="Rear Deltoids", name_zh="後三角肌", category="upper_pull")
    db.add_all([ant, lat, rear])
    await db.flush()
    for mg in (ant, lat, rear):
        db.add(MuscleGroupAlias(muscle_group_id=mg.id, alias="肩"))
        db.add(MuscleGroupAlias(muscle_group_id=mg.id, alias="shoulder"))
    await db.flush()

    # Three exercises, one per deltoid head.
    ohp = Exercise(
        name="Overhead Press", name_zh="肩推", type="strength",
        equipment="barbell", movement_pattern="vertical_push", is_assisted=False,
    )
    lr = Exercise(
        name="Lateral Raise", name_zh="側平舉", type="strength",
        equipment="dumbbell", movement_pattern="vertical_push", is_assisted=False,
    )
    rdf = Exercise(
        name="Rear Delt Fly", name_zh="後三角飛鳥", type="strength",
        equipment="dumbbell", movement_pattern="horizontal_pull", is_assisted=False,
    )
    db.add_all([ohp, lr, rdf])
    await db.flush()
    db.add_all([
        ExerciseMuscle(exercise_id=ohp.id, muscle_group_id=ant.id, is_primary=True),
        ExerciseMuscle(exercise_id=lr.id, muscle_group_id=lat.id, is_primary=True),
        ExerciseMuscle(exercise_id=rdf.id, muscle_group_id=rear.id, is_primary=True),
    ])
    await db.flush()

    matches_zh = await search_exercises(db, muscle_group="肩")
    matched_ids_zh = {ex.id for ex in matches_zh}
    assert {ohp.id, lr.id, rdf.id} <= matched_ids_zh

    # English alias works the same; case-insensitive.
    matches_en = await search_exercises(db, muscle_group="Shoulder")
    assert {ex.id for ex in matches_en} == matched_ids_zh


async def test_search_exercises_muscle_group_is_fuzzy_substring(
    db: AsyncSession, seed_exercises: dict[str, Exercise]
):
    """User-friendly: '三頭' / '臀' / 'tricep' should land without the full name."""
    # seed_exercises adds Triceps + Glutes muscle groups via conftest, but the
    # squat fixture exercise only links Quadriceps. Add a triceps-linked one.
    triceps_result = await db.execute(
        select(MuscleGroup).where(MuscleGroup.name == "Triceps")
    )
    triceps = triceps_result.scalar_one()
    pushdown = Exercise(
        name="Cable Triceps Pushdown",
        name_zh="Cable三頭下壓",
        type="strength",
        equipment="cable",
        movement_pattern="arm_iso",
        is_assisted=False,
    )
    db.add(pushdown)
    await db.flush()
    db.add(
        ExerciseMuscle(exercise_id=pushdown.id, muscle_group_id=triceps.id, is_primary=True)
    )
    await db.flush()

    # Colloquial short form "三頭" — main case the user complained about.
    matches_short = await search_exercises(db, muscle_group="三頭")
    assert pushdown.id in {ex.id for ex in matches_short}

    # English partial "tricep" should also work.
    matches_en_partial = await search_exercises(db, muscle_group="tricep")
    assert pushdown.id in {ex.id for ex in matches_en_partial}


async def test_get_personal_records_includes_session_type(
    db: AsyncSession, user: User, seed_exercises: dict[str, Exercise]
):
    d = date(2026, 3, 12)
    s, _ = await get_or_create_session(db, user.id, d, "coach")
    await record_exercises(
        db,
        user.id,
        s.id,
        [
            {
                "exercise_name": "深蹲",
                "sets": [
                    {
                        "weight_value": 60,
                        "weight_type": "total",
                        "weight_unit": "kg",
                        "reps_min": 5,
                        "num_sets": 3,
                    }
                ],
            },
        ],
        training_date=d,
    )

    prs = await get_personal_records(db, user.id, exercise_name="深蹲")
    assert len(prs) == 1
    assert prs[0]["exercise"] == "槓鈴背蹲"
    assert prs[0]["best"] == "60kg"
    assert prs[0]["session_type"] == "coach"
    assert prs[0]["date"] == "2026-03-12"


async def test_get_personal_records_by_muscle_group(
    db: AsyncSession, user: User, seed_exercises: dict[str, Exercise]
):
    family = await _add_deadlift_family(db)

    d1 = date(2026, 3, 10)
    s1, _ = await get_or_create_session(db, user.id, d1, "self_training")
    await record_exercises(
        db,
        user.id,
        s1.id,
        [
            {
                "exercise_name": "硬舉",
                "sets": [
                    {
                        "weight_value": 70,
                        "weight_type": "total",
                        "weight_unit": "kg",
                        "reps_min": 5,
                        "num_sets": 3,
                    }
                ],
            },
        ],
        training_date=d1,
    )
    d2 = date(2026, 3, 14)
    s2, _ = await get_or_create_session(db, user.id, d2, "self_training")
    await record_exercises(
        db,
        user.id,
        s2.id,
        [
            {
                "exercise_name": "RDL",
                "sets": [
                    {
                        "weight_value": 40,
                        "weight_type": "total",
                        "weight_unit": "kg",
                        "reps_min": 8,
                        "num_sets": 3,
                    }
                ],
            },
        ],
        training_date=d2,
    )
    # Sanity check fixtures registered the family.
    assert family["bb_dl"].id and family["rdl"].id

    # 硬舉 keyword catches BB deadlift only (per substring rule above).
    prs_kw = await get_personal_records(db, user.id, exercise_name="硬舉")
    exercises_kw = {pr["exercise"] for pr in prs_kw}
    assert "槓鈴硬舉" in exercises_kw
    assert "槓鈴RDL" not in exercises_kw

    # Muscle-group filter pulls the whole hinge family.
    prs_mg = await get_personal_records(db, user.id, muscle_group="膕繩肌")
    exercises_mg = {pr["exercise"] for pr in prs_mg}
    assert "槓鈴硬舉" in exercises_mg
    assert "槓鈴RDL" in exercises_mg


async def test_get_exercise_progression_multi_match_shape(
    db: AsyncSession, user: User, seed_exercises: dict[str, Exercise], today: date
):
    family = await _add_deadlift_family(db)
    # Log one session on each of the deadlift family within recent window.
    for offset, (name, weight) in enumerate(
        [("硬舉", 70), ("史密斯相撲硬舉", 60), ("RDL", 40)]
    ):
        d = today - timedelta(days=offset)
        s, _ = await get_or_create_session(db, user.id, d, "self_training")
        await record_exercises(
            db,
            user.id,
            s.id,
            [
                {
                    "exercise_name": name,
                    "sets": [
                        {
                            "weight_value": weight,
                            "weight_type": "total",
                            "weight_unit": "kg",
                            "reps_min": 5,
                            "num_sets": 3,
                        }
                    ],
                },
            ],
        )

    # Muscle-group route — guarantees multi-match across family.
    prog = await get_exercise_progression(
        db, user.id, muscle_group="膕繩肌", days=30
    )
    matched_names = set(prog["matched_exercises"])
    assert {"槓鈴硬舉", "相撲硬舉", "槓鈴RDL"} <= matched_names
    assert len(prog["exercises"]) >= 3
    for block in prog["exercises"]:
        for sess in block["sessions"]:
            assert sess["session_type"] == "self_training"
    # Multi-match: legacy single-shape keys must NOT be present.
    assert "progression" not in prog
    assert family["bb_dl"].id  # sanity


async def test_get_exercise_catalog_has_pr_flag(
    db: AsyncSession, user: User, seed_exercises: dict[str, Exercise]
):
    family = await _add_deadlift_family(db)

    # Log only 槓鈴硬舉 — others should show has_pr=false.
    d = date(2026, 3, 12)
    s, _ = await get_or_create_session(db, user.id, d, "self_training")
    await record_exercises(
        db,
        user.id,
        s.id,
        [
            {
                "exercise_name": "硬舉",
                "sets": [
                    {
                        "weight_value": 60,
                        "weight_type": "total",
                        "weight_unit": "kg",
                        "reps_min": 5,
                        "num_sets": 3,
                    }
                ],
            },
        ],
        training_date=d,
    )

    catalog = await get_exercise_catalog(db, user.id, muscle_group="膕繩肌")
    by_name = {row["exercise"]: row for row in catalog["matched"]}
    assert by_name["槓鈴硬舉"]["has_pr"] is True
    assert by_name["槓鈴硬舉"]["best"] == "60kg"
    assert by_name["槓鈴硬舉"]["last_logged_date"] == "2026-03-12"
    assert by_name["相撲硬舉"]["has_pr"] is False
    assert by_name["槓鈴RDL"]["has_pr"] is False
    assert family["bb_dl"].id  # sanity
