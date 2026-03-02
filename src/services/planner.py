import os
import json
import logging
import openai
from src.core import models

logger = logging.getLogger(__name__)

# ==========================================
# JSON OUTPUT SCHEMA
# ==========================================
# We instruct the LLM to return strictly this JSON structure
PLANNER_PROMPT = """\
You are an elite AI Endurance Coach. Generate a periodized training plan.
Respond with valid JSON only. Use this exact structure:
{
  "plan_name": "string",
  "goal": "string", 
  "total_weeks": number,
  "weeks": [
    {
      "week_number": 1,
      "focus": "Base Building",
      "total_tss": number,
      "workouts": [
        {
          "day": "Monday",
          "type": "Easy Run",
          "distance_km": number,
          "duration_min": number,
          "pace_min_per_km": number,
          "description": "string",
          "key_intervals": []
        }
      ]
    }
  ]
}
Generate ALL weeks in one response. Be specific with paces and intervals."""

async def generate_plan_streaming(
    user_id: int, 
    goal: str, 
    target_date: str, 
    weekly_hours: float, 
    start_date: str,
    rag_context: str,
    # V4: Pre-plan interview fields
    days_per_week: int = 5,
    pb_5k: int = None,
    pb_10k: int = None,
    pb_hm: int = None,
    pb_marathon: int = None,
    experience: str = "intermediate",
    injury: str = None,
    weekly_km: float = None,
):
    from openai import AsyncOpenAI
    from datetime import datetime, timedelta
    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))
    
    prof = models.get_user_profile(user_id)
    
    # V4: Build enhanced athlete context with interview data
    state_str = (
        f"ATHLETE PROFILE:\n"
        f"- Target Goal: {goal}\n"
        f"- Target Race Date: {target_date}\n"
        f"- Plan Start Date: {start_date}\n"
        f"- Available Training Days/Week: {days_per_week}\n"
        f"- Available Training Hours/Week: {weekly_hours}\n"
        f"- Current VDOT: {prof.get('current_vdot', 'Unknown')}\n"
        f"- Resting HR: {prof.get('resting_hr', 'Unknown')}\n"
        f"- Max HR: {prof.get('max_hr', 'Unknown')}\n"
        f"- Experience Level: {experience or 'Unknown'}\n"
        f"- Life Stress: {prof.get('life_stress_level', 'Unknown')}\n"
    )
    
    # Add PBs if provided
    from src.services.sports_science import format_time
    if pb_5k:
        state_str += f"- 5K PB: {format_time(pb_5k)}\n"
    if pb_10k:
        state_str += f"- 10K PB: {format_time(pb_10k)}\n"
    if pb_hm:
        state_str += f"- Half Marathon PB: {format_time(pb_hm)}\n"
    if pb_marathon:
        state_str += f"- Marathon PB: {format_time(pb_marathon)}\n"
    if weekly_km:
        state_str += f"- Current Weekly Mileage: {weekly_km} km\n"
    if injury:
        state_str += f"- Injury / Limitations: {injury}\n"
    
    full_system_prompt = f"{PLANNER_PROMPT}\n\n{state_str}\n\nRAG METHODOLOGY CONTEXT:\n{rag_context}"
    
    try:
        stream = await client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            stream=True,
            messages=[
                {"role": "system", "content": full_system_prompt},
                {"role": "user", "content": f"Generate a training schedule from {start_date} to {target_date}. Plan for {days_per_week} days per week."}
            ],
            temperature=0.3,
            max_tokens=4000
        )
        
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                delta = chunk.choices[0].delta.content
                yield delta
                
        # V4: Do NOT auto-save to DB. The frontend will call /api/planner/confirm
        # after the user reviews and approves the plan.

    except Exception as e:
        logger.error(f"Failed to stream plan: {e}")
