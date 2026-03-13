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
- "inbody": An InBody or body composition analyzer report/printout
- "progress": Gym selfie, physique photo, before/after comparison
- "meal": Food or meal photo
- "other": Anything else

Step 2: Return a JSON object based on the category.

For ALL categories, include:
{
  "category": "inbody|progress|meal|other",
  "description": "Brief description in Traditional Chinese (zh-TW)"
}

For "inbody" ONLY, also include all extractable fields:
{
  "category": "inbody",
  "description": "InBody report description",
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
    "bmi": number,
    "body_water_kg": number,
    "protein_kg": number,
    "mineral_kg": number,
    "ideal_weight_kg": number,
    "ideal_body_fat_pct": number,
    "waist_hip_ratio": number,
    ... any other visible data
  }
}

IMPORTANT:
- Return ONLY valid JSON, no markdown or explanation.
- Use "below", "standard", "above" for grades.
- For segment grades, map from bar chart levels on the report.
- Omit fields not visible in the image (except category and description).
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
    except Exception:
        logger.exception("Failed to classify/parse image")
        return None
