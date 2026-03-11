"""Seed exercises, muscle groups, aliases, and their relationships."""

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.database import async_session, engine
from src.db.models import Base, Exercise, ExerciseAlias, ExerciseMuscle, MuscleGroup

logger = logging.getLogger(__name__)

MUSCLE_GROUPS = [
    # Lower body
    {"name": "Quadriceps", "name_zh": "股四頭肌", "category": "lower_body"},
    {"name": "Glutes", "name_zh": "臀大肌", "category": "lower_body"},
    {"name": "Gluteus Medius", "name_zh": "臀中肌", "category": "lower_body"},
    {"name": "Hamstrings", "name_zh": "膕繩肌", "category": "lower_body"},
    {"name": "Adductors", "name_zh": "內收肌群", "category": "lower_body"},
    {"name": "Hip Flexors", "name_zh": "髖屈肌", "category": "lower_body"},
    {"name": "Calves", "name_zh": "小腿肌", "category": "lower_body"},
    # Upper push
    {"name": "Chest", "name_zh": "胸肌", "category": "upper_push"},
    {"name": "Anterior Deltoids", "name_zh": "前三角肌", "category": "upper_push"},
    {"name": "Lateral Deltoids", "name_zh": "中三角肌", "category": "upper_push"},
    {"name": "Triceps", "name_zh": "三頭肌", "category": "upper_push"},
    # Upper pull
    {"name": "Lats", "name_zh": "闊背肌", "category": "upper_pull"},
    {"name": "Rhomboids", "name_zh": "菱形肌", "category": "upper_pull"},
    {"name": "Rear Deltoids", "name_zh": "後三角肌", "category": "upper_pull"},
    {"name": "Biceps", "name_zh": "二頭肌", "category": "upper_pull"},
    {"name": "Trapezius", "name_zh": "斜方肌", "category": "upper_pull"},
    # Core
    {"name": "Rectus Abdominis", "name_zh": "腹直肌", "category": "core"},
    {"name": "Obliques", "name_zh": "腹斜肌", "category": "core"},
    {"name": "Transverse Abdominis", "name_zh": "腹橫肌", "category": "core"},
    {"name": "Erector Spinae", "name_zh": "豎脊肌", "category": "core"},
]

