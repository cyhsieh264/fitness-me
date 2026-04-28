"""Vision model integration for classifying and parsing fitness images."""

import base64
import json
import logging

import litellm

from src.config import settings

logger = logging.getLogger(__name__)

IMAGE_CLASSIFY_PROMPT = """\
You are a fitness image analyzer. Classify this image and extract relevant data.

Step 1: Determine the category:
- "inbody":         An InBody or body composition analyzer report/printout
- "training_sheet": A workout written on paper/whiteboard/screen (sets, weights, reps)
- "meal":           Food or meal photo
- "progress":       Gym selfie, physique photo, before/after comparison
- "other":          Anything else

Step 2: Return a JSON object. ALWAYS include:
{
  "category": "<one of the above>",
  "description": "Concrete 1–2 sentence description in Traditional Chinese (zh-TW)"
}

Per-category extras:

# inbody
{
  "category": "inbody",
  "description": "...",
  "date": "YYYY-MM-DD if visible",
  "weight_kg": number,
  "body_fat_pct": number,
  "muscle_mass_kg": number (skeletal muscle mass),
  "visceral_fat_level": integer (1-20),
  "bmr": integer (kcal),
  "score": integer (InBody score),
  "segments": [
    {"segment": "left_arm", "muscle_mass_kg": number,
     "muscle_grade": "below|standard|above",
     "fat_mass_kg": number, "fat_grade": "below|standard|above"},
    {"segment": "right_arm", ...},
    {"segment": "trunk", ...},
    {"segment": "left_leg", ...},
    {"segment": "right_leg", ...}
  ],
  "inbody_data": {
    "bmi": number, "body_water_kg": number, "protein_kg": number,
    "mineral_kg": number, "ideal_weight_kg": number,
    "ideal_body_fat_pct": number, "waist_hip_ratio": number,
    ... any other visible data
  }
}

# meal
{
  "category": "meal",
  "description": "...",
  "meal_type": "breakfast|lunch|dinner|snack",
  "food_items": ["義大利麵", "沙拉", "美式咖啡"],
  "estimated_calories": integer,
  "estimated_protein_g": number,
  "estimated_carbs_g": number,
  "estimated_fat_g": number
}

# training_sheet
{
  "category": "training_sheet",
  "description": "...",
  "date": "YYYY-MM-DD if visible",
  "exercises": [
    { "name": "深蹲",  "raw_text": "40kg*10*4" },
    { "name": "RDL",   "raw_text": "35kg*10*3" }
  ]
}

# progress
{
  "category": "progress",
  "description": "正面/側面/背面，1–3 個具體觀察（對稱性、線條、姿勢），不要主觀美醜評論。"
}

# other
{
  "category": "other",
  "description": "1–2 句具體描述，捕捉與健身可能相關的線索。"
}

IMPORTANT:
- Return ONLY valid JSON, no markdown or explanation.
- Omit any field you cannot determine confidently — never invent numbers.
- For segment grades, map from bar chart levels on the InBody report.
- meal_type / category / description are required for their categories;
  numeric estimates may be omitted if the photo is too ambiguous.
"""


async def classify_and_parse_image(image_bytes: bytes) -> dict | None:
    """Classify a fitness image and extract data if applicable."""
    b64 = base64.b64encode(image_bytes).decode("utf-8")

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": IMAGE_CLASSIFY_PROMPT},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                },
            ],
        }
    ]

    try:
        response = await litellm.acompletion(
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            messages=messages,
            temperature=0.1,
            timeout=30,
        )
        content = response.choices[0].message.content or ""

        # Strip markdown code fences if present
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1] if "\n" in content else content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        return json.loads(content)
    except (litellm.RateLimitError, litellm.AuthenticationError):
        # Bubble these up so the LINE handler can show a service-paused
        # message rather than the generic "couldn't process image" reply.
        raise
    except Exception:
        logger.exception("Failed to classify/parse image")
        return None
