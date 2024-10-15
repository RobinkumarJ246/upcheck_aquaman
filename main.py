import os
from flask import Flask, request, jsonify
from pymongo import MongoClient
from bson import ObjectId
import requests
from datetime import datetime, timedelta
from typing import Dict, Optional, List
import logging
from dataclasses import dataclass, asdict
import json

app = Flask(__name__)

# MongoDB setup
MONGO_URI = "mongodb+srv://robin246j:RdYG9uPZukPXKuaI@app.zfm1a.mongodb.net/?retryWrites=true&w=majority&appName=App"
client = MongoClient(MONGO_URI)
db = client.aquaculture_db


@dataclass
class WeatherData:
    temperature: float
    condition: str
    wind_speed: float
    precipitation: float
    timestamp: datetime


@dataclass
class PondParameters:
    area: float
    depth: float
    stocking_density: int
    culture_start_date: datetime
    water_color: str
    shrimp_behavior: str
    secchi_disk: float
    ph: float
    location: str


class WeatherAPI:

    def __init__(self, api_key: str):
        self.api_key = api_key

    def get_weather_data(self, location: str) -> Optional[WeatherData]:
        try:
            url = f"http://api.weatherapi.com/v1/current.json?key={self.api_key}&q={location}"
            response = requests.get(url, timeout=10)

            if response.status_code == 200:
                data = response.json()
                return WeatherData(
                    temperature=data['current']['temp_c'],
                    condition=data['current']['condition']['text'],
                    wind_speed=data['current']['wind_kph'],
                    precipitation=data['current']['precip_mm'],
                    timestamp=datetime.now())
            else:
                logging.error(f"Weather API error: {response.status_code}")
                return None
        except Exception as e:
            logging.error(f"Weather API exception: {str(e)}")
            return None


