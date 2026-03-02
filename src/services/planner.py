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
    rag_context: str
):
    from openai import AsyncOpenAI
    from datetime import datetime, timedelta
    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))
    
    prof = models.get_user_profile(user_id)
    
    state_str = (
        f"ATHLETE PROFILE:\n"
        f"- Target Goal: {goal}\n"
        f"- Target Race Date: {target_date}\n"
        f"- Plan Start Date: {start_date}\n"
        f"- Available Training Hours/Week: {weekly_hours}\n"
        f"- Current VDOT: {prof.get('current_vdot', 'Unknown')}\n"
        f"- Resting HR: {prof.get('resting_hr', 'Unknown')}\n"
        f"- Life Stress: {prof.get('life_stress_level', 'Unknown')}\n"
    )
    
    full_system_prompt = f"{PLANNER_PROMPT}\n\n{state_str}\n\nRAG METHODOLOGY CONTEXT:\n{rag_context}"
    
    try:
        stream = await client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            stream=True,
            messages=[
                {"role": "system", "content": full_system_prompt},
                {"role": "user", "content": f"Generate a training schedule from {start_date} to {target_date}."}
            ],
            temperature=0.3,
            max_tokens=4000
        )
        
        buffer = ""
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                delta = chunk.choices[0].delta.content
                buffer += delta
                yield delta
                
        # Once complete, parse and save to DB
        try:
            plan = json.loads(buffer)
            plan_id = models.create_training_plan(
                user_id=user_id, goal=goal, target_date=target_date, weekly_hours=weekly_hours
            )
            # Save workouts 
            sd = datetime.strptime(start_date, '%Y-%m-%d')
            days_map = {"Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3, "Friday": 4, "Saturday": 5, "Sunday": 6}
            start_weekday = sd.weekday()
            
            for week in plan.get("weeks", []):
                wn = week.get("week_number", 1) - 1
                for w in week.get("workouts", []):
                    day_name = w.get("day", "Monday")
                    day_offset = days_map.get(day_name, 0)
                    target_day = sd + timedelta(days=(wn * 7) + day_offset - start_weekday)
                    if target_day < sd:
                        target_day = target_day + timedelta(days=7) 
                        
                    models.add_planned_workout(
                        plan_id=plan_id,
                        date=target_day.strftime('%Y-%m-%d'),
                        sport="Run",
                        workout_type=w.get("type", "Workout"),
                        dist=w.get("distance_km", 0) * 1000,
                        dur=w.get("duration_min", 0) * 60,
                        desc=w.get("description", "") + f" | Pace: {w.get('pace_min_per_km','N/A')}/km"
                    )
        except Exception as e:
            logger.error(f"Failed to json parse / save streaming plan: {e}")

    except Exception as e:
        logger.error(f"Failed to stream plan: {e}")
