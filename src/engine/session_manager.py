from datetime import datetime, timezone
from typing import List, Tuple, Optional, Dict, Any, Union

class SessionManager:
    """
    Manages and validates global market trading sessions in UTC:
    - London Session: 07:00 - 16:00 UTC (12:00 - 21:00 PKT)
    - New York Session: 12:00 - 21:00 UTC (17:00 - 02:00 PKT)
    - Asian Session: 00:00 - 09:00 UTC (05:00 - 14:00 PKT)
    - 24/7 (Any Session): Unrestricted trading round the clock

    Grounded in verified institutional playbooks:
    - Master Trading Sessions & Killzones Playbook
    - Master Strategy Playbook of Top Global Traders & Live Streamers
    """

    SESSION_WINDOWS = {
        "London Session": (7, 16),
        "New York Session": (12, 21),
        "Asian Session": (0, 9),
    }

    # Strategy-Specific Execution Windows & Killzones from
    # "TRADING SESSIONS & KILLZONES PLAYBOOK" (Pages 1-3)
    STRATEGY_SPECIFIC_WINDOWS = {
        # 1. Michael J. Huddleston (Inner Circle Trader - ICT)
        # Windows: London Killzone (2-5 AM EST / 07:00-10:00 UTC)
        #          NY Killzone (7-10 AM EST / 12:00-15:00 UTC)
        #          ICT Silver Bullet AM (10-11 AM EST / 15:00-16:00 UTC)
        #          ICT Silver Bullet PM (2-3 PM EST / 19:00-20:00 UTC)
        # Note: Asian Range (8 PM - 12 AM EST) is used strictly as liquidity targets, never for entry.
        "ICT": [
            ((7, 0), (10, 0), "London Killzone (07:00-10:00 UTC / 2-5 AM EST)"),
            ((12, 0), (16, 0), "NY Killzone & Silver Bullet AM (12:00-16:00 UTC / 7-11 AM EST)"),
            ((19, 0), (20, 0), "ICT Silver Bullet PM (19:00-20:00 UTC / 2-3 PM EST)")
        ],

        # 2. Vivek Yadav (Trade For Profit / Advance Crypto Trader)
        # Windows: London Open (3-6 AM EST / 08:00-11:00 UTC)
        #          NY Open (8-11 AM EST / 13:00-16:00 UTC)
        #          Macro News Windows (CPI 13:00-14:00 UTC, FOMC 19:00-20:00 UTC)
        # Note: Asian session is strictly for accumulating liquidation clusters on CoinGlass/Hyblock.
        "VIVEK_YADAV": [
            ((8, 0), (11, 0), "London Open Liquidity Sweep (08:00-11:00 UTC / 3-6 AM EST)"),
            ((13, 0), (16, 0), "NY Open & CPI Window (13:00-16:00 UTC / 8-11 AM EST)"),
            ((19, 0), (20, 0), "FOMC News Window (19:00-20:00 UTC / 2-3 PM EST)")
        ],

        # 3. Bernd Skorupinski (FTMO #1 Leaderboard Record Holder)
        # Execution Windows: Session-Independent ('Set and Forget') / 24-7
        # "No Intra-Day Session Restriction: Explicitly states he does not trade specific live sessions.
        # He is a swing trader seeking high-probability HTF zones... Trades fill automatically whether during
        # Asia, London, or NY sessions."
        "BERND_SKORUPINSKI": "SESSION_INDEPENDENT",

        # 4. Ross Cameron (Warrior Trading)
        # Windows: Pre-Market (7:00 AM - 9:30 AM EST / 12:00 - 14:30 UTC)
        #          NY Open First Hour (9:30 AM - 10:30 AM EST / 14:30 - 15:30 UTC)
        # Rule: Stops trading after 10:30 AM EST (15:30 UTC) to avoid mid-day chop.
        "ROSS_CAMERON": [
            ((12, 0), (15, 30), "Pre-Market & NY Open Power Hour (12:00-15:30 UTC / 7:00-10:30 AM EST)")
        ],

        # 5. Ndemazeah Godlove (GU MVR Strategy)
        # Windows: London Open & New York Overlap (2:00 AM - 5:00 PM GMT+2 / 07:00 - 16:30 UTC)
        # Active Hours: Peak GBP/EUR volume hours where 10/23 EMA crossover pullback occurs.
        "NDEMAZEAH_GODLOVE": [
            ((7, 0), (16, 30), "London & NY Overlap Peak Volume (07:00-16:30 UTC / 2 AM-5 PM GMT+2)")
        ],

        # 6. Steven Hart (The Trading Channel) & Rayner Teo
        # Windows: London Open (3:00 AM EST / 08:00 UTC) & NY Open (8:00 AM EST / 13:00 UTC)
        # Active Hours: 08:00 - 17:00 UTC
        # Core Rule: "Avoid Asian Session: Avoid trading major Forex pairs during Asia due to low volatility and wider spreads."
        "STEVEN_HART": [
            ((8, 0), (17, 0), "London & NY Peak Volume Hours (08:00-17:00 UTC / Avoid Asian)")
        ],
        "RAYNER_TEO": [
            ((8, 0), (17, 0), "London & NY Trend Hours (08:00-17:00 UTC / Avoid Asian)")
        ]
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

    @classmethod
    def is_strategy_session_allowed(
        cls,
        strategy_key: str,
        dt: Optional[datetime] = None,
        generic_allowed_sessions: Optional[List[str]] = None,
        asset_type: str = 'forex'
    ) -> Tuple[bool, str]:
        """
        Validates whether trading is permitted for a specific strategy according to the
        'TRADING SESSIONS & KILLZONES PLAYBOOK'.
        
        - If strategy is explicitly defined in STRATEGY_SPECIFIC_WINDOWS:
          The user-selected UI session is ignored, and the strategy's native author
          execution window/killzone is strictly enforced.
        - If strategy is NOT in STRATEGY_SPECIFIC_WINDOWS (or 'DEFAULT'):
          The user-selected UI session settings (generic_allowed_sessions) are respected.
        """
        if dt is None:
            dt = datetime.now(timezone.utc)
        elif dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)

        current_min = dt.hour * 60 + dt.minute

        # Universal Rule 2: Avoid Session Roll-Over (5 PM EST / 21:45-22:15 UTC)
        # Prevents high spread execution and broker daily server resets (Forex & Metals)
        if asset_type != 'crypto':
            if (21 * 60 + 45) <= current_min < (22 * 60 + 15):
                return False, "Session Roll-Over Spread Guard: 5 PM EST / 22:00 UTC daily rollover window"

        # Check if strategy has specific session rules from Playbook
        strat_cfg = cls.STRATEGY_SPECIFIC_WINDOWS.get(strategy_key)

        if strat_cfg is not None:
            # Case 1: Session-Independent (Bernd Skorupinski)
            if strat_cfg == "SESSION_INDEPENDENT":
                return True, "Bernd Skorupinski: Session-Independent ('Set and Forget') / 24-7"

            # Case 2: Specific Killzones & Execution Windows
            matched_windows = []
            for (start_h, start_m), (end_h, end_m), window_name in strat_cfg:
                start_mins = start_h * 60 + start_m
                end_mins = end_h * 60 + end_m

                if start_mins <= end_mins:
                    if start_mins <= current_min < end_mins:
                        matched_windows.append(window_name)
                else:
                    # Wraps over midnight UTC
                    if current_min >= start_mins or current_min < end_mins:
                        matched_windows.append(window_name)

            if matched_windows:
                return True, f"Inside {matched_windows[0]}"

            # Generate informative description of allowed windows
            allowed_desc = " | ".join(w[2].split(' (')[0] for w in strat_cfg)
            return False, f"Outside {strategy_key} Killzone/Session (Designated: {allowed_desc})"

        # Case 3: Strategy not mentioned in Sessions Playbook (or DEFAULT)
        # Respect user's selected autonomous sessions
        return cls.is_session_allowed(generic_allowed_sessions or ["24/7 (Any Session)"], dt)
