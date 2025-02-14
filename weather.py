import requests
import logging
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Optional, Dict, Union
from flask import current_app

logger = logging.getLogger(__name__)

JsonDict = Dict[str, Union[str, float, int]]

def get_cache_key() -> float:
    """
    Generate a cache key based on the current time interval.
    The key changes every CACHE_TIMEOUT_MINUTES to control cache invalidation.
    
    Returns:
        float: Unix timestamp for current cache interval
    """
    now = datetime.now()
    interval = now.replace(second=0, microsecond=0)
    cache_timeout = current_app.config.get('CACHE_TIMEOUT_MINUTES', 15)
    interval = interval - timedelta(minutes=interval.minute % cache_timeout)
    return interval.timestamp()

@lru_cache(maxsize=1)
def fetch_weather_data(cache_key: float) -> Optional[JsonDict]:
    """
    Fetch current weather and forecast data from OpenWeatherMap API.
    Results are cached based on the cache_key.
    
    Args:
        cache_key: Timestamp used for cache control
        
    Returns:
        Optional[dict]: Weather data dictionary or None if fetch fails
    """
    api_key = current_app.config.get('WEATHER_API_KEY')
    if not api_key:
        logger.error("Weather API key not configured")
        return None

    lat = current_app.config.get('LOCATION_LAT')
    lon = current_app.config.get('LOCATION_LON')
    
    try:
        # Fetch current weather
        current_weather = fetch_current_weather(lat, lon, api_key)
        if not current_weather:
            return None
            
        # Fetch forecast
        forecast = fetch_forecast(lat, lon, api_key)
        if not forecast:
            return None
            
        # Combine and process the data
        return process_weather_data(current_weather, forecast)
        
    except Exception as e:
        logger.error(f"Weather data fetch error: {str(e)}")
        return None

def fetch_current_weather(lat: str, lon: str, api_key: str) -> Optional[JsonDict]:
    """
    Fetch current weather conditions from OpenWeatherMap API.
    
    Args:
        lat: Latitude
        lon: Longitude
        api_key: OpenWeatherMap API key
        
    Returns:
        Optional[dict]: Current weather data or None if fetch fails
    """
    current_url = (
        f'https://api.openweathermap.org/data/2.5/weather'
        f'?lat={lat}&lon={lon}&appid={api_key}&units=metric'
    )
    
    try:
        response = requests.get(current_url, timeout=5)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Current weather API error: {str(e)}")
        return None

def fetch_forecast(lat: str, lon: str, api_key: str) -> Optional[JsonDict]:
    """
    Fetch weather forecast from OpenWeatherMap API.
    
    Args:
        lat: Latitude
        lon: Longitude
        api_key: OpenWeatherMap API key
        
    Returns:
        Optional[dict]: Forecast data or None if fetch fails
    """
    forecast_url = (
        f'https://api.openweathermap.org/data/2.5/forecast'
        f'?lat={lat}&lon={lon}&appid={api_key}&units=metric'
    )
    
    try:
        response = requests.get(forecast_url, timeout=5)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Forecast API error: {str(e)}")
        return None

def process_weather_data(current_data: JsonDict, forecast_data: JsonDict) -> JsonDict:
    """
    Process and combine current weather and forecast data.
    
    Args:
        current_data: Current weather data from API
        forecast_data: Forecast data from API
        
    Returns:
        dict: Combined and processed weather information
    """
    # Get next 3 hours of forecast data
    next_3_hours = forecast_data['list'][:1]  # First forecast entry (3-hour step)
    
    # Extract rain data
    rain_last_hour = current_data.get('rain', {}).get('1h', 0)
    rain_forecast = next_3_hours[0].get('rain', {}).get('3h', 0) if next_3_hours else 0
    rain_probability = round(next_3_hours[0].get('pop', 0) * 100) if next_3_hours else 0
    
    return {
        'temperature': current_data['main']['temp'],
        'feels_like': current_data['main']['feels_like'],
        'temperature_min': current_data['main']['temp_min'],
        'temperature_max': current_data['main']['temp_max'],
        'description': current_data['weather'][0]['description'],
        'icon': current_data['weather'][0]['icon'],
        'rain_last_hour': rain_last_hour,
        'rain_forecast': rain_forecast,
        'rain_probability': rain_probability,
        'timestamp': datetime.now(current_app.config['TIMEZONE']).isoformat()
    }

def get_weather() -> Optional[JsonDict]:
    """
    Get weather data with caching.
    This is the main function that should be called by other parts of the application.
    
    Returns:
        Optional[dict]: Weather data or None if unavailable
    """
    cache_key = get_cache_key()
    return fetch_weather_data(cache_key)

def get_weather_icon_url(icon_code: str) -> str:
    """
    Generate the URL for a weather icon.
    
    Args:
        icon_code: OpenWeatherMap icon code
        
    Returns:
        str: Complete URL for the weather icon
    """
    return f"https://openweathermap.org/img/wn/{icon_code}.png"

# Template filters for weather data
def register_weather_filters(app):
    """Register Jinja2 filters for weather data formatting."""
    
    @app.template_filter('temp')
    def format_temperature(value: float) -> str:
        """Format temperature with 1 decimal place."""
        return f"{value:.1f}°C"
    
    @app.template_filter('rainfall')
    def format_rainfall(value: float) -> str:
        """Format rainfall in mm."""
        return f"{value:.1f}mm"
    
    @app.template_filter('probability')
    def format_probability(value: float) -> str:
        """Format probability as percentage."""
        return f"{value}%"