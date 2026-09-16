from datetime import datetime, timezone
from typing import List, Tuple, Optional

class SessionManager:
    """
    Manages and validates global market trading sessions in UTC:
    - London Session: 07:00 - 16:00 UTC (12:00 - 21:00 PKT)
    - New York Session: 12:00 - 21:00 UTC (17:00 - 02:00 PKT)
    - Asian Session: 00:00 - 09:00 UTC (05:00 - 14:00 PKT)
    - 24/7 (Any Session): Unrestricted trading round the clock
    """

    SESSION_WINDOWS = {
        "London Session": (7, 16),
        "New York Session": (12, 21),
        "Asian Session": (0, 9),
    }

    @classmethod
    def get_active_market_sessions(cls, dt: Optional[datetime] = None) -> List[str]:
        """
        Returns the list of currently active market session names for the given UTC datetime.
        """
        if dt is None:
            dt = datetime.now(timezone.utc)
        elif dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)

        current_hour = dt.hour
        active = []

        for name, (start_h, end_h) in cls.SESSION_WINDOWS.items():
            if start_h <= current_hour < end_h:
                active.append(name)

        return active

    @classmethod
    def is_session_allowed(cls, allowed_sessions: List[str], dt: Optional[datetime] = None) -> Tuple[bool, str]:
        """
        Validates if current time falls within any of the user-selected allowed sessions.
        Returns: (is_allowed: bool, reason: str)
        """
        if not allowed_sessions or any("24/7" in s for s in allowed_sessions):
            return True, "24/7 Trading Mode Active"

        active = cls.get_active_market_sessions(dt)
        if not active:
            return False, "Outside all major market sessions (Off-hours chop window)"

        # Check for intersection
        matched = []
        for req in allowed_sessions:
            for act in active:
                if req.lower() in act.lower() or act.lower() in req.lower():
                    matched.append(act)

        if matched:
            return True, f"Active session: {', '.join(set(matched))}"
        
        return False, f"Current active ({', '.join(active)}) not in selected ({', '.join(allowed_sessions)})"
