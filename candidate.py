from qgis.core import QgsGeometry, QgsProject, QgsCoordinateReferenceSystem, QgsCoordinateTransform

class Candidate:
    def __init__(self, feature, buffer_distance, feedback=None):
        """Initialize the candidate with its feature and buffer."""
        self.feature = feature
        self.feedback = feedback
        
        # Store the ID immediately for consistent access
        self.id = feature.id()  # Use native feature ID
        
        # Check all possible ID field variations
        if 'Id' in feature.fields().names():
            self.field_id = feature['Id']
        elif 'ID' in feature.fields().names():
            self.field_id = feature['ID']
        elif 'id' in feature.fields().names():
            self.field_id = feature['id']
        else:
            self.field_id = self.id
            
        # Log ID assignment for debugging
        if self.feedback:
            self.feedback.pushInfo(f"Initializing candidate with ID: {self.id} (field ID: {self.field_id})")
        
        self.buffer = self.create_buffer(buffer_distance)
        
        # Initialize other attributes
        self.infrastructures = {}
        self.census_data = {}
        self.census_scores = {}
        self.critical_zones = {}
        self.final_score = 0
        self.total_census_score = 0
        self.total_infra_score = 0
        self.total_zone_score = 0
        
        # Initialize outage cost tracking
        self.outage_costs = {}
        self.total_outage_cost_savings = 0
        
    def create_buffer(self, buffer_distance):
        # Log buffer creation information
        if self.feedback:
            feature_id = self.feature['id'] if 'id' in self.feature.fields().names() else 'unknown'
            self.feedback.pushInfo(f"Creating buffer for candidate {self.field_id} with distance {buffer_distance:.2f} meters")
            
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
                'weighted_score': 0,
                'outage_costs': []  # Add a list to track outage costs for this infra type
            }
        self.infrastructures[infra_name]['count'] = count
    
    def add_infrastructure_outage_cost(self, infra_name, outage_cost):
        """Add outage cost for a specific infrastructure item."""
        if infra_name not in self.outage_costs:
            self.outage_costs[infra_name] = []
            
        if outage_cost is not None and outage_cost != "NULL":
            try:
                cost = float(outage_cost)
                self.outage_costs[infra_name].append(cost)
                
                # Also store in infrastructure dict for consistency
                if infra_name not in self.infrastructures:
                    self.update_infrastructure_count(infra_name)
                if 'outage_costs' not in self.infrastructures[infra_name]:
                    self.infrastructures[infra_name]['outage_costs'] = []
                    
                self.infrastructures[infra_name]['outage_costs'].append(cost)
                
                if self.feedback:
                    self.feedback.pushInfo(f"Added outage cost {cost} for {infra_name}")
            except (ValueError, TypeError):
                if self.feedback:
                    self.feedback.pushInfo(f"Invalid outage cost value: {outage_cost}")
    
    def calculate_total_outage_cost_savings(self):
        """Calculate the total outage cost savings from all infrastructure types."""
        total = 0
        for infra_name, costs in self.outage_costs.items():
            # Only count costs if this infrastructure contributes to the score
            infra_score = self.infrastructures.get(infra_name, {}).get('weighted_score', 0)
            if infra_score > 0:
                total += sum(costs)
        
        self.total_outage_cost_savings = total
        return total
        
    def set_infrastructure_score(self, infra_name, normalized_score, weighted_score=None):
        """
        Set both normalized and weighted scores for an infrastructure type.
        
        Args:
            infra_name (str): Name of the infrastructure
            normalized_score (float): The normalized score (0-1)
            weighted_score (float, optional): The weighted score. If None, only normalized score is updated.
        """
        if infra_name not in self.infrastructures:
            self.infrastructures[infra_name] = {
                'count': 0,
                'raw_score': 0,
                'normalized_score': 0,
                'weighted_score': 0,
                'outage_costs': []  # Initialize outage costs list
            }
        
        self.infrastructures[infra_name]['normalized_score'] = normalized_score
        
        if weighted_score is not None:
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
            
    def set_census_data_score(self, variable, weighted_score):
        """
        Set a weighted normalized score for a census variable.
        In the new unified system, census scores are weighted as part of the total score.
        """
        # Store in both places for backward compatibility during transition
        self.census_data[variable + "_score"] = weighted_score
        self.census_scores[variable] = weighted_score
        
    def set_critical_zone_score(self, zone_type, score):
        """Set score for a critical zone. These are direct modifiers."""
        self.critical_zones[zone_type] = score
        
    def calculate_final_score(self):
        """
        Calculate the final score using the new unified scoring system.
        Infrastructure and census scores use unified weighting,
        while critical zone scores are direct modifiers.
        """
        # Calculate infrastructure score using weighted scores
        infrastructure_score = sum(info.get('weighted_score', 0) 
                                 for info in self.infrastructures.values())
        self.total_infra_score = infrastructure_score
        
        # Sum census data scores (which are already weighted)
        census_score = sum(self.census_scores.values())
        self.total_census_score = census_score
        
        # Sum critical zone scores
        critical_zone_score = sum(self.critical_zones.values())
        self.total_zone_score = critical_zone_score
        
        # Calculate final score: (weighted scores) + (zone modifiers)
        self.final_score = infrastructure_score + census_score + critical_zone_score
        
        return self.final_score
        
    def generate_output_attributes(self):
        # Generate a list of attributes for the output feature
        attributes = [self.feature['id'], self.feature['name']]
        
        # Add infrastructure attributes
        for infra_type, info in self.infrastructures.items():
            attributes.extend([info['count'], info['raw_score'], info['score']])
            
            # Add outage costs if available
            outage_costs = self.outage_costs.get(infra_type, [])
            total_type_cost = sum(outage_costs)
            attributes.append(total_type_cost)
        
        # Add total outage cost savings
        attributes.append(self.calculate_total_outage_cost_savings())
        
        # Add remaining attributes
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
