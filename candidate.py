from qgis.core import QgsGeometry, QgsProject, QgsCoordinateReferenceSystem, QgsCoordinateTransform

class Candidate:
    def __init__(self, feature, buffer_distance, feedback=None):
        self.feature = feature
        self.feedback = feedback
        self.buffer = self.create_buffer(buffer_distance)
        # Initialize infrastructure dictionary with all required score types
        self.infrastructures = {}  # Format: {'infra_name': {'count': 0, 'raw_score': 0, 'normalized_score': 0, 'weighted_score': 0}}
        self.census_data = {}
        self.census_scores = {}
        self.critical_zones = {}
        self.final_score = 0
        self.total_census_score = 0
        self.total_infra_score = 0
        self.total_zone_score = 0
        
    def create_buffer(self, buffer_distance):
        # Log buffer creation information
        if self.feedback:
            feature_id = self.feature['id'] if 'id' in self.feature.fields().names() else 'unknown'
            self.feedback.pushInfo(f"Creating buffer for candidate {feature_id} with distance {buffer_distance:.2f} meters")
            
        # Get the feature's geometry
        geom = self.feature.geometry()
        
        if not geom.isGeosValid():
            if self.feedback:
                self.feedback.pushInfo("Invalid input geometry, attempting to fix...")
            geom = geom.makeValid()
        
        # Get centroid for UTM zone calculation
        centroid = geom.centroid().asPoint()
        
        # Calculate UTM zone for the location (Puerto Rico is around -66° longitude)
        # Puerto Rico falls in UTM zone 19N
        utm_crs = QgsCoordinateReferenceSystem('EPSG:32161')  # Puerto Rico State Plane (meters)
        
        if self.feedback:
            self.feedback.pushInfo(f"Using projected CRS: {utm_crs.description()}")
        
        # Create transform context
        source_crs = QgsCoordinateReferenceSystem('EPSG:4326')  # WGS84
        transform_to_utm = QgsCoordinateTransform(source_crs, utm_crs, QgsProject.instance())
        transform_to_wgs84 = QgsCoordinateTransform(utm_crs, source_crs, QgsProject.instance())
        
        # Transform geometry to UTM
        geom_utm = QgsGeometry(geom)
        geom_utm.transform(transform_to_utm)
        
        if self.feedback:
            self.feedback.pushInfo(f"Geometry area before buffer (UTM): {geom_utm.area():.2f} sq meters")
        
        # Create buffer in UTM coordinates (which are in meters)
        buffer_geom = geom_utm.buffer(buffer_distance, segments=36)  # More segments for smoother buffer
        
        if self.feedback:
            self.feedback.pushInfo(f"Buffer area (UTM): {buffer_geom.area():.2f} sq meters")
        
        # Transform buffer back to WGS84
        buffer_geom.transform(transform_to_wgs84)
        
        if self.feedback:
            self.feedback.pushInfo(f"Final buffer area (WGS84): {buffer_geom.area():.2f} sq meters")
            self.feedback.pushInfo(f"Buffer is valid: {buffer_geom.isGeosValid()}")
        
        return buffer_geom
        
    def update_infrastructure_count(self, infra_name, count=0):
        """Update the count of infrastructure items of a given type."""
        if infra_name not in self.infrastructures:
            self.infrastructures[infra_name] = {
                'count': 0,
                'raw_score': 0,
                'normalized_score': 0,
                'weighted_score': 0
            }
        self.infrastructures[infra_name]['count'] = count
        
    def set_infrastructure_score(self, infra_name, normalized_score, weight=None):
        """Set the normalized and weighted scores for an infrastructure type.
        
        Args:
            infra_name (str): Name of the infrastructure
            normalized_score (float): The normalized score (0-1)
            weight (float, optional): The weight to apply. If None, only normalized score is updated.
        """
        if infra_name not in self.infrastructures:
            self.infrastructures[infra_name] = {
                'count': 0,
                'raw_score': 0,
                'normalized_score': 0,
                'weighted_score': 0
            }
        
        # Set normalized score
        self.infrastructures[infra_name]['normalized_score'] = normalized_score
        
        # Calculate and set weighted score if weight is provided
        if weight is not None:
            weighted_score = normalized_score * weight
            self.infrastructures[infra_name]['weighted_score'] = weighted_score
        
    def set_infrastructure_raw_score(self, infra_name, raw_score):
        """Set the raw (unweighted) score for an infrastructure type."""
        if infra_name not in self.infrastructures:
            self.infrastructures[infra_name] = {
                'count': 0,
                'raw_score': 0,
                'normalized_score': 0,
                'weighted_score': 0
            }
        self.infrastructures[infra_name]['raw_score'] = raw_score
            
    def set_census_data_score(self, variable, score):
        """Set a normalized score for a census variable"""
        # Store in both places for backward compatibility during transition
        self.census_data[variable + "_score"] = score
        self.census_scores[variable] = score
        
    def set_critical_zone_score(self, zone_type, score):
        """Set score for a critical zone"""
        self.critical_zones[zone_type] = score
        
    def calculate_final_score(self):
        """Calculate the final score combining all components"""
        # Calculate infrastructure score using weighted scores
        infrastructure_score = sum(info.get('weighted_score', 0) for info in self.infrastructures.values())
        self.total_infra_score = infrastructure_score
        
        # Sum census data scores
        census_score = sum(self.census_scores.values())
        self.total_census_score = census_score
        
        # Sum critical zone scores
        critical_zone_score = sum(self.critical_zones.values())
        self.total_zone_score = critical_zone_score
        
        # Calculate final score
        self.final_score = infrastructure_score + census_score + critical_zone_score
        
        return self.final_score
        
    def generate_output_attributes(self):
        # Generate a list of attributes for the output feature
        attributes = [self.feature['id'], self.feature['name']]
        for infra_type, info in self.infrastructures.items():
            attributes.extend([info['count'], info['raw_score'], info['score']])
        for variable, value in self.census_data.items():
            if not variable.endswith("_score"):  # Only include raw values
                attributes.append(value)
                score = self.census_scores.get(variable, 0)
                attributes.append(score)
        for zone_type, score in self.critical_zones.items():
            attributes.append(score)
        attributes.append(self.final_score)
        return attributes
        
    def set_census_data(self, variable_name, value):
        """Set a census data value for a given variable"""
        self.census_data[variable_name] = value

    def calculate_total_census_score(self):
        """Calculate the total census score as sum of all normalized scores"""
        if self.census_scores:
            self.total_census_score = sum(self.census_scores.values())
        else:
            self.total_census_score = 0
        return self.total_census_score
        
    def get_census_data(self, variable_name):
        """Get raw census data for a variable"""
        return self.census_data.get(variable_name, 0)
        
    def get_census_score(self, variable_name):
        """Get normalized score for a census variable"""
        return self.census_scores.get(variable_name, 0)
