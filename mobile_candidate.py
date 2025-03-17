"""
This module defines the Candidate class for mobile energy storage evaluation.
It represents a potential location for mobile energy storage system deployment with all its
attributes and scoring mechanisms as described in methodology section 3.3.
"""

from qgis.core import QgsGeometry, QgsProject, QgsCoordinateReferenceSystem, QgsCoordinateTransform

class Candidate:
    def __init__(self, feature, buffer_distance, feedback=None):
        """
        Initialize the mobile candidate with its feature.
        
        As described in section 3.3.1.1, candidates for mobile energy storage represent 
        geographical locations under consideration for mobile units to be stationed or areas
        frequently visited for deployment.
        
        Note that mobile candidates don't use a buffer as in the static model, since they
        operate within a shared coverage area (section 3.3.2.2).
        
        Args:
            feature: QgsFeature representing the candidate location
            buffer_distance: Not used for mobile candidates (kept for API compatibility)
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
            self.feedback.pushInfo(f"Initializing mobile candidate with ID: {self.id} (field ID: {self.field_id})")
        
        # Mobile candidates don't use a buffer - they operate within a shared coverage area
        # as described in section 3.3.2.2
        self.buffer = None
        
        # Initialize score tracking with total_duration for mobile model
        # For the mobile model, we track travel times instead of distances
        # as described in section 3.3.2.1 and 3.3.4.2.1
        self.infrastructures = {}  # Will store count, raw_score, final_score, and total_duration
        self.census_data = {}      # Raw census data values
        self.census_scores = {}    # Normalized and weighted census scores
        self.critical_zones = {}   # Critical zone direct modifiers
        self.final_score = 0       # Final combined score
        self.total_census_score = 0  # Total census component
        self.total_infra_score = 0   # Total infrastructure component
        self.total_zone_score = 0    # Total zone modifiers
        
    def update_infrastructure_count(self, infra_name, count=0):
        """
        Update the count of infrastructure items of a given type.
        
        As described in section 3.3.4.2.1, traveling time to critical infrastructure
        is a key scoring factor for mobile ESS. This method tracks how many infrastructure
        items of each type are within the coverage area.
        
        Args:
            infra_name: Name of the infrastructure type
            count: Number of infrastructure items found
        """
        if infra_name not in self.infrastructures:
            self.infrastructures[infra_name] = {
                'count': 0,
                'raw_score': 0,
                'final_score': 0,
                'total_duration': 0
            }
        self.infrastructures[infra_name]['count'] = count

    def set_infrastructure_raw_score(self, infra_name, raw_score):
        """
        Set the raw (unweighted) score for an infrastructure type.
        
        For the mobile model, the raw score is based on the formula from section 3.3.4.2.1:
        Sinfra = ∑(1/ETA)
        
        However, in the implementation, we first collect all travel durations and then 
        convert them to scores during normalization.
        
        Args:
            infra_name: Name of the infrastructure type
            raw_score: The raw unweighted score (sum of travel times)
        """
        if infra_name not in self.infrastructures:
            self.infrastructures[infra_name] = {
                'count': 0,
                'raw_score': 0,
                'final_score': 0,
                'total_duration': 0
            }
        self.infrastructures[infra_name]['raw_score'] = raw_score

    def set_infrastructure_score(self, infra_name, final_score, weight=1.0):
        """
        Set the final (normalized and weighted) score for an infrastructure type.
        
        Implements the normalization and weighting as described in section 3.3.4.2.1:
        - Normalized score from min-max normalization
        - Weighted score after applying infrastructure weight
        
        Args:
            infra_name: Name of the infrastructure type
            final_score: The weighted normalized score
            weight: The weight applied (for information only)
        """
        if infra_name not in self.infrastructures:
            self.infrastructures[infra_name] = {
                'count': 0,
                'raw_score': 0,
                'final_score': 0,
                'total_duration': 0
            }
        
        # Store final score (already normalized and weighted)
        self.infrastructures[infra_name]['final_score'] = final_score
        
    def set_census_data_score(self, variable, weighted_score):
        """
        Set a weighted normalized score for a census variable.
        
        As described in section 3.3.4.2.2, demographic considerations follow
        the same approach as in the static model, with an emphasis on areas
        with significant population movement or temporary energy demand spikes.
        
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
        
        As described in section 3.3.4.2.2, critical zones maintain the same
        scoring approach as the static model. These are direct modifiers to
        the final score.
        
        Args:
            zone_type: Name of the critical zone
            score: Direct score modifier (can be positive or negative)
        """
        self.critical_zones[zone_type] = score
        
    def calculate_final_score(self):
        """
        Calculate the final score based on all components.
        
        Follows the scoring algorithm in section 3.3.4.3, combining
        infrastructure scores, census scores, and critical zone modifiers.
        
        Returns:
            float: The final calculated score
        """
        infra_score = self.total_infra_score
        census_score = self.calculate_total_census_score()
        self.total_zone_score = sum(self.critical_zones.values())  # Ensure we store the total zone score
        
        # Final score is the sum of infrastructure score, census score, and critical zone scores
        # Similar to the static model's approach, but with a different calculation for infrastructure scores
        self.final_score = infra_score + census_score + self.total_zone_score
        return self.final_score
        
    def generate_output_attributes(self):
        """
        Generate list of attributes for the output feature.
        
        This creates the attributes structure for the output shapefile.
        Note that unlike the static model, mobile model doesn't include
        outage cost savings (as mentioned in section 3.3.4.3).
        
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
        
        # Start attributes list with ID and name
        attributes = [feature_id, feature_name]
        
        # Add infrastructure scores
        for infra_name, data in self.infrastructures.items():
            attributes.append(data.get('count', 0))
            attributes.append(data.get('raw_score', 0))
            attributes.append(data.get('final_score', 0))
        
        # Add total infrastructure score
        attributes.append(self.total_infra_score)
        
        # Add census data and scores
        for var_name, value in self.census_data.items():
            if not var_name.endswith('_score'):  # Only add raw census values
                attributes.append(value)
                score = self.census_scores.get(var_name, 0)
                attributes.append(score)
        
        # Calculate total census (demographic) score
        total_census = self.calculate_total_census_score()
        
        # Add critical zone scores
        for zone_name, score in self.critical_zones.items():
            attributes.append(score)
        
        # Add total zone score
        attributes.append(self.total_zone_score)
        
        # Add total census (demographic) score
        attributes.append(total_census)
        
        # Add final score
        attributes.append(self.final_score)
        
        return attributes
        
    def set_census_data(self, variable_name, value):
        """
        Set a census data value for a given variable.
        
        As described in section 3.3.1.3, census data is used to understand
        and predict where mobile energy storage services might be needed most.
        
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
        
    def set_infrastructure_total_duration(self, infra_name, total_duration):
        """
        Set the total travel duration for an infrastructure type.
        
        This is specific to the mobile model, tracking the key metric
        of travel time as described in section 3.3.2.1 (Estimating Traveling Time).
        
        Args:
            infra_name: Name of the infrastructure type
            total_duration: Total travel duration in seconds
        """
        if infra_name not in self.infrastructures:
            self.infrastructures[infra_name] = {
                'count': 0,
                'raw_score': 0,
                'final_score': 0,
                'total_duration': 0
            }
        self.infrastructures[infra_name]['total_duration'] = total_duration