# Tuple format:
# (name, name_zh, type, equipment, movement_pattern, is_assisted,
#  aliases, primary_muscles, secondary_muscles)
EXERCISES = [
    # =====================================================================
    # SQUAT pattern - bilateral knee-dominant
    # =====================================================================
    (
        "Barbell Back Squat",
        "槓鈴背蹲",
        "strength",
        "barbell",
        "squat",
        False,
        ["槓鈴深蹲", "深蹲", "短槓深蹲"],
        ["Quadriceps", "Glutes"],
        ["Hamstrings", "Erector Spinae", "Transverse Abdominis"],
    ),
    (
        "Goblet Squat",
        "高腳杯深蹲",
        "strength",
        "dumbbell",
        "squat",
        False,
        ["高腳杯深蹲", "高腳杯彈力繩深蹲"],
        ["Quadriceps", "Glutes"],
        ["Transverse Abdominis"],
    ),
    (
        "Front Squat",
        "前蹲舉",
        "strength",
        "barbell",
        "squat",
        False,
        ["前蹲舉", "前抱式深蹲", "史密斯前蹲舉", "史密斯前抱式深蹲"],
        ["Quadriceps", "Glutes"],
        ["Erector Spinae", "Transverse Abdominis"],
    ),
    (
        "Reverse Hack Squat",
        "反向哈克深蹲",
        "strength",
        "machine",
        "squat",
        False,
        ["反向哈克深蹲", "哈克反向深蹲"],
        ["Quadriceps", "Glutes"],
        ["Hamstrings"],
    ),
    (
        "Box Squat",
        "箱上蹲",
        "strength",
        "bodyweight",
        "squat",
        False,
        ["水管箱上蹲", "箱上蹲", "水管深蹲練習"],
        ["Quadriceps", "Glutes"],
        [],
    ),
    (
        "Dumbbell Shoulder Squat",
        "啞鈴肩負重深蹲",
        "strength",
        "dumbbell",
        "squat",
        False,
        ["啞鈴肩負重深蹲"],
        ["Quadriceps", "Glutes"],
        ["Transverse Abdominis"],
    ),
    (
        "Leg Press",
        "臥姿腿推",
        "strength",
        "machine",
        "squat",
        False,
        ["臥姿腿推"],
        ["Quadriceps", "Glutes"],
        ["Hamstrings"],
    ),
    # =====================================================================
    # LUNGE pattern - unilateral knee-dominant
    # =====================================================================
    (
        "Bulgarian Split Squat",
        "後腳抬高蹲",
        "strength",
        "dumbbell",
        "lunge",
        False,
        ["後腳抬高蹲"],
        ["Quadriceps", "Glutes"],
        ["Hamstrings", "Gluteus Medius"],
    ),
    (
        "Split Squat",
        "分腿蹲",
        "strength",
        "dumbbell",
        "lunge",
        False,
        ["分腿蹲", "壺鈴肩負重分腿蹲+抬腿"],
        ["Quadriceps", "Glutes"],
        ["Hamstrings"],
    ),
    (
        "Forward Lunge",
        "前弓箭步",
        "strength",
        "dumbbell",
        "lunge",
        False,
        ["前弓箭步", "弓箭步"],
        ["Quadriceps", "Glutes"],
        ["Hamstrings"],
    ),
    (
        "Reverse Lunge",
        "後弓箭步",
        "strength",
        "dumbbell",
        "lunge",
        False,
        ["後弓箭步"],
        ["Glutes", "Quadriceps"],
        ["Hamstrings"],
    ),
    (
        "Walking Lunge",
        "行走弓箭步",
        "strength",
        "dumbbell",
        "lunge",
        False,
        ["行走弓箭步", "弓箭步走路"],
        ["Quadriceps", "Glutes"],
        ["Hamstrings"],
    ),
    (
        "Smith Machine Reverse Lunge",
        "史密斯後弓步",
        "strength",
        "machine",
        "lunge",
        False,
        ["史密斯後弓步+抬腿", "史密斯後弓步"],
        ["Glutes", "Quadriceps"],
        ["Hamstrings"],
    ),
    (
        "Smith Machine Split Squat",
        "史密斯分腿蹲",
        "strength",
        "machine",
        "lunge",
        False,
        ["史密斯分腿蹲"],
        ["Quadriceps", "Glutes"],
        ["Hamstrings"],
    ),
    (
        "Step Up",
        "登階",
        "strength",
        "dumbbell",
        "lunge",
        False,
        ["登階", "登階+抬腿舉球", "登階 左右側移"],
        ["Quadriceps", "Glutes"],
        ["Gluteus Medius"],
    ),
    (
        "Lunge with Leg Raise",
        "弓箭步+抬腿",
        "strength",
        "bodyweight",
        "lunge",
        False,
        ["弓箭步+抬腿"],
        ["Quadriceps", "Glutes"],
        ["Gluteus Medius", "Hip Flexors"],
    ),
    # =====================================================================
    # HINGE pattern - hip-dominant
    # =====================================================================
    (
        "Barbell Romanian Deadlift",
        "槓鈴RDL",
        "strength",
        "barbell",
        "hinge",
        False,
        ["槓鈴rdl", "槓鈴RDL", "槓鈴(rdl)", "rdl", "RDL"],
        ["Hamstrings", "Glutes"],
        ["Erector Spinae"],
    ),
    (
        "Dumbbell Romanian Deadlift",
        "啞鈴RDL",
        "strength",
        "dumbbell",
        "hinge",
        False,
        ["啞鈴rdl", "啞鈴RDL"],
        ["Hamstrings", "Glutes"],
        ["Erector Spinae"],
    ),
    (
        "Single Leg Romanian Deadlift",
        "單腿RDL",
        "strength",
        "dumbbell",
        "hinge",
        False,
        ["單腿rdl", "單腿RDL"],
        ["Hamstrings", "Glutes"],
        ["Erector Spinae", "Gluteus Medius"],
    ),
    (
        "Barbell Deadlift",
        "槓鈴硬舉",
        "strength",
        "barbell",
        "hinge",
        False,
        ["槓鈴硬舉", "硬舉"],
        ["Glutes", "Hamstrings", "Erector Spinae"],
        ["Quadriceps", "Lats", "Trapezius"],
    ),
    (
        "Sumo Deadlift",
        "相撲硬舉",
        "strength",
        "barbell",
        "hinge",
        False,
        ["相撲硬舉", "史密斯相撲硬舉", "壺鈴相撲硬舉"],
        ["Glutes", "Hamstrings", "Adductors"],
        ["Erector Spinae", "Quadriceps"],
    ),
    (
        "Kettlebell Swing",
        "壺鈴擺盪",
        "strength",
        "kettlebell",
        "hinge",
        False,
        ["壺鈴擺盪"],
        ["Glutes", "Hamstrings"],
        ["Erector Spinae", "Transverse Abdominis"],
    ),
    (
        "Roman Chair Hip Extension",
        "羅馬椅髖屈伸",
        "strength",
        "bodyweight",
        "hinge",
        False,
        ["羅馬椅髖屈伸"],
        ["Glutes", "Erector Spinae"],
        ["Hamstrings"],
    ),
    # =====================================================================
    # GLUTE_ISO pattern - glute isolation
    # =====================================================================
    (
        "Hip Thrust",
        "臀推",
        "strength",
        "barbell",
        "glute_iso",
        False,
        ["臀推", "啞鈴臀推", "短槓臀推"],
        ["Glutes"],
        ["Hamstrings"],
    ),
    (
        "Single Leg Hip Thrust",
        "單腿臀推",
        "strength",
        "bodyweight",
        "glute_iso",
        False,
        ["單腿臀推"],
        ["Glutes"],
        ["Hamstrings", "Gluteus Medius"],
    ),
    (
        "Single Leg Glute Bridge",
        "單腿臀橋",
        "strength",
        "bodyweight",
        "glute_iso",
        False,
        ["單腿臀橋"],
        ["Glutes"],
        ["Hamstrings"],
    ),
    (
        "Cable Kickback",
        "腿後踢",
        "strength",
        "cable",
        "glute_iso",
        False,
        ["腿後踢"],
        ["Glutes"],
        ["Hamstrings"],
    ),
    (
        "Hip Abduction",
        "髖外展",
        "strength",
        "machine",
        "glute_iso",
        False,
        ["髖外展"],
        ["Gluteus Medius"],
        ["Glutes"],
    ),
    # =====================================================================
    # HORIZONTAL_PUSH pattern - chest dominant
    # =====================================================================
    (
        "Smith Machine Incline Bench Press",
        "史密斯上斜臥推",
        "strength",
        "machine",
        "horizontal_push",
        False,
        ["史密斯上斜臥推"],
        ["Chest", "Anterior Deltoids"],
        ["Triceps"],
    ),
    (
        "Smith Machine Bench Press",
        "史密斯臥推",
        "strength",
        "machine",
        "horizontal_push",
        False,
        ["史密斯臥推"],
        ["Chest"],
        ["Anterior Deltoids", "Triceps"],
    ),
    (
        "Dumbbell Bench Press",
        "啞鈴臥推",
        "strength",
        "dumbbell",
        "horizontal_push",
        False,
        ["啞鈴臥推"],
        ["Chest"],
        ["Anterior Deltoids", "Triceps"],
    ),
    (
        "Incline Push Up",
        "上斜伏地挺身",
        "strength",
        "bodyweight",
        "horizontal_push",
        False,
        ["上斜伏地挺身"],
        ["Chest"],
        ["Anterior Deltoids", "Triceps"],
    ),
    (
        "Seated Chest Press",
        "坐姿胸推",
        "strength",
        "machine",
        "horizontal_push",
        False,
        ["坐姿胸推", "上斜胸推"],
        ["Chest"],
        ["Anterior Deltoids", "Triceps"],
    ),
    (
        "Dumbbell Fly",
        "啞鈴飛鳥",
        "strength",
        "dumbbell",
        "horizontal_push",
        False,
        ["啞鈴飛鳥"],
        ["Chest"],
        ["Anterior Deltoids"],
    ),
    (
        "Band Push",
        "彈力繩上推",
        "strength",
        "band",
        "horizontal_push",
        False,
        ["彈力繩上推"],
        ["Chest"],
        ["Anterior Deltoids", "Triceps"],
    ),
    (
        "Dip (Assisted)",
        "Dip",
        "strength",
        "machine",
        "horizontal_push",
        True,
        ["Dip", "dip"],
        ["Chest", "Triceps"],
        ["Anterior Deltoids"],
    ),
    # =====================================================================
    # VERTICAL_PUSH pattern - shoulder dominant
    # =====================================================================
    (
        "Dumbbell Shoulder Press",
        "啞鈴肩推",
        "strength",
        "dumbbell",
        "vertical_push",
        False,
        ["啞鈴肩推", "啞鈴坐姿肩推", "站姿肩推", "坐姿肩推"],
        ["Anterior Deltoids", "Lateral Deltoids"],
        ["Triceps"],
    ),
    (
        "Short Bar Shoulder Press",
        "短槓肩推",
        "strength",
        "barbell",
        "vertical_push",
        False,
        ["短槓肩推"],
        ["Anterior Deltoids", "Lateral Deltoids"],
        ["Triceps"],
    ),
    (
        "Dumbbell Lateral Raise",
        "啞鈴側平舉",
        "strength",
        "dumbbell",
        "vertical_push",
        False,
        ["啞鈴側平舉", "啞鈴前+側平舉"],
        ["Lateral Deltoids"],
        ["Anterior Deltoids"],
    ),
    (
        "W Raise",
        "W平舉",
        "strength",
        "dumbbell",
        "vertical_push",
        False,
        ["W平舉"],
        ["Rear Deltoids", "Lateral Deltoids"],
        ["Trapezius"],
    ),
    (
        "Dumbbell Rocket Push",
        "啞鈴火箭推",
        "strength",
        "dumbbell",
        "power",
        False,
        ["啞鈴火箭推", "啞鈴藥球火箭推"],
        ["Anterior Deltoids", "Lateral Deltoids"],
        ["Triceps", "Quadriceps", "Glutes"],
    ),
    # =====================================================================
    # ARM_ISO pattern - triceps
    # =====================================================================
    (
        "Cable Tricep Pushdown",
        "Cable三頭下壓",
        "strength",
        "cable",
        "arm_iso",
        False,
        ["三頭下壓", "Cable三頭下壓", "三頭下拉", "Cable三頭下拉"],
        ["Triceps"],
        [],
    ),
    (
        "Cable Overhead Tricep Extension",
        "Cable三頭過頭屈伸",
        "strength",
        "cable",
        "arm_iso",
        False,
        ["Cable三頭過頭屈伸", "Cable 三頭過頭屈伸", "三頭過頭伸展", "三頭過頭彎舉"],
        ["Triceps"],
        [],
    ),
    (
        "Dumbbell French Press",
        "啞鈴法式推舉",
        "strength",
        "dumbbell",
        "arm_iso",
        False,
        ["啞鈴法式推舉", "啞鈴法式彎舉"],
        ["Triceps"],
        [],
    ),
    # =====================================================================
    # VERTICAL_PULL pattern - lat dominant
    # =====================================================================
    (
        "Assisted Pull Up",
        "引體向上",
        "strength",
        "machine",
        "vertical_pull",
        True,
        ["引體向上", "腳支撐引體", "腳支撐輔助引體"],
        ["Lats"],
        ["Biceps", "Rhomboids", "Rear Deltoids"],
    ),
    (
        "Lat Pulldown",
        "滑輪下拉",
        "strength",
        "cable",
        "vertical_pull",
        False,
        ["滑輪下拉", "雙滑軌滑輪下拉", "雙側下拉", "滑輪雙側下拉", "雙滑軌滑輪下拉"],
        ["Lats"],
        ["Biceps", "Rhomboids"],
    ),
    (
        "Reverse Grip Lat Pulldown",
        "反手下拉",
        "strength",
        "cable",
        "vertical_pull",
        False,
        ["反手下拉"],
        ["Lats", "Biceps"],
        ["Rhomboids"],
    ),
    (
        "Cable Straight Arm Pushdown",
        "直臂下壓",
        "strength",
        "cable",
        "vertical_pull",
        False,
        ["直臂下壓"],
        ["Lats"],
        ["Rear Deltoids", "Transverse Abdominis"],
    ),
    # =====================================================================
    # HORIZONTAL_PULL pattern - row dominant
    # =====================================================================
    (
        "Seated Cable Row",
        "坐姿划船",
        "strength",
        "cable",
        "horizontal_pull",
        False,
        ["坐姿划船", "Cable坐姿划船", "雙軌坐姿划船"],
        ["Rhomboids", "Lats"],
        ["Biceps", "Rear Deltoids", "Trapezius"],
    ),
    (
        "Cable Single Arm Row",
        "Cable單側划船",
        "strength",
        "cable",
        "horizontal_pull",
        False,
        ["Cable單側划船", "Cable 雙邊划船"],
        ["Rhomboids", "Lats"],
        ["Biceps"],
    ),
    (
        "Dumbbell Row",
        "啞鈴划船",
        "strength",
        "dumbbell",
        "horizontal_pull",
        False,
        ["啞鈴划船", "啞鈴單側划船", "啞鈴上斜划船", "單側划船"],
        ["Rhomboids", "Lats"],
        ["Biceps", "Rear Deltoids"],
    ),
    (
        "Barbell Row",
        "槓鈴划船",
        "strength",
        "barbell",
        "horizontal_pull",
        False,
        ["槓鈴划船", "窄握反手 划船"],
        ["Rhomboids", "Lats"],
        ["Biceps", "Erector Spinae"],
    ),
    (
        "Cable Rear Delt Fly",
        "Cable後飛鳥",
        "strength",
        "cable",
        "horizontal_pull",
        False,
        ["Cable後飛鳥", "後飛鳥"],
        ["Rear Deltoids"],
        ["Rhomboids", "Trapezius"],
    ),
    (
        "TRX Y Fly",
        "TRX Y飛鳥",
        "strength",
        "trx",
        "horizontal_pull",
        False,
        ["Trx Y飛鳥", "啞鈴Y飛鳥"],
        ["Rear Deltoids"],
        ["Trapezius", "Rhomboids"],
    ),
    # =====================================================================
    # ARM_ISO pattern - biceps
    # =====================================================================
    (
        "Cable Bicep Curl",
        "Cable二頭彎舉",
        "strength",
        "cable",
        "arm_iso",
        False,
        ["Cable二頭彎舉"],
        ["Biceps"],
        [],
    ),
    (
        "EZ Bar Bicep Curl",
        "曲槓二頭彎舉",
        "strength",
        "barbell",
        "arm_iso",
        False,
        ["曲槓二頭彎舉", "W槓二頭彎舉"],
        ["Biceps"],
        [],
    ),
    (
        "Dumbbell Incline Bicep Curl",
        "啞鈴上斜二頭彎舉",
        "strength",
        "dumbbell",
        "arm_iso",
        False,
        ["啞鈴上斜二頭彎舉"],
        ["Biceps"],
        [],
    ),
    # =====================================================================
    # CORE_STABILITY pattern - anti-extension, anti-rotation
    # =====================================================================
    (
        "Plank",
        "棒式",
        "strength",
        "bodyweight",
        "core_stability",
        False,
        [
            "棒式",
            "肘撐棒式",
            "肘撐棒式+高位棒式",
            "Bosu 棒式",
            "棒式上下槓片",
            "棒式+交錯摸肩膀",
            "藥球支撐單邊棒式",
            "Trx棒式支撐",
            "高位棒式",
            "棒式抬手",
        ],
        ["Transverse Abdominis"],
        ["Rectus Abdominis", "Obliques", "Erector Spinae"],
    ),
    (
        "Dead Bug",
        "死蟲",
        "warmup",
        "bodyweight",
        "core_stability",
        False,
        ["死蟲", "死蟲 腳跟落地"],
        ["Transverse Abdominis"],
        ["Erector Spinae"],
    ),
    (
        "Bird Dog",
        "鳥狗式",
        "warmup",
        "bodyweight",
        "core_stability",
        False,
        ["鳥狗式", "飛機式", "滾筒飛機式", "飛機"],
        ["Transverse Abdominis", "Erector Spinae"],
        ["Gluteus Medius"],
    ),
    (
        "Side Plank",
        "側棒式",
        "strength",
        "bodyweight",
        "core_stability",
        False,
        ["側棒式", "左核心 側棒式開髖"],
        ["Obliques", "Transverse Abdominis"],
        ["Gluteus Medius"],
    ),
    # =====================================================================
    # CORE_FLEXION pattern - crunch, leg raise
    # =====================================================================
    (
        "Hanging Leg Raise",
        "懸吊抬腿",
        "strength",
        "bodyweight",
        "core_flexion",
        False,
        ["懸吊抬腿"],
        ["Rectus Abdominis"],
        ["Hip Flexors", "Obliques"],
    ),
    (
        "Crunch",
        "捲腹",
        "strength",
        "bodyweight",
        "core_flexion",
        False,
        ["捲腹", "臥姿抬腿捲腹", "Trx捲腹", "臥姿bench捲腹"],
        ["Rectus Abdominis"],
        ["Obliques"],
    ),
    # =====================================================================
    # CORE_ROTATION pattern - chop, slam, anti-rotation
    # =====================================================================
    (
        "Medicine Ball Slam",
        "藥球下砸",
        "strength",
        "medicine_ball",
        "core_rotation",
        False,
        ["藥球下砸", "藥球左右下砸"],
        ["Obliques", "Rectus Abdominis"],
        ["Lats"],
    ),
    (
        "Medicine Ball Woodchop",
        "藥球劈砍",
        "strength",
        "medicine_ball",
        "core_rotation",
        False,
        ["藥球劈砍", "藥球劈柴"],
        ["Obliques"],
        ["Transverse Abdominis", "Rectus Abdominis"],
    ),
    # =====================================================================
    # POWER pattern - explosive full-body
    # =====================================================================
    (
        "Battle Ropes",
        "戰繩",
        "strength",
        "battle_ropes",
        "power",
        False,
        ["戰繩"],
        ["Anterior Deltoids", "Transverse Abdominis"],
        ["Lats", "Glutes"],
    ),
    (
        "Toe Taps",
        "Toe Taps",
        "strength",
        "bodyweight",
        "power",
        False,
        ["Toe taps", "Toe Taps"],
        ["Hip Flexors", "Quadriceps"],
        [],
    ),
    # =====================================================================
    # MOBILITY pattern - corrective, activation, warm-up
    # =====================================================================
    (
        "Hip Mobility Drill",
        "髖關節活動度練習",
        "mobility",
        "bodyweight",
        "mobility",
        False,
        ["髖關節活動度練習", "髖關節鬆動"],
        ["Hip Flexors", "Glutes"],
        [],
    ),
    (
        "Clamshell",
        "蚌殼式",
        "warmup",
        "bodyweight",
        "mobility",
        False,
        ["蚌殼式", "右邊蚌殼式"],
        ["Gluteus Medius"],
        [],
    ),
    (
        "Copenhagen Side Plank",
        "哥本哈根側棒式",
        "warmup",
        "bodyweight",
        "core_stability",
        False,
        ["哥本哈根側棒式", "右哥本哈根側棒式"],
        ["Adductors"],
        ["Obliques"],
    ),
    (
        "Glute Med Activation",
        "臀中肌啟動",
        "warmup",
        "bodyweight",
        "mobility",
        False,
        ["臀中肌啟動", "臀中肌抬腿練習"],
        ["Gluteus Medius"],
        [],
    ),
    (
        "Half Kneeling Adductor",
        "半跪姿內收肌練習",
        "mobility",
        "bodyweight",
        "mobility",
        False,
        ["半跪姿內收肌練習"],
        ["Adductors"],
        [],
    ),
    (
        "Band Squat",
        "彈力繩深蹲",
        "warmup",
        "band",
        "squat",
        False,
        ["彈力繩深蹲"],
        ["Quadriceps", "Glutes"],
        [],
    ),
    (
        "Single Leg Stand Hip Flexion",
        "單腿站姿髖屈練習",
        "warmup",
        "band",
        "mobility",
        False,
        ["單腿站姿彈力繩髖屈練習"],
        ["Hip Flexors"],
        ["Gluteus Medius"],
    ),
    (
        "Single Leg Stand",
        "單腿站立練習",
        "warmup",
        "bodyweight",
        "mobility",
        False,
        ["單腿站立練習"],
        ["Gluteus Medius"],
        ["Transverse Abdominis"],
    ),
]


