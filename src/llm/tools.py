"""LLM function calling tool definitions (OpenAI-compatible format)."""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "log_strength_training",
            "description": (
                "Record a strength training session. Call when user reports workout exercises."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "Training date YYYY-MM-DD. Omit for today.",
                    },
                    "session_type": {
                        "type": "string",
                        "enum": ["self_training", "coach", "other"],
                        "description": (
                            "self_training=solo, coach=with trainer, other=sport/class"
                        ),
                    },
                    "exercises": {
                        "type": "array",
                        "description": "List of exercises performed",
                        "items": {
                            "type": "object",
                            "properties": {
                                "exercise_name": {
                                    "type": "string",
                                    "description": ("Exercise name in Chinese or English"),
                                },
                                "category": {
                                    "type": "string",
                                    "enum": [
                                        "working",
                                        "warmup",
                                        "activation",
                                        "circuit",
                                    ],
                                    "description": "Default: working",
                                },
                                "raw_text": {
                                    "type": "string",
                                    "description": "Original user text",
                                },
                                "notes": {
                                    "type": "string",
                                    "description": "Technique cues or notes",
                                },
                                "sets": {
                                    "type": "array",
                                    "description": ("Set groups (one per weight/rep combo)"),
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "weight_value": {
                                                "type": "number",
                                                "description": (
                                                    "Weight number. Omit for bodyweight."
                                                ),
                                            },
                                            "weight_type": {
                                                "type": "string",
                                                "enum": [
                                                    "total",
                                                    "per_side",
                                                    "counterweight",
                                                    "bodyweight",
                                                    "band",
                                                ],
                                                "description": (
                                                    "How to interpret weight. 'each' = per_side."
                                                ),
                                            },
                                            "weight_unit": {
                                                "type": "string",
                                                "enum": ["kg", "lb"],
                                                "description": "Default: kg",
                                            },
                                            "band_info": {
                                                "type": "string",
                                                "description": (
                                                    "Band color/resistance e.g. 'black+green'"
                                                ),
                                            },
                                            "reps_min": {
                                                "type": "integer",
                                                "description": ("Rep count (or min if range)"),
                                            },
                                            "reps_max": {
                                                "type": "integer",
                                                "description": (
                                                    "Max reps if range. Same as min if exact."
                                                ),
                                            },
                                            "num_sets": {
                                                "type": "integer",
                                                "description": "Number of sets",
                                            },
                                            "duration_sec": {
                                                "type": "integer",
                                                "description": (
                                                    "Duration in seconds for timed exercises"
                                                ),
                                            },
                                            "is_each_side": {
                                                "type": "boolean",
                                                "description": (
                                                    "True if each side / per leg / per arm"
                                                ),
                                            },
                                        },
                                    },
                                },
                            },
                            "required": ["exercise_name", "sets"],
                        },
                    },
                    "session_notes": {
                        "type": "string",
                        "description": "Overall session notes",
                    },
                },
                "required": ["session_type", "exercises"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "log_user_condition",
            "description": (
                "Record a body condition, injury, weakness, or technique cue. "
                "Call when user reports pain, alignment issues, or exercise-specific notes. "
                "Use exercise_name to link the note to a specific exercise."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": ["posture", "injury", "weakness", "cue"],
                    },
                    "description": {
                        "type": "string",
                        "description": "Description of the condition or technique note",
                    },
                    "action_item": {
                        "type": "string",
                        "description": "Suggested action to address it",
                    },
                    "exercise_name": {
                        "type": "string",
                        "description": (
                            "Link to a specific exercise (e.g. 'dip', 'squat'). "
                            "Omit for general body conditions."
                        ),
                    },
                },
                "required": ["category", "description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "resolve_user_condition",
            "description": ("Mark a body condition as resolved when the user says it improved."),
            "parameters": {
                "type": "object",
                "properties": {
                    "condition_id": {
                        "type": "integer",
                        "description": "ID of the condition to resolve",
                    },
                },
                "required": ["condition_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_user_profile",
            "description": (
                "Update soft fitness-profile context (training cadence, cardio "
                "status, body-fat / heart-rate targets). For concrete, deadlined "
                "goals call manage_goal instead."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "training_habit": {"type": "string"},
                    "cardio_status": {"type": "string"},
                    "target_body_fat_pct": {"type": "number"},
                    "target_max_hr": {"type": "integer"},
                    "notes": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_personal_records",
            "description": (
                "Query user's personal records. Call when user asks about PRs or max weights."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "exercise_name": {
                        "type": "string",
                        "description": "Filter by exercise (omit for all)",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_training_history",
            "description": (
                "Query recent training sessions (summary: exercise names only). "
                "For full detail with sets/weights/reps, use query_training_detail instead."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Days to look back (default 7)",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_training_detail",
            "description": (
                "Query full training detail with exercises, sets, weights, and reps. "
                "Use when user asks about specific workout content, volume, or intensity."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Days to look back (default 7)",
                    },
                    "date": {
                        "type": "string",
                        "description": "Specific date YYYY-MM-DD (overrides days)",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_exercise_progression",
            "description": (
                "Query weight/rep progression for a specific exercise over time. "
                "Use when user asks about progress on a particular lift."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "exercise_name": {
                        "type": "string",
                        "description": "Exercise name (Chinese or English)",
                    },
                    "days": {
                        "type": "integer",
                        "description": "Days to look back (default 90)",
                    },
                },
                "required": ["exercise_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_conditions",
            "description": (
                "Query active body conditions. Call when user asks about issues to watch."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_exercise_notes",
            "description": (
                "Query user's personal notes/cues for a specific exercise. "
                "Call when discussing or recording a specific exercise to reference their notes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "exercise_name": {
                        "type": "string",
                        "description": "Exercise name (Chinese or English)",
                    },
                },
                "required": ["exercise_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "log_cardio",
            "description": (
                "Record a cardio session (treadmill, spinning, rowing). "
                "Call when user reports cardio exercise."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "Date YYYY-MM-DD. Omit for today.",
                    },
                    "cardio_type": {
                        "type": "string",
                        "enum": ["treadmill", "spinning", "rowing"],
                    },
                    "duration_min": {
                        "type": "integer",
                        "description": "Duration in minutes",
                    },
                    "incline": {
                        "type": "number",
                        "description": "Treadmill incline",
                    },
                    "speed_kmh": {
                        "type": "number",
                        "description": "Speed in km/h",
                    },
                    "resistance": {
                        "type": "number",
                        "description": "Resistance level (spinning/rowing)",
                    },
                    "distance_km": {"type": "number"},
                    "max_heart_rate": {"type": "integer"},
                    "avg_heart_rate": {"type": "integer"},
                    "calories": {"type": "integer"},
                    "notes": {"type": "string"},
                },
                "required": ["cardio_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "log_body_composition",
            "description": (
                "Record body composition data (manual input or InBody report). "
                "Call when user reports body fat, weight, muscle mass, or InBody results."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "Date YYYY-MM-DD. Omit for today.",
                    },
                    "body_fat_pct": {
                        "type": "number",
                        "description": "Body fat percentage",
                    },
                    "weight_kg": {
                        "type": "number",
                        "description": "Body weight in kg",
                    },
                    "muscle_mass_kg": {
                        "type": "number",
                        "description": "Skeletal muscle mass in kg",
                    },
                    "visceral_fat_level": {
                        "type": "integer",
                        "description": "Visceral fat level (1-20)",
                    },
                    "bmr": {
                        "type": "integer",
                        "description": "Basal metabolic rate (kcal)",
                    },
                    "score": {
                        "type": "integer",
                        "description": "InBody total score",
                    },
                    "segments": {
                        "type": "array",
                        "description": "Body segment analysis (from InBody)",
                        "items": {
                            "type": "object",
                            "properties": {
                                "segment": {
                                    "type": "string",
                                    "enum": [
                                        "left_arm",
                                        "right_arm",
                                        "trunk",
                                        "left_leg",
                                        "right_leg",
                                    ],
                                },
                                "muscle_mass_kg": {
                                    "type": "number",
                                    "description": "Segment muscle mass in kg",
                                },
                                "muscle_grade": {
                                    "type": "string",
                                    "enum": ["below", "standard", "above"],
                                    "description": "Muscle development grade",
                                },
                                "fat_mass_kg": {
                                    "type": "number",
                                    "description": "Segment fat mass in kg",
                                },
                                "fat_grade": {
                                    "type": "string",
                                    "enum": ["below", "standard", "above"],
                                    "description": "Fat level grade",
                                },
                            },
                            "required": ["segment"],
                        },
                    },
                    "inbody_data": {
                        "type": "object",
                        "description": (
                            "Additional InBody data as JSON (BMI, body water, "
                            "ideal weight, ideal body fat, protein, etc.)"
                        ),
                    },
                    "notes": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_body_composition",
            "description": (
                "Query body composition history. "
                "Call when user asks about body fat or weight trends. "
                "Use latest_only=true when you just need the most recent data for reference."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Days to look back (default 90)",
                    },
                    "latest_only": {
                        "type": "boolean",
                        "description": "Return only summary with latest measurement (saves tokens)",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_cardio_progress",
            "description": ("Query cardio history. Call when user asks about cardio trends or HR."),
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Days to look back (default 30)",
                    },
                    "cardio_type": {
                        "type": "string",
                        "enum": ["treadmill", "spinning", "rowing"],
                        "description": "Filter by type (omit for all)",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_user_images",
            "description": (
                "Query user's saved images (InBody reports, progress photos, etc). "
                "Returns id, category, date, and description. "
                "Set include_urls=true to get secure URLs for sending images back to user."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": ["inbody", "progress", "meal", "other"],
                        "description": "Filter by category (omit for all)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results (default 10)",
                    },
                    "include_urls": {
                        "type": "boolean",
                        "description": (
                            "Include secure URLs for each image (for sending to user). "
                            "Default false to save tokens."
                        ),
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "manage_goal",
            "description": (
                "Create, update, or close a fitness goal. "
                "action=create: new goal (requires category + description). "
                "action=update/achieve/abandon: modify existing goal (requires goal_id)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["create", "update", "achieve", "abandon"],
                    },
                    "goal_id": {
                        "type": "integer",
                        "description": "Required for update/achieve/abandon",
                    },
                    "category": {
                        "type": "string",
                        "enum": ["body_comp", "strength", "habit", "general"],
                        "description": (
                            "Required for create. "
                            "body_comp=weight/fat/muscle, strength=lift targets, "
                            "habit=frequency/routine, general=other"
                        ),
                    },
                    "description": {
                        "type": "string",
                        "description": "Goal description in user's language",
                    },
                    "target_value": {
                        "type": "number",
                        "description": "Numeric target (e.g. 22.0 for body fat 22%)",
                    },
                    "target_unit": {
                        "type": "string",
                        "description": "Unit: %, kg, sessions_per_week, min, etc.",
                    },
                    "deadline": {
                        "type": "string",
                        "description": "Target date YYYY-MM-DD (omit if open-ended)",
                    },
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_daily_plan",
            "description": (
                "Record user's reply to today's daily push notification. "
                "Call when user responds to the morning greeting with their training plan."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_plan": {
                        "type": "string",
                        "enum": ["rest", "self_training", "coach", "other"],
                        "description": "User's plan for today",
                    },
                    "user_response": {
                        "type": "string",
                        "description": "User's original response text",
                    },
                },
                "required": ["user_plan", "user_response"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "log_meal",
            "description": (
                "Record a meal with optional nutrition estimates. Call when user "
                "describes what they ate (text or photo). Always pass image_id "
                "if a synthetic [User just sent a meal photo] payload included one."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "Eat date YYYY-MM-DD. Omit for today.",
                    },
                    "meal_type": {
                        "type": "string",
                        "enum": ["breakfast", "lunch", "dinner", "snack"],
                    },
                    "food_items": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of foods, e.g. ['義大利麵', '沙拉']",
                    },
                    "calories": {"type": "integer"},
                    "protein_g": {"type": "number"},
                    "carbs_g": {"type": "number"},
                    "fat_g": {"type": "number"},
                    "image_id": {
                        "type": "integer",
                        "description": "user_images row id when this meal came from a photo",
                    },
                    "notes": {"type": "string"},
                },
                "required": ["meal_type", "food_items"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_meal_history",
            "description": (
                "List recent meals with daily nutrition totals. Call when user asks "
                "about diet history, calorie/macro intake, or 'what did I eat'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Days to look back (default 7)",
                    },
                    "meal_type": {
                        "type": "string",
                        "enum": ["breakfast", "lunch", "dinner", "snack"],
                        "description": "Filter to one meal type",
                    },
                },
            },
        },
    },
]
