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
                "Update user's fitness profile (goals, habits, etc). "
                "Call when user mentions a new goal or routine change."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "fitness_goals": {"type": "string"},
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
                "Record body composition data. "
                "Call when user reports body fat, weight, or muscle mass."
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
                        "description": "Muscle mass in kg",
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
                "Call when user asks about body fat or weight trends."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Days to look back (default 90)",
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
]
