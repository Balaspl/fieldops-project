from typing import List, Dict, Any
from .ola_map_client import OlaMapsClient

class DistanceScoringService:
    async def calculate_distance_score(self, job_loc: dict, tech_locs: List[dict], redis_client) -> List[dict]:
        gmaps_client = OlaMapsClient(redis_client)
        results = []
        
        for t in tech_locs:
            tech_loc = {"lat": t.get("lat", 0), "lng": t.get("lng", 0)}
            
            # Fetch distance in km (uses cache, fallback, circuit breaker internally)
            distance_km = await gmaps_client.get_distance(job_loc, tech_loc)
            
            # Distance scoring formula: 0km = 100, 50km = 50, 100km = 0, >100km = 0
            if distance_km > 100:
                score = 0.0
            else:
                score = round(100 - (distance_km / 100 * 100), 2)
                
            results.append({
                "id": t["id"],
                "score": score,
                "distance_km": round(distance_km, 2)
            })
            
        return results
