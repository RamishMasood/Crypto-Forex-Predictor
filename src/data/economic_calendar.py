"""
Economic News & High-Impact Event Blackout Filter
Fetches live economic calendar data from ForexFactory (fair economy feed),
caches locally on disk to prevent rate limits, and provides a 30-minute
pre/post event blackout filter for high-impact ('red folder') releases (FOMC, CPI, NFP, ECB, PPI, etc.).
Requires ZERO private API keys.
"""

import os
import io
import csv
import json
import time
import requests
import pandas as pd
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta

CACHE_DIR = os.path.join(os.path.dirname(__file__), 'cache')
CACHE_FILE = os.path.join(CACHE_DIR, 'economic_calendar_cache.json')
CACHE_TTL_SECONDS = 3600  # 1 hour cache TTL

FOREX_FACTORY_JSON_URL = 'https://nfs.faireconomy.media/ff_calendar_thisweek.json'
FOREX_FACTORY_CSV_URL = 'https://nfs.faireconomy.media/ff_calendar_thisweek.csv'

# Standard recurring major central bank and macroeconomic release keywords
HIGH_IMPACT_KEYWORDS = [
    'FOMC', 'FEDERAL FUNDS RATE', 'CPI', 'CONSUMER PRICE INDEX',
    'NON-FARM', 'NONFARM', 'NFP', 'UNEMPLOYMENT RATE', 'GDP',
    'INTEREST RATE', 'RATE DECISION', 'ECB', 'MONETARY POLICY',
    'REFINANCING RATE', 'PRESS CONFERENCE', 'PPI', 'CORE CPI',
    'RETAIL SALES', 'POWELL', 'LAGARDE', 'BOE', 'BOJ', 'SNB'
]

# Static fallback schedule of major 2026 macroeconomic dates (UTC)
# Ensures zero-failure resilience even during total network or Cloudflare outages
FALLBACK_2026_EVENTS = [
    {'title': 'ECB Monetary Policy & Refinancing Rate', 'country': 'EUR', 'date': '2026-09-10T12:15:00Z', 'impact': 'High'},
    {'title': 'ECB Press Conference', 'country': 'EUR', 'date': '2026-09-10T12:45:00Z', 'impact': 'High'},
    {'title': 'US Core PPI & PPI m/m', 'country': 'USD', 'date': '2026-09-10T12:30:00Z', 'impact': 'High'},
    {'title': 'US Consumer Price Index (CPI)', 'country': 'USD', 'date': '2026-09-11T12:30:00Z', 'impact': 'High'},
    {'title': 'FOMC Interest Rate Decision & Projections', 'country': 'USD', 'date': '2026-09-16T18:00:00Z', 'impact': 'High'},
    {'title': 'FOMC Press Conference (Fed Chair)', 'country': 'USD', 'date': '2026-09-16T18:30:00Z', 'impact': 'High'},
    {'title': 'Bank of England (BOE) Rate Decision', 'country': 'GBP', 'date': '2026-09-17T11:00:00Z', 'impact': 'High'},
    {'title': 'Bank of Japan (BOJ) Policy Rate', 'country': 'JPY', 'date': '2026-09-19T03:00:00Z', 'impact': 'High'},
    {'title': 'US Non-Farm Payrolls (NFP) & Unemployment', 'country': 'USD', 'date': '2026-10-02T12:30:00Z', 'impact': 'High'},
]


