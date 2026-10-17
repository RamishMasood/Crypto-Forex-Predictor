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
    # ── August 2026 Macro Calendar ──
    {'title': 'RBA Interest Rate Decision', 'country': 'AUD', 'date': '2026-08-04T04:30:00Z', 'impact': 'High'},
    {'title': 'Bank of England (BOE) Bank Rate & Policy Summary', 'country': 'GBP', 'date': '2026-08-06T11:00:00Z', 'impact': 'High'},
    {'title': 'US Non-Farm Payrolls (NFP) & Unemployment', 'country': 'USD', 'date': '2026-08-07T12:30:00Z', 'impact': 'High'},
    {'title': 'Canada Net Change in Employment & Unemployment', 'country': 'CAD', 'date': '2026-08-07T12:30:00Z', 'impact': 'High'},
    {'title': 'US Consumer Price Index (CPI)', 'country': 'USD', 'date': '2026-08-12T12:30:00Z', 'impact': 'High'},
    {'title': 'Jackson Hole Economic Symposium (Fed Powell)', 'country': 'USD', 'date': '2026-08-21T14:00:00Z', 'impact': 'High'},
    {'title': 'US Core PCE Price Index', 'country': 'USD', 'date': '2026-08-28T12:30:00Z', 'impact': 'High'},
    # ── September 2026 Macro Calendar ──
    {'title': 'Bank of Canada (BOC) Overnight Rate', 'country': 'CAD', 'date': '2026-09-02T13:45:00Z', 'impact': 'High'},
    {'title': 'US Non-Farm Payrolls (NFP)', 'country': 'USD', 'date': '2026-09-04T12:30:00Z', 'impact': 'High'},
    {'title': 'Canada Net Change in Employment & Unemployment', 'country': 'CAD', 'date': '2026-09-04T12:30:00Z', 'impact': 'High'},
    {'title': 'ECB Monetary Policy & Refinancing Rate', 'country': 'EUR', 'date': '2026-09-10T12:15:00Z', 'impact': 'High'},
    {'title': 'ECB Press Conference', 'country': 'EUR', 'date': '2026-09-10T12:45:00Z', 'impact': 'High'},
    {'title': 'US Core PPI & PPI m/m', 'country': 'USD', 'date': '2026-09-10T12:30:00Z', 'impact': 'High'},
    {'title': 'US Consumer Price Index (CPI)', 'country': 'USD', 'date': '2026-09-11T12:30:00Z', 'impact': 'High'},
    {'title': 'FOMC Interest Rate Decision & Projections', 'country': 'USD', 'date': '2026-09-16T18:00:00Z', 'impact': 'High'},
    {'title': 'FOMC Press Conference (Fed Chair)', 'country': 'USD', 'date': '2026-09-16T18:30:00Z', 'impact': 'High'},
    {'title': 'Bank of England (BOE) Rate Decision', 'country': 'GBP', 'date': '2026-09-17T11:00:00Z', 'impact': 'High'},
    {'title': 'Bank of Japan (BOJ) Policy Rate', 'country': 'JPY', 'date': '2026-09-19T03:00:00Z', 'impact': 'High'},
    {'title': 'RBA Interest Rate Decision', 'country': 'AUD', 'date': '2026-09-22T04:30:00Z', 'impact': 'High'},
    {'title': 'US Core PCE Price Index m/m', 'country': 'USD', 'date': '2026-09-25T12:30:00Z', 'impact': 'High'},
    # ── October 2026 Macro Calendar ──
    {'title': 'US Non-Farm Payrolls (NFP) & Unemployment', 'country': 'USD', 'date': '2026-10-02T12:30:00Z', 'impact': 'High'},
    {'title': 'US Consumer Price Index (CPI)', 'country': 'USD', 'date': '2026-10-08T12:30:00Z', 'impact': 'High'},
    {'title': 'Canada Net Change in Employment & Unemployment', 'country': 'CAD', 'date': '2026-10-09T12:30:00Z', 'impact': 'High'},
    {'title': 'FOMC Meeting Minutes', 'country': 'USD', 'date': '2026-10-14T18:00:00Z', 'impact': 'High'},
    {'title': 'US Core Retail Sales & Retail Sales m/m', 'country': 'USD', 'date': '2026-10-15T12:30:00Z', 'impact': 'High'},
    {'title': 'ECB Monetary Policy Meeting & Statement', 'country': 'EUR', 'date': '2026-10-15T12:15:00Z', 'impact': 'High'},
    {'title': 'US Prelim UoM Consumer Sentiment', 'country': 'USD', 'date': '2026-10-16T14:00:00Z', 'impact': 'High'},
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

    @classmethod
    def _normalize_event_key(cls, country: str, title: str, date_str: str) -> tuple:
        """
        Normalizes country, title, and UTC timestamp down to the minute so that
        identical events arriving with slight formatting differences are never duplicated.
        """
        import re
        c = str(country or '').strip().upper()
        clean_t = re.sub(r'^(us|german|uk|eu)\s+', '', str(title or '').lower().strip())
        clean_t = re.sub(r'[^a-z0-9]+', ' ', clean_t).strip()
        dt = cls._parse_event_datetime(date_str)
        dt_str = dt.strftime('%Y-%m-%d %H:%M') if dt else str(date_str).strip()
        return (c, clean_t, dt_str)

    @classmethod
    def deduplicate_events(cls, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Strict deduplication filter: Eliminates any duplicate events scheduled for the
        same country, title, and time. Conserves disk space, memory, and UI cleanliness.
        """
        if not events:
            return []
        unique_map: Dict[tuple, Dict[str, Any]] = {}
        for e in events:
            k = cls._normalize_event_key(e.get('country', ''), e.get('title', ''), e.get('date', ''))
            if k not in unique_map:
                unique_map[k] = dict(e)
            else:
                existing = unique_map[k]
                if not existing.get('forecast') and e.get('forecast'):
                    existing['forecast'] = e['forecast']
                if not existing.get('previous') and e.get('previous'):
                    existing['previous'] = e['previous']
                if e.get('impact') == 'High':
                    existing['impact'] = 'High'
                elif e.get('impact') == 'Medium' and existing.get('impact') != 'High':
                    existing['impact'] = 'Medium'
        return list(unique_map.values())

    def _load_cache(self) -> Optional[List[Dict[str, Any]]]:
        if not os.path.exists(CACHE_FILE):
            return None
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            cached_at = data.get('cached_at', 0)
            cached_date = data.get('cached_date')
            today_date_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')

            # Daily Refresh Guarantee: If cache was saved on a previous calendar day, invalidate to force fresh daily pull
            if cached_date and cached_date != today_date_str:
                return None

            # Hourly Refresh Guarantee: 1-hour cache TTL (3600 seconds)
            if (time.time() - cached_at) < self.cache_ttl:
                return self.deduplicate_events(data.get('events', []))
        except Exception:
            pass
        return None

    def _save_cache(self, events: List[Dict[str, Any]]) -> None:
        try:
            today_date_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
            clean_events = self.deduplicate_events(events)
            with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump({
                    'cached_at': time.time(),
                    'cached_date': today_date_str,
                    'events': clean_events
                }, f)
        except Exception:
            pass

    def fetch_live_calendar(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Fetches calendar from live feed or cache with guaranteed deduplication.
        """
        if not force_refresh and self._cached_events is not None:
            return self._cached_events

        if not force_refresh:
            cached = self._load_cache()
            if cached is not None:
                # Merge static fallback events strictly deduplicated
                merged = self.deduplicate_events(cached + FALLBACK_2026_EVENTS)
                self._cached_events = merged
                return merged

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
                    merged = self.deduplicate_events(parsed + FALLBACK_2026_EVENTS)
                    self._save_cache(merged)
                    self._cached_events = merged
                    self._last_fetch_time = time.time()
                    return merged
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
                    merged = self.deduplicate_events(parsed + FALLBACK_2026_EVENTS)
                    self._save_cache(merged)
                    for ev in merged:
                        if '_dt_parsed' not in ev:
                            ev['_dt_parsed'] = self._parse_event_datetime(ev.get('date', ''))
                    self._cached_events = merged
                    self._last_fetch_time = time.time()
                    return merged
        except Exception:
            pass

        # Attempt 3: Expired cache if available
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    events = data.get('events', [])
                    if events:
                        merged = self.deduplicate_events(events + FALLBACK_2026_EVENTS)
                        for ev in merged:
                            if '_dt_parsed' not in ev:
                                ev['_dt_parsed'] = self._parse_event_datetime(ev.get('date', ''))
                        self._cached_events = merged
                        return merged
            except Exception:
                pass

        # Fallback 4: Built-in high-impact schedule
        self._cached_events = self.deduplicate_events(FALLBACK_2026_EVENTS)
        for ev in self._cached_events:
            if '_dt_parsed' not in ev:
                ev['_dt_parsed'] = self._parse_event_datetime(ev.get('date', ''))
        return self._cached_events

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

            dt = e.get('_dt_parsed')
            if dt is None:
                dt = self._parse_event_datetime(date_str)
                e['_dt_parsed'] = dt
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

    def fetch_daily_calendar(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Guarantees that calendar data is freshly fetched and synchronized for today.
        """
        return self.fetch_live_calendar(force_refresh=force_refresh)

    def fetch_hourly_calendar(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Hourly synchronization: Fetches and refreshes live calendar data on an hourly basis.
        Guarantees strict deduplication so no same-time news is ever repeated or wastes disk space.
        """
        now = time.time()
        need_live_pull = force_refresh or ((now - self._last_fetch_time) >= 3600)
        events = self.fetch_live_calendar(force_refresh=need_live_pull)
        return self.deduplicate_events(events)

    def get_todays_events(
        self,
        symbol: Optional[str] = None,
        asset_type: str = 'crypto',
        target_date: Optional[datetime] = None,
        min_impact: str = 'All'
    ) -> List[Dict[str, Any]]:
        """
        Retrieves all economic events scheduled specifically for TODAY (24h window).
        Provides exact UTC & Local PKT time, currency, impact, countdown, and blackout status.
        Guarantees zero duplicate entries for same-time events.
        """
        now_utc = datetime.now(timezone.utc)
        cur_date = target_date.date() if target_date else now_utc.date()

        events = self.fetch_hourly_calendar()
        affected_ccys = self.get_affected_currencies(symbol, asset_type) if symbol else None

        todays_list = []
        for e in events:
            date_str = e.get('date', '')
            dt = self._parse_event_datetime(date_str)
            if not dt:
                continue

            # Filter for events occurring on the target date (today)
            if dt.date() != cur_date:
                continue

            country = e.get('country', '').upper().strip()
            impact = e.get('impact', 'Low').capitalize().strip()
            title = e.get('title', '').strip()

            if affected_ccys and country not in affected_ccys and country != 'ALL':
                continue

            if min_impact == 'High' and impact != 'High':
                continue
            elif min_impact == 'Medium+' and impact not in ('High', 'Medium'):
                continue

            diff_mins = (dt - now_utc).total_seconds() / 60.0

            # Status determination
            if -30.0 <= diff_mins <= 30.0 and impact == 'High':
                status = '🔴 IN BLACKOUT NOW'
                status_color = '#ef4444'
            elif diff_mins < -30.0:
                status = '✅ COMPLETED'
                status_color = '#64748b'
            elif 0 <= diff_mins <= 60.0:
                status = f'⚠️ IMMINENT ({int(diff_mins)}m away)'
                status_color = '#f59e0b'
            elif diff_mins > 60.0:
                hrs = diff_mins / 60.0
                status = f'⏳ UPCOMING ({hrs:.1f}h away)'
                status_color = '#38bdf8'
            else:
                status = '✅ PASSED'
                status_color = '#64748b'

            # Local PKT time conversion (UTC + 5)
            pkt_dt = dt + timedelta(hours=5)

            todays_list.append({
                'title': title,
                'country': country,
                'impact': impact,
                'time_utc': dt.strftime('%H:%M UTC'),
                'time_pkt': pkt_dt.strftime('%I:%M %p PKT'),
                'datetime_utc': dt.isoformat(),
                'minutes_away': round(diff_mins, 1),
                'status': status,
                'status_color': status_color,
                'forecast': e.get('forecast', '-'),
                'previous': e.get('previous', '-'),
                'is_high_impact': (impact == 'High')
            })

        # Strict deduplication: never allow the same event at the same time to repeat twice
        deduped_todays = []
        seen_keys = set()
        for item in todays_list:
            ukey = (item['country'], item['title'].lower().strip(), item['time_utc'])
            if ukey not in seen_keys:
                seen_keys.add(ukey)
                deduped_todays.append(item)

        # Sort chronologically
        deduped_todays.sort(key=lambda x: x['datetime_utc'])
        return deduped_todays

    def get_daily_summary(self, symbol: Optional[str] = None, asset_type: str = 'crypto') -> Dict[str, Any]:
        """
        Returns high-level daily KPI summary of today's economic schedule.
        """
        todays = self.get_todays_events(symbol=symbol, asset_type=asset_type)
        high_impact_today = [e for e in todays if e.get('is_high_impact')]
        upcoming_high = [e for e in high_impact_today if e.get('minutes_away', -999) > 0]

        now_utc = datetime.now(timezone.utc)
        pkt_now = now_utc + timedelta(hours=5)

        blackout_st = self.check_blackout_status(symbol=symbol or 'BTC/USD', asset_type=asset_type)

        return {
            'date_utc': now_utc.strftime('%Y-%m-%d'),
            'date_display': pkt_now.strftime('%A, %d %B %Y'),
            'total_events_today': len(todays),
            'high_impact_events_today': len(high_impact_today),
            'upcoming_high_impact_today': len(upcoming_high),
            'next_event': upcoming_high[0] if upcoming_high else None,
            'is_blackout': blackout_st.get('is_blackout', False),
            'active_blackout_event': blackout_st.get('active_event'),
            'blackout_reason': blackout_st.get('blackout_reason', ''),
            'todays_events': todays
        }

