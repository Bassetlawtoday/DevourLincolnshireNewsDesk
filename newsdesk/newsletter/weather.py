"""Cached, attributed MET Norway forecast snapshots for newsletter editions."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from .models import WeatherBlock


class WeatherError(RuntimeError):
    pass


SYMBOLS = {
    "clearsky": "clear skies", "fair": "fair conditions",
    "partlycloudy": "partly cloudy conditions", "cloudy": "cloudy conditions",
    "fog": "fog", "lightrain": "light rain", "rain": "rain",
    "heavyrain": "heavy rain", "lightsnow": "light snow", "snow": "snow",
    "heavysnow": "heavy snow", "sleet": "sleet", "rainshowers": "rain showers",
    "heavyrainshowers": "heavy rain showers", "thunderstorm": "thunderstorms",
}


class WeatherForecastService:
    ENDPOINT = "https://api.met.no/weatherapi/locationforecast/2.0/compact"
    USER_AGENT = "DevourLincolnshireNewsDesk/1.0 https://bassetlawtoday.co.uk"

    def __init__(self, cache_path: str | Path | None = None, *, opener=urlopen):
        self.cache_path = Path(cache_path or Path("data/newsletter/weather_cache.json"))
        self.opener = opener

    def fetch_bassetlaw(self) -> WeatherBlock:
        return self.fetch(location="Bassetlaw", latitude=53.3220, longitude=-0.9430)

    def fetch(self, *, location: str, latitude: float, longitude: float) -> WeatherBlock:
        cached = self._load_cache()
        headers = {"User-Agent": self.USER_AGENT, "Accept": "application/json"}
        if cached.get("last_modified"):
            headers["If-Modified-Since"] = cached["last_modified"]
        url = self.ENDPOINT + "?" + urlencode({"lat": f"{latitude:.4f}", "lon": f"{longitude:.4f}"})
        try:
            response = self.opener(Request(url, headers=headers), timeout=15)
            payload = json.loads(response.read().decode("utf-8"))
            last_modified = response.headers.get("Last-Modified", "")
            self._save_cache(payload, last_modified)
        except HTTPError as exc:
            if exc.code == 304 and cached.get("payload"):
                payload = cached["payload"]
            elif cached.get("payload"):
                payload = cached["payload"]
            else:
                raise WeatherError("The weather service is temporarily unavailable.") from None
        except (URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
            if cached.get("payload"):
                payload = cached["payload"]
            else:
                raise WeatherError("The weather service is temporarily unavailable.") from None
        return self._snapshot(payload, location=location)

    def _snapshot(self, payload: dict, *, location: str) -> WeatherBlock:
        local = ZoneInfo("Europe/London")
        today = datetime.now(local).date()
        rows = []
        for entry in payload.get("properties", {}).get("timeseries", []):
            instant = entry.get("data", {}).get("instant", {}).get("details", {})
            when = datetime.fromisoformat(str(entry.get("time", "")).replace("Z", "+00:00"))
            if when.astimezone(local).date() != today:
                continue
            temperature = instant.get("air_temperature")
            if temperature is None:
                continue
            next_hour = entry.get("data", {}).get("next_1_hours", {})
            symbol = str(next_hour.get("summary", {}).get("symbol_code", "")).split("_")[0]
            precipitation = next_hour.get("details", {}).get("precipitation_amount", 0) or 0
            rows.append((float(temperature), symbol, float(precipitation)))
        if not rows:
            raise WeatherError("No forecast is available for Bassetlaw today.")
        low, high = round(min(row[0] for row in rows)), round(max(row[0] for row in rows))
        symbol = max((row[1] for row in rows if row[1]), key=lambda value: sum(r[1] == value for r in rows), default="")
        rain = sum(row[2] for row in rows)
        conditions = SYMBOLS.get(symbol, symbol.replace("_", " ") or "mixed conditions")
        summary = f"Expect {conditions}, with temperatures between {low}°C and {high}°C."
        if rain >= 0.1:
            summary += f" Around {rain:.1f} mm of precipitation is forecast."
        return WeatherBlock(
            included=True,
            location=location,
            headline=f"Today’s weather in {location}",
            summary=summary,
            fetched_at=datetime.now(timezone.utc),
        )

    def _load_cache(self) -> dict:
        try:
            return json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return {}

    def _save_cache(self, payload: dict, last_modified: str) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.cache_path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"last_modified": last_modified, "payload": payload}), encoding="utf-8")
        temporary.replace(self.cache_path)


__all__ = ["WeatherError", "WeatherForecastService"]