class AquacultureManager:

    def __init__(self):
        self.VALID_INPUTS = {
            'water_color': ['Clear', 'Green', 'Brown', 'Other'],
            'shrimp_behavior': ['Active', 'Lethargic', 'Coming to Surface'],
        }

        self.MEASUREMENT_RANGES = {
            'secchi_disk': (10, 60),  # cm
            'ph': (6.0, 9.0),
            'area': (100, 10000),  # m²
            'depth': (0.8, 2.5),  # m
            'stocking_density': (15, 150)  # shrimp per m²
        }

    def validate_input(self, pond_params: PondParameters) -> List[str]:
        errors = []

        for field, valid_values in self.VALID_INPUTS.items():
            value = getattr(pond_params, field)
            if value not in valid_values:
                errors.append(
                    f"Invalid {field}. Must be one of: {', '.join(valid_values)}"
                )

        numeric_fields = {
            'secchi_disk': pond_params.secchi_disk,
            'ph': pond_params.ph,
            'area': pond_params.area,
            'depth': pond_params.depth,
            'stocking_density': pond_params.stocking_density
        }

        for measure, value in numeric_fields.items():
            min_val, max_val = self.MEASUREMENT_RANGES[measure]
            if not min_val <= value <= max_val:
                errors.append(
                    f"{measure} must be between {min_val} and {max_val}")

        if pond_params.culture_start_date > datetime.now():
            errors.append("Culture start date cannot be in the future")

        return errors

    def analyze_pond(self, pond_params: PondParameters,
                     weather: Optional[WeatherData]) -> Dict:
        days_of_culture = (datetime.now() -
                           pond_params.culture_start_date).days

        growth_prediction = self._predict_growth(pond_params, weather,
                                                 days_of_culture)
        biomass_estimation = self._estimate_biomass(pond_params,
                                                    growth_prediction)
        water_quality = self._assess_water_quality(pond_params)
        carrying_capacity = self._calculate_carrying_capacity(pond_params)
        feeding_recommendation = self._calculate_feed(
            biomass_estimation['estimated_biomass'])

        recommendations = self._generate_recommendations(
            pond_params, weather, water_quality, biomass_estimation,
            carrying_capacity)

        return {
            'days_of_culture': days_of_culture,
            'growth_prediction': growth_prediction,
            'biomass_estimation': biomass_estimation,
            'water_quality': water_quality,
            'carrying_capacity': carrying_capacity,
            'feeding_recommendation': feeding_recommendation,
            'recommendations': recommendations,
            'confidence_score':
            self._calculate_confidence(pond_params, weather)
        }

    def _assess_water_quality(self, pond_params: PondParameters) -> Dict:
        water_quality_status = "Good"
        issues = []

        if not (6.5 <= pond_params.ph <= 8.5):
            water_quality_status = "Poor"
            issues.append("pH out of optimal range")

        if pond_params.secchi_disk < 20:
            water_quality_status = "Poor"
            issues.append("Water transparency is too low")

        return {'status': water_quality_status, 'issues': issues}

    def _predict_growth(self, pond_params: PondParameters,
                        weather: Optional[WeatherData], days: int) -> Dict:
        base_growth = 0.028  # g/day

        density_factor = 1.0
        if pond_params.stocking_density < 50:
            density_factor = 1.1
        elif pond_params.stocking_density > 100:
            density_factor = 0.9

        depth_factor = 1.0
        if pond_params.depth < 1.2:
            depth_factor = 0.9
        elif pond_params.depth > 1.8:
            depth_factor = 0.95

        temp_factor = 1.0
        if weather:
            if weather.temperature < 25:
                temp_factor = 0.8
            elif weather.temperature > 32:
                temp_factor = 0.7

        adjusted_growth = base_growth * density_factor * depth_factor * temp_factor

        return {
            'daily_growth': round(adjusted_growth, 4),
            'weekly_growth': round(adjusted_growth * 7, 4),
            'estimated_size': round(0.002 + (adjusted_growth * days),
                                    4)  # starting from 0.002g PL
        }

    def _estimate_biomass(self, pond_params: PondParameters,
                          growth_prediction: Dict) -> Dict:
        survival_rate = self._estimate_survival_rate(pond_params)
        estimated_population = pond_params.area * pond_params.stocking_density * survival_rate

        return {
            'estimated_population':
            round(estimated_population),
            'survival_rate':
            survival_rate,
            'estimated_biomass':
            (round(estimated_population * growth_prediction['estimated_size'],
                   2)) / 1000
        }

    def _estimate_survival_rate(self, pond_params: PondParameters) -> float:
        days = (datetime.now() - pond_params.culture_start_date).days
        base_survival = 0.85  # 85% base survival

        if pond_params.stocking_density > 100:
            base_survival *= 0.95

        if days > 60:
            base_survival *= 0.98

        return round(base_survival, 2)

    def _calculate_carrying_capacity(self,
                                     pond_params: PondParameters) -> Dict:
        volume = pond_params.area * pond_params.depth
        max_biomass_per_m3 = 0.4  # kg per cubic meter

        return {
            'max_biomass': round(volume * max_biomass_per_m3, 2),
            'volume': round(volume, 2)
        }

    def _calculate_feed(self, estimated_biomass: float) -> Dict:
        daily_feed_percentage = 0.03  # 3% of biomass
        daily_feed = estimated_biomass * daily_feed_percentage

        return {
            'daily_feed_kg':
            round(daily_feed, 2),
            'feeding_schedule': [{
                'time': '06:00',
                'percentage': 15
            }, {
                'time': '09:00',
                'percentage': 15
            }, {
                'time': '12:00',
                'percentage': 15
            }, {
                'time': '15:00',
                'percentage': 15
            }, {
                'time': '18:00',
                'percentage': 20
            }, {
                'time': '21:00',
                'percentage': 20
            }]
        }

    def _generate_recommendations(self, pond_params: PondParameters,
                                  weather: Optional[WeatherData],
                                  water_quality: Dict,
                                  biomass_estimation: Dict,
                                  carrying_capacity: Dict) -> List[Dict]:
        recommendations = []

        if biomass_estimation[
                'estimated_biomass'] > carrying_capacity['max_biomass'] * 0.8:
            recommendations.append({
                'issue': 'Approaching Carrying Capacity',
                'action':
                'Short term: consider partial harvest, increase aeration. Long term: plan water exchange or pond expansion',
                'priority': 'High'
            })

        if water_quality['issues']:
            for issue in water_quality['issues']:
                recommendations.append({
                    'issue': issue,
                    'action': 'Implement water quality management measures',
                    'priority': 'High'
                })

        if weather and weather.temperature > 32:
            recommendations.append({
                'issue': 'High Temperature',
                'action': 'Increase aeration and monitor oxygen levels',
                'priority': 'Medium'
            })

        return recommendations

    def _calculate_confidence(self, pond_params: PondParameters,
                              weather: Optional[WeatherData]) -> int:
        confidence = 100

        if not weather:
            confidence -= 20

        if pond_params.ph < 6.5 or pond_params.ph > 8.8:
            confidence -= 10

        if pond_params.secchi_disk < 15 or pond_params.secchi_disk > 55:
            confidence -= 10

        if pond_params.stocking_density > 120:
            confidence -= 10

        days_of_culture = (datetime.now() -
                           pond_params.culture_start_date).days
        if days_of_culture > 100:
            confidence -= 5

        return max(confidence, 0)


# API endpoint
@app.route('/analyze_pond', methods=['POST'])
def analyze_pond():
    try:
        data = request.json
        weather_api = WeatherAPI("92e43917a3c44f2983a92327241110")
        aquaculture_manager = AquacultureManager()

        # Convert date string to datetime object
        data['culture_start_date'] = datetime.fromisoformat(
            data['culture_start_date'])

        pond_params = PondParameters(**data)

        errors = aquaculture_manager.validate_input(pond_params)
        if errors:
            return jsonify({"errors": errors}), 400

        weather_data = weather_api.get_weather_data(
            data.get('location', 'Ranipet'))

        analysis_result = aquaculture_manager.analyze_pond(
            pond_params, weather_data)

        # Store the analysis result in MongoDB
        result = db.pond_analyses.insert_one({
            "pond_params":
            asdict(pond_params),
            "weather_data":
            asdict(weather_data) if weather_data else None,
            "analysis_result":
            analysis_result,
            "timestamp":
            datetime.now()
        })

        # Add the MongoDB document ID to the response
        analysis_result['_id'] = str(result.inserted_id)

        return jsonify(analysis_result), 200

    except Exception as e:
        logging.error(f"Error in analyze_pond: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route('/', methods=['GET'])
def home():
    try:
        return "Upcheck aquaman home page"

    except Exception as e:
        logging.error(f"Error in request: {str(e)}")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))