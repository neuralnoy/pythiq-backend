from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from app.auth.deps import get_current_user
from app.db.repositories.token_usage import token_usage_repository

router = APIRouter()

@router.get("/tokens")
async def get_token_usage(
    month: Optional[str] = None,  # Format: YYYY-MM
    window: Optional[str] = "1d",  # 15m, 1h, or 1d
    current_user: dict = Depends(get_current_user)
):
    # If month not provided, use current month
    if not month:
        now = datetime.utcnow()
        month = now.strftime("%Y-%m")
    
    # Parse month to get start and end dates
    try:
        year, month_num = map(int, month.split("-"))
        start_date = datetime(year, month_num, 1)
        if month_num == 12:
            end_date = datetime(year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = datetime(year, month_num + 1, 1) - timedelta(days=1)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid month format. Use YYYY-MM")

    # Get usage data
    usage_data = await token_usage_repository.get_usage_by_user_and_date_range(
        user_id=current_user['email'],
        start_date=start_date.strftime("%Y-%m-%d"),
        end_date=end_date.strftime("%Y-%m-%d")
    )

    # Process data based on window
    window_minutes = {
        "15m": 15,
        "1h": 60,
        "1d": 1440
    }.get(window)
    
    if not window_minutes:
        raise HTTPException(status_code=400, detail="Invalid window. Use 15m, 1h, or 1d")

    # Initialize data structure
    aggregated_data = {}
    
    for record in usage_data:
        # Parse timestamp
        timestamp = datetime.fromisoformat(record['created_at'].replace('Z', '+00:00'))
        
        # Round timestamp based on window
        if window == "1d":
            key = timestamp.strftime("%Y-%m-%d")
        else:
            # Round to nearest window
            minutes = timestamp.hour * 60 + timestamp.minute
            rounded_minutes = (minutes // window_minutes) * window_minutes
            rounded_time = timestamp.replace(
                hour=rounded_minutes // 60,
                minute=rounded_minutes % 60,
                second=0,
                microsecond=0
            )
            key = rounded_time.isoformat()

        if key not in aggregated_data:
            aggregated_data[key] = {
                'total_tokens': 0
            }
        
        # Sum all token types
        total_tokens = (
            record.get('prompt_tokens', 0) +
            record.get('completion_tokens', 0) +
            record.get('embedding_tokens', 0)
        )
        
        aggregated_data[key]['total_tokens'] += total_tokens

    # Convert to list and sort by timestamp
    result = [
        {
            'timestamp': k,
            **v
        }
        for k, v in aggregated_data.items()
    ]
    result.sort(key=lambda x: x['timestamp'])

    return result 