"""
This module defines the Candidate class for static energy storage evaluation.
It represents a potential location for energy storage system deployment with all its
attributes and scoring mechanisms as described in methodology section 3.2.
"""

from qgis.core import QgsGeometry, QgsProject, QgsCoordinateReferenceSystem, QgsCoordinateTransform

class Candidate:
    def __init__(self, feature, buffer_distance, feedback=None):
        """
        Initialize the candidate with its feature and buffer.
        
        As described in section 3.2.1.1, candidates represent geographical locations
        under consideration for the deployment of Energy Storage Systems (ESS).
        
        Args:
            feature: QgsFeature representing the candidate location
            buffer_distance: Distance in kilometers for buffer analysis (section 3.2.2.2)
            feedback: Optional feedback mechanism for logging
        """
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
        
        # Create buffer as the service area around the candidate (section 3.2.2.2)
        self.buffer = self.create_buffer(buffer_distance)
        
        # Initialize data structures for scoring categories (section 3.2.4.2)
        self.infrastructures = {}    # Critical Infrastructure proximity scores
        self.census_data = {}        # Raw census data values
        self.census_scores = {}      # Normalized and weighted census scores
        self.critical_zones = {}     # Critical zone direct modifiers
        self.final_score = 0         # Final combined score
        self.total_census_score = 0  # Total census component
        self.total_infra_score = 0   # Total infrastructure component
        self.total_zone_score = 0    # Total zone modifiers
        
        # Initialize outage cost tracking for economic analysis (section 3.2.4.3)
        self.outage_costs = {}
        self.total_outage_cost_savings = 0
        
    def create_buffer(self, buffer_distance):
        """
        Create a circular buffer (service area) around the candidate location.
        
        As described in section 3.2.2.2 (Buffer Analysis), this creates a buffer zone
        that represents the candidate's service area. All infrastructures within this
        buffer are considered as potential customers (loads) for the candidate.
        
        Args:
            buffer_distance: Distance in kilometers for the buffer radius
            
        Returns:
            QgsGeometry: Buffer geometry in WGS84 coordinates
        """
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
        """
        Update the count of infrastructure items of a given type.
        
        As described in section 3.2.4.2.1, proximity to critical infrastructure
        is a key scoring factor. This method tracks how many infrastructure items
        of each type are within the candidate's buffer zone.
        
        Args:
            infra_name: Name of the infrastructure type
            count: Number of infrastructure items found
        """
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
        """
        Add outage cost for a specific infrastructure item.
        
        As described in section 3.2.4.3 under "Outage Cost Savings", this tracks
        the financial losses incurred per hour of service disruption, providing
        an economic metric for evaluating candidates.
        
        Args:
            infra_name: Name of the infrastructure type
            outage_cost: Cost per hour of outage for this infrastructure
        """
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
        """
        Calculate the total outage cost savings from all infrastructure types.
        
        As specified in section 3.2.4.3, the Outage Cost Savings is reported separately
        from the overall site suitability score, allowing for independent economic analysis.
        
        Returns:
            float: Total potential outage cost savings
        """
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
        
        Implements the normalization and weighting as described in section 3.2.4.3:
        - Normalized score (0-1) from min-max normalization
        - Weighted score after applying the infrastructure weight
        
        Args:
            infra_name: Name of the infrastructure type
            normalized_score: The normalized score (0-1)
            weighted_score: The weighted score (normalized * weight)
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
        """
        Set the raw (unweighted) score for an infrastructure type.
        
        This sets the raw score calculated using the formula from section 3.2.4.3:
        Sinfra = ∑(Dbuffer - Dactual)
        
        Args:
            infra_name: Name of the infrastructure type
            raw_score: The raw unweighted score
        """
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
        
        As described in section 3.2.4.2.2 (Demographic Considerations), census data
        provides insights into population characteristics that influence ESS utility.
        
        Args:
            variable: Census variable name
            weighted_score: The weighted normalized score for this census variable
        """
        # Store in both places for backward compatibility during transition
        self.census_data[variable + "_score"] = weighted_score
        self.census_scores[variable] = weighted_score
        
    def set_critical_zone_score(self, zone_type, score):
        """
        Set score for a critical zone.
        
        As described in section 3.2.4.2.3 (Location within Critical Zones), these
        are direct modifiers that can be positive or negative based on whether the
        zone is favorable or unfavorable for ESS deployment.
        
        Args:
            zone_type: Name of the critical zone
            score: Direct score modifier (can be positive or negative)
        """
        self.critical_zones[zone_type] = score
        
    def calculate_final_score(self):
        """
        Calculate the final score using the unified scoring system from section 3.2.4.3.
        
        The final score is calculated as:
        Sfinal-total = Sinfra+census-final + Scritical-zone-score
        
        Returns:
            float: The final score
        """
        # Calculate infrastructure score using weighted scores
        infrastructure_score = sum(info.get('weighted_score', 0) 
                                 for info in self.infrastructures.values())
        self.total_infra_score = infrastructure_score
        
        # Sum census data scores (which are already weighted)
        census_score = sum(self.census_scores.values())
        self.total_census_score = census_score
        
        # Sum critical zone scores (direct modifiers)
        critical_zone_score = sum(self.critical_zones.values())
        self.total_zone_score = critical_zone_score
        
        # Calculate final score: (weighted scores) + (zone modifiers)
        self.final_score = infrastructure_score + census_score + critical_zone_score
        
        return self.final_score
        
    def generate_output_attributes(self):
        """
        Generate a list of attributes for the output feature.
        
        This creates the attributes structure for the output shapefile
        according to the specifications in section 3.2.
        
        Returns:
            list: Attributes for the output feature
        """
        # Get proper ID for the feature
        feature_id = self.id  # Default to internal ID
        
        # Try different ID field variations
        if 'Id' in self.feature.fields().names():
            feature_id = self.feature['Id']
            if self.feedback:
                self.feedback.pushInfo(f"Using 'Id' field value: {feature_id}")
        elif 'ID' in self.feature.fields().names():
            feature_id = self.feature['ID'] 
            if self.feedback:
                self.feedback.pushInfo(f"Using 'ID' field value: {feature_id}")
        elif 'id' in self.feature.fields().names():
            feature_id = self.feature['id']
            if self.feedback:
                self.feedback.pushInfo(f"Using 'id' field value: {feature_id}")
        else:
            if self.feedback:
                self.feedback.pushInfo(f"No Id field found, using internal ID: {feature_id}")
        
        # Get proper Name for the feature
        feature_name = None
        
        # Try different Name field variations
        if 'Name' in self.feature.fields().names():
            feature_name = str(self.feature['Name'])
            if self.feedback:
                self.feedback.pushInfo(f"Using 'Name' field value: {feature_name}")
        elif 'name' in self.feature.fields().names():
            feature_name = str(self.feature['name'])
            if self.feedback:
                self.feedback.pushInfo(f"Using 'name' field value: {feature_name}")
        elif 'NAME' in self.feature.fields().names():
            feature_name = str(self.feature['NAME'])
            if self.feedback:
                self.feedback.pushInfo(f"Using 'NAME' field value: {feature_name}")
        
        # If no name was found, use Id as the name
        if not feature_name:
            feature_name = f'Candidate {feature_id}'
            if self.feedback:
                self.feedback.pushInfo(f"No Name field found, using ID as name: {feature_name}")
        
        # Start building attributes list with ID and name
        attributes = [feature_id, feature_name]
        
        # Add infrastructure attributes
        for infra_type, info in self.infrastructures.items():
            attributes.append(info.get('count', 0))
            attributes.append(info.get('raw_score', 0))
            attributes.append(info.get('weighted_score', 0))
            
            # Add outage costs if available
            outage_costs = self.outage_costs.get(infra_type, [])
            total_type_cost = sum(outage_costs)
            attributes.append(total_type_cost)
        
        # Add total infrastructure score
        attributes.append(self.total_infra_score)
        
        # Add total outage cost savings (independent economic metric)
        attributes.append(self.calculate_total_outage_cost_savings())
        
        # Add census data values and scores
        for variable, value in self.census_data.items():
            if not variable.endswith("_score"):  # Only include raw values
                attributes.append(value)
                score = self.census_scores.get(variable, 0)
                attributes.append(score)
                
        # Add zone scores
        for zone_type, score in self.critical_zones.items():
            attributes.append(score)
            
        # Add total zone score
        attributes.append(self.total_zone_score)
        
        # Add total demographic/census score
        attributes.append(self.total_census_score)
        
        # Add final score - ensure this is not NULL
        if hasattr(self, 'final_score') and self.final_score is not None:
            attributes.append(self.final_score)
            if self.feedback:
                self.feedback.pushInfo(f"Adding final score: {self.final_score}")
        else:
            # Calculate final score if not already calculated
            final_score = self.calculate_final_score()
            attributes.append(final_score)
            if self.feedback:
                self.feedback.pushInfo(f"Adding newly calculated final score: {final_score}")
        
        return attributes
        
    def set_census_data(self, variable_name, value):
        """
        Set a census data value for a given variable.
        
        As described in section 3.2.1.3 (Census Data), this stores raw census data
        for each candidate location.
        
        Args:
            variable_name: Name of the census variable
            value: The raw value
        """
        self.census_data[variable_name] = value

    def calculate_total_census_score(self):
        """
        Calculate the total census score as sum of all normalized scores.
        
        Returns:
            float: Total census score component
        """
        if self.census_scores:
            self.total_census_score = sum(self.census_scores.values())
        else:
            self.total_census_score = 0
        return self.total_census_score
        
    def get_census_data(self, variable_name):
        """
        Get raw census data for a variable.
        
        Args:
            variable_name: Name of the census variable
            
        Returns:
            float: The raw census value or 0 if not found
        """
        return self.census_data.get(variable_name, 0)
        
    def get_census_score(self, variable_name):
        """
        Get normalized score for a census variable.
        
        Args:
            variable_name: Name of the census variable
            
        Returns:
            float: The normalized score or 0 if not found
        """
        return self.census_scores.get(variable_name, 0)