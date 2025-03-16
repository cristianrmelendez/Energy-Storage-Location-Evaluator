import requests
import numpy as np
from qgis.core import QgsCoordinateTransform, QgsProject, QgsPointXY, QgsCoordinateReferenceSystem

class RoadNetworkAnalyzer:
    def __init__(self, osrm_base_url="http://127.0.0.1:5001"):
        """
        Initializes the RoadNetworkAnalyzer with the URL of the OSRM instance.
        """
        self.osrm_base_url = osrm_base_url

    def get_route_info(self, start_lon, start_lat, end_lon, end_lat):
        """
        Fetches route, distance in meters, and duration in seconds between two points
        using the road network from the OSRM instance.
        """
        location = f"{start_lon},{start_lat};{end_lon},{end_lat}"
        r = requests.get(f"{self.osrm_base_url}/route/v1/driving/{location}")

        if r.status_code != 200:
            raise Exception(f"OSRM request failed with status code {r.status_code}")

        res = r.json()
        distance = res['routes'][0]['distance']
        duration = res['routes'][0]['duration']

        return {'distance': distance, 'duration': duration}

    def transform_coordinates(self, x, y):
        source_crs = QgsProject.instance().crs()  # Get the current project CRS
        dest_crs = QgsCoordinateReferenceSystem('EPSG:4326')  # WGS 84
        transform = QgsCoordinateTransform(source_crs, dest_crs, QgsProject.instance())
        pt = transform.transform(QgsPointXY(x, y))
        return pt.x(), pt.y()

    def calculate_road_distance(self, start_x, start_y, end_x, end_y):
        """
        Calculates the road distance in meters between two points using OSRM.
        The coordinates are transformed from the layer's CRS to WGS 84 (EPSG:4326).
        
        Returns:
            float: Road distance in meters
        """
        # Transform coordinates from the layer's CRS to WGS 84
        start_lon, start_lat = self.transform_coordinates(start_x, start_y)
        end_lon, end_lat = self.transform_coordinates(end_x, end_y)
        
        # Get route information using OSRM
        try:
            route_info = self.get_route_info(start_lon, start_lat, end_lon, end_lat)
            return route_info['distance']  # Distance in meters
        except Exception as e:
            # If OSRM fails, return a large number to indicate failure
            # This will effectively give a score of 0 for this connection
            print(f"Error calculating road distance: {str(e)}")
            return float('inf')

    def calculate_eta(self, start_lon, start_lat, end_lon, end_lat):
        """
        Calculates the Estimated Time of Arrival (ETA) using the OSRM backend.
        """
        route_info = self.get_route_info(start_lon, start_lat, end_lon, end_lat)
        return route_info['duration']  # Duration in seconds

    def haversine_distance(self, lon1, lat1, lon2, lat2):
        """
        Calculate the great circle distance between two points 
        on the earth (specified in decimal degrees).
        Returns distance in kilometers.
        """
        r = 6371  # Radius of Earth in kilometers
        phi1 = np.radians(lat1)
        phi2 = np.radians(lat2)
        delta_phi = np.radians(lat2 - lat1)
        delta_lambda = np.radians(lon2 - lon1)
        a = np.sin(delta_phi / 2)**2 + np.cos(phi1) * np.cos(phi2) * np.sin(delta_lambda / 2)**2
        res = r * (2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a)))
        return np.round(res * 1000, 2)  # Convert to meters for consistency with road distance