class EconomicCalendarManager:
    """
    Manages live economic events, local caching, and high-impact trading blackouts.
    """

    def __init__(self, cache_ttl: int = CACHE_TTL_SECONDS):
        self.cache_ttl = cache_ttl
        os.makedirs(CACHE_DIR, exist_ok=True)
        self._cached_events: Optional[List[Dict[str, Any]]] = None
        self._last_fetch_time: float = 0.0

    def _load_cache(self) -> Optional[List[Dict[str, Any]]]:
        if not os.path.exists(CACHE_FILE):
            return None
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            cached_at = data.get('cached_at', 0)
            if (time.time() - cached_at) < self.cache_ttl:
                return data.get('events', [])
        except Exception:
            pass
        return None

    def _save_cache(self, events: List[Dict[str, Any]]) -> None:
        try:
            with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump({'cached_at': time.time(), 'events': events}, f)
        except Exception:
            pass

    def fetch_live_calendar(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Fetches calendar from live feed or cache.
        """
        if not force_refresh:
            cached = self._load_cache()
            if cached is not None:
                self._cached_events = cached
                return cached

        # Attempt 1: ForexFactory JSON endpoint
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        try:
            resp = requests.get(FOREX_FACTORY_JSON_URL, headers=headers, timeout=5)
            if resp.status_code == 200:
                raw_events = resp.json()
                parsed = []
                for e in raw_events:
                    parsed.append({
                        'title': str(e.get('title', '')).strip(),
                        'country': str(e.get('country', '')).upper().strip(),
                        'date': str(e.get('date', '')),
                        'impact': str(e.get('impact', 'Low')).capitalize().strip(),
                        'forecast': str(e.get('forecast', '')).strip(),
                        'previous': str(e.get('previous', '')).strip(),
                        'source': 'forexfactory_live_json'
                    })
                if parsed:
                    self._save_cache(parsed)
                    self._cached_events = parsed
                    return parsed
        except Exception:
            pass

        # Attempt 2: ForexFactory CSV endpoint (less prone to Cloudflare rate limits)
        try:
            resp = requests.get(FOREX_FACTORY_CSV_URL, headers=headers, timeout=5)
            if resp.status_code == 200:
                text = resp.content.decode('utf-8', errors='ignore')
                reader = csv.DictReader(text.splitlines())
                parsed = []
                for row in reader:
                    title = row.get('Title') or row.get('title')
                    country = row.get('Country') or row.get('country')
                    impact = row.get('Impact') or row.get('impact')
                    date_str = row.get('Date') or row.get('date')
                    time_str = row.get('Time') or row.get('time')
                    if title and country and date_str:
                        # Convert date/time to ISO-like
                        dt_iso = f"{date_str} {time_str}".strip()
                        parsed.append({
                            'title': str(title).strip(),
                            'country': str(country).upper().strip(),
                            'date': dt_iso,
                            'impact': str(impact or 'Low').capitalize().strip(),
                            'forecast': str(row.get('Forecast', '')).strip(),
                            'previous': str(row.get('Previous', '')).strip(),
                            'source': 'forexfactory_live_csv'
                        })
                if parsed:
                    self._save_cache(parsed)
                    self._cached_events = parsed
                    return parsed
        except Exception:
            pass

        # Attempt 3: Expired cache if available
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    events = data.get('events', [])
                    if events:
                        self._cached_events = events
                        return events
            except Exception:
                pass

        # Fallback 4: Built-in high-impact schedule
        self._cached_events = FALLBACK_2026_EVENTS
        return FALLBACK_2026_EVENTS

    @staticmethod
    def _parse_event_datetime(date_str: str) -> Optional[datetime]:
        """
        Parses various date strings into an aware UTC datetime object.
        ForexFactory CSV formats without timezone offsets are standard US Eastern Time.
        """
        if not date_str:
            return None
        try:
            # ISO 8601 with timezone (e.g. 2026-09-10T08:15:00-04:00 or 2026-09-10T12:15:00Z)
            dt = pd.to_datetime(date_str)
            if dt.tzinfo is None:
                try:
                    dt = dt.tz_localize('America/New_York').tz_convert('UTC')
                except Exception:
                    dt = dt.tz_localize('UTC')
            else:
                dt = dt.tz_convert('UTC')
            return dt.to_pydatetime()
        except Exception:
            pass

        # Fallback date + time e.g. 09-10-2026 8:30am (ForexFactory CSV standard)
        try:
            dt = pd.to_datetime(date_str, format='%m-%d-%Y %I:%M%p')
            try:
                dt = dt.tz_localize('America/New_York').tz_convert('UTC')
            except Exception:
                dt = dt.tz_localize('UTC')
            return dt.to_pydatetime()
        except Exception:
            pass

        return None

    @staticmethod
    def get_affected_currencies(symbol: str, asset_type: str = 'crypto') -> List[str]:
        """
        Determines which economic countries/currencies influence the given asset.
        """
        sym = symbol.upper().replace('-', '/').replace('_', '/')
        if asset_type.lower() == 'crypto':
            # Major USD macroeconomic releases drive crypto volatility (FOMC, CPI, NFP)
            return ['USD']
        
        # Forex pairs: e.g. EUR/USD -> EUR, USD
        parts = sym.split('/')
        if len(parts) == 2:
            base, quote = parts[0], parts[1]
            # Special commodities proxy
            if base in ['XAU', 'XAG', 'WTI']:
                return ['USD']
            return [base, quote]
        
        # Default
        return ['USD', 'EUR', 'GBP']

    def check_blackout_status(
        self,
        symbol: str,
        asset_type: str = 'crypto',
        check_time: Optional[datetime] = None,
        blackout_minutes: int = 30
    ) -> Dict[str, Any]:
        """
        Checks if the current time is within [-blackout_minutes, +blackout_minutes]
        of a High-Impact ("red folder") economic event.
        """
        if check_time is None:
            now_utc = datetime.now(timezone.utc)
        elif check_time.tzinfo is None:
            now_utc = check_time.replace(tzinfo=timezone.utc)
        else:
            now_utc = check_time.astimezone(timezone.utc)

        events = self.fetch_live_calendar()
        affected_ccys = self.get_affected_currencies(symbol, asset_type)

        is_blackout = False
        active_blackout_event = None
        min_abs_diff_mins = 999999.0
        upcoming_events = []

        for e in events:
            country = e.get('country', '').upper()
            impact = e.get('impact', 'Low')
            title = e.get('title', '')
            date_str = e.get('date', '')

            # Check if event affects this pair and is High impact
            is_high_impact = (impact == 'High') or any(kw in title.upper() for kw in HIGH_IMPACT_KEYWORDS)
            affects_pair = (country in affected_ccys) or (country == 'ALL')

            if not affects_pair or not is_high_impact:
                continue

            dt = self._parse_event_datetime(date_str)
            if dt is None:
                continue

            diff_secs = (dt - now_utc).total_seconds()
            diff_mins = diff_secs / 60.0

            event_summary = {
                'title': title,
                'country': country,
                'impact': impact,
                'datetime_utc': dt.isoformat(),
                'minutes_away': round(diff_mins, 1),
                'forecast': e.get('forecast', ''),
                'previous': e.get('previous', '')
            }

            # Collect upcoming events within next 24 hours
            if 0 <= diff_mins <= 1440:
                upcoming_events.append(event_summary)

            # Check blackout window: within blackout_minutes before OR after
            if -blackout_minutes <= diff_mins <= blackout_minutes:
                is_blackout = True
                if abs(diff_mins) < min_abs_diff_mins:
                    min_abs_diff_mins = abs(diff_mins)
                    active_blackout_event = event_summary

        # Sort upcoming
        upcoming_events.sort(key=lambda x: x['minutes_away'])

        if is_blackout and active_blackout_event:
            mins_away = active_blackout_event['minutes_away']
            if mins_away > 0:
                timing_desc = f"in {mins_away:.0f} minutes"
            elif mins_away < 0:
                timing_desc = f"{abs(mins_away):.0f} minutes ago"
            else:
                timing_desc = "RIGHT NOW"

            reason = (
                f"HIGH-IMPACT NEWS BLACKOUT: [{active_blackout_event['country']}] "
                f"{active_blackout_event['title']} release ({timing_desc}). "
                f"Trading strictly halted within +/-{blackout_minutes} min window."
            )
        else:
            reason = "Economic news conditions CLEAR. No active high-impact release within 30 minutes."

        return {
            'is_blackout': is_blackout,
            'active_event': active_blackout_event,
            'blackout_reason': reason,
            'blackout_window_mins': blackout_minutes,
            'affected_currencies': affected_ccys,
            'upcoming_high_impact_events': upcoming_events[:5]
        }
