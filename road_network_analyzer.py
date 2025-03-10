import requests
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