async def seed_muscle_groups(session: AsyncSession) -> dict[str, int]:
    existing = (await session.execute(select(MuscleGroup))).scalars().all()
    if existing:
        return {mg.name: mg.id for mg in existing}

    name_to_id = {}
    for mg_data in MUSCLE_GROUPS:
        mg = MuscleGroup(**mg_data)
        session.add(mg)
        await session.flush()
        name_to_id[mg.name] = mg.id

    return name_to_id


async def seed_exercises(session: AsyncSession, muscle_map: dict[str, int]) -> None:
    existing = (await session.execute(select(Exercise))).scalars().first()
    if existing:
        logger.info("Exercises already seeded, skipping")
        return

    for (
        name,
        name_zh,
        ex_type,
        equipment,
        movement_pattern,
        is_assisted,
        aliases,
        primary,
        secondary,
    ) in EXERCISES:
        exercise = Exercise(
            name=name,
            name_zh=name_zh,
            type=ex_type,
            equipment=equipment,
            movement_pattern=movement_pattern,
            is_assisted=is_assisted,
        )
        session.add(exercise)
        await session.flush()

        for alias_text in aliases:
            session.add(ExerciseAlias(exercise_id=exercise.id, alias=alias_text))

        for muscle_name in primary:
            if muscle_name in muscle_map:
                session.add(
                    ExerciseMuscle(
                        exercise_id=exercise.id,
                        muscle_group_id=muscle_map[muscle_name],
                        is_primary=True,
                    )
                )

        for muscle_name in secondary:
            if muscle_name in muscle_map:
                session.add(
                    ExerciseMuscle(
                        exercise_id=exercise.id,
                        muscle_group_id=muscle_map[muscle_name],
                        is_primary=False,
                    )
                )


async def run_seed():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        async with session.begin():
            muscle_map = await seed_muscle_groups(session)
            await seed_exercises(session, muscle_map)
        logger.info("Seed completed successfully")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_seed())
