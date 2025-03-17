"""
This module implements the static energy storage evaluation model. It handles all the logic
for evaluating potential sites for static energy storage facilities as described in the
methodology section 3.2 (Static Energy Storage Systems Model).
"""

from qgis.core import (QgsProcessingException, QgsFeature, QgsFields, QgsField,
                      QgsWkbTypes, QgsFeatureSink, QgsPointXY, QgsProject,
                      QgsCoordinateTransform, QgsCoordinateReferenceSystem,
                      QgsGeometry, QgsRectangle)
from qgis.PyQt.QtCore import QVariant
from .road_network_analyzer import RoadNetworkAnalyzer

class StaticEnergyStorageEvaluator:
    def __init__(self, feedback=None):
        """Initialize the evaluator with optional feedback mechanism."""
        self.feedback = feedback
        self.road_analyzer = RoadNetworkAnalyzer()

    def log(self, message):
        """Log a message if feedback is available."""
        if self.feedback:
            self.feedback.pushInfo(message)

    def validate_weights(self, infra_weights, census_weights, infra_count, census_count):
        """
        Validate that all weights (infrastructure and census) sum to 1.0 when combined
        and match their respective counts.
        
        As described in section 3.2.4.4 (Customizing Scoring Parameters), the sum of
        all weights must equal 1.0 to ensure a balanced evaluation.
        
        Args:
            infra_weights (str): Comma-separated infrastructure weights
            census_weights (str): Comma-separated census weights
            infra_count (int): Expected number of infrastructure weights
            census_count (int): Expected number of census weights
            
        Returns:
            tuple: Normalized infrastructure and census weights
            
        Raises:
            QgsProcessingException: If weights are invalid
        """
        try:
            infra_weights = [float(w) for w in infra_weights.split(',')]
            census_weights = [float(w) for w in census_weights.split(',')]
        except ValueError:
            raise QgsProcessingException("All weights must be numeric values separated by commas.")

        # Check counts match
        if len(infra_weights) != infra_count:
            raise QgsProcessingException(
                f"Number of infrastructure weights ({len(infra_weights)}) "
                f"does not match number of infrastructure layers ({infra_count})"
            )
        
        if len(census_weights) != census_count:
            raise QgsProcessingException(
                f"Number of census weights ({len(census_weights)}) "
                f"does not match number of census variables ({census_count})"
            )

        # All weights must sum to 1.0
        total_sum = sum(infra_weights) + sum(census_weights)
        if not 0.999 <= total_sum <= 1.001:
            raise QgsProcessingException(
                f"Total of all weights ({total_sum}) must equal 1.0. "
                "This includes both infrastructure and census weights."
            )

        # Normalize weights to exactly 1.0 if needed
        weight_sum = sum(infra_weights) + sum(census_weights)
        if weight_sum != 1.0:
            factor = 1.0 / weight_sum
            infra_weights = [w * factor for w in infra_weights]
            census_weights = [w * factor for w in census_weights]

        return infra_weights, census_weights

    def evaluate_critical_zones(self, candidates, zone_layers, zone_scores):
        """
        Evaluate candidates against critical zones and apply scores.
        
        As described in section 3.2.4.2.3 (Location within Critical Zones), critical zone
        scores are direct modifiers to the final score and not part of the weighted system.
        These can be positive or negative values depending on whether the zone is favorable
        or unfavorable for ESS deployment.
        
        Args:
            candidates: List of Candidate objects
            zone_layers: List of zone layers
            zone_scores: List of scores corresponding to zone layers
        """
        for candidate in candidates:
            candidate_id = candidate.feature.id() if hasattr(candidate.feature, 'id') else 'unknown'
            self.log(f"Evaluating critical zones for candidate {candidate_id}")
            
            for i, zone_layer in enumerate(zone_layers):
                zone_name = zone_layer.name()
                zone_score = zone_scores[i]
                
                for zone_feature in zone_layer.getFeatures():
                    if zone_feature.geometry().intersects(candidate.feature.geometry()):
                        # Apply the zone score as a direct modifier as per methodology section 3.2.4.3
                        candidate.set_critical_zone_score(zone_name, zone_score)
                        self.log(f"Candidate intersects with {zone_name}, applying score: {zone_score}")
                        break
                    else:
                        candidate.set_critical_zone_score(zone_name, 0)

    def evaluate_infrastructure(self, candidate, infra_layers, infra_weights, buffer_distance, distance_method):
        """
        Evaluate a candidate against infrastructure layers using the specified distance method.
        Also gather outage costs for infrastructure features within the buffer.
        
        As described in section 3.2.4.2.1 (Proximity to Critical Infrastructure), this calculates
        a score based on the proximity of the candidate to critical infrastructures.
        
        The buffer analysis (section 3.2.2.2) defines the service area around each candidate.
        The score formula follows Sinfra = ∑(Dbuffer - Dactual) as described in section 3.2.4.3.
        
        Args:
            candidate: Candidate object to evaluate
            infra_layers: List of infrastructure layers
            infra_weights: List of weights for each infrastructure layer
            buffer_distance: Distance in kilometers for buffer analysis
            distance_method: Method for distance calculation (0=Road, 1=Haversine)
        """
        for i, layer in enumerate(infra_layers):
            infra_name = layer.name()
            weight = infra_weights[i]
            
            # Calculate scores based on distances to infrastructure
            total_score = 0
            infra_count = 0
            
            for feature in layer.getFeatures():
                # Only consider infrastructure within the candidate's buffer (service area)
                if feature.geometry().intersects(candidate.buffer):
                    infra_count += 1
                    start_point = candidate.feature.geometry().asPoint()
                    end_point = feature.geometry().asPoint()
                    
                    # Calculate distance based on method selected by user
                    # As described in section 3.2.2.1 (Distance Calculations)
                    if distance_method == 0:  # Road distance through network
                        try:
                            distance = self.road_analyzer.calculate_road_distance(
                                start_point.x(), start_point.y(),
                                end_point.x(), end_point.y()
                            )
                        except Exception as e:
                            self.log(f"Road distance calculation failed: {str(e)}, using Haversine")
                            # Transform coordinates to get lon/lat
                            start_lon, start_lat = self.road_analyzer.transform_coordinates(
                                start_point.x(), start_point.y()
                            )
                            end_lon, end_lat = self.road_analyzer.transform_coordinates(
                                end_point.x(), end_point.y()
                            )
                            distance = self.road_analyzer.haversine_distance(
                                start_lon, start_lat, end_lon, end_lat
                            )
                    else:  # Haversine distance (straight-line)
                        # Transform coordinates to get lon/lat for haversine calculation
                        start_lon, start_lat = self.road_analyzer.transform_coordinates(
                            start_point.x(), start_point.y()
                        )
                        end_lon, end_lat = self.road_analyzer.transform_coordinates(
                            end_point.x(), end_point.y()
                        )
                        distance = self.road_analyzer.haversine_distance(
                            start_lon, start_lat, end_lon, end_lat
                        )
                    
                    # Score formula: buffer_distance - actual_distance
                    # Following the formula Sinfra = ∑(Dbuffer - Dactual) from section 3.2.4.3
                    score = max(0, buffer_distance - distance)
                    
                    # Process outage cost for economic analysis (section 3.2.4.3 - Outage Cost Savings)
                    if score > 0:
                        # Get outage cost if it exists in the feature
                        if 'outage_cos' in feature.fields().names():
                            outage_cost = feature['outage_cos']
                            self.log(f"Found outage_cos in feature: {outage_cost} (contributes to score)")
                            candidate.add_infrastructure_outage_cost(infra_name, outage_cost)
                    
                    total_score += score
            
            # Update candidate with counts and raw scores
            candidate.update_infrastructure_count(infra_name, infra_count)
            candidate.set_infrastructure_raw_score(infra_name, total_score)

    def normalize_and_weight_scores(self, candidates, infra_layers, census_variables, infra_weights, census_weights):
        """
        Normalize and apply weights to infrastructure and census scores.
        
        This implements the normalization and weighting as described in section 3.2.4.3:
        - Using Min-Max Normalization for both infrastructure and census data
        - Applying weights to reflect relative importance
        
        Args:
            candidates: List of candidate objects
            infra_layers: List of infrastructure layers
            census_variables: List of census variable names
            infra_weights: List of weights for infrastructure layers
            census_weights: List of weights for census variables
        """
        # Find global min/max for infrastructure scores
        global_infra_min = float('inf')
        global_infra_max = float('-inf')
        
        for candidate in candidates:
            for infra_name in [layer.name() for layer in infra_layers]:
                score = candidate.infrastructures.get(infra_name, {}).get('raw_score', 0)
                global_infra_min = min(global_infra_min, score)
                global_infra_max = max(global_infra_max, score)
        
        # Find global min/max for census values
        census_ranges = {var: {'min': float('inf'), 'max': float('-inf')} 
                        for var in census_variables}
        
        for candidate in candidates:
            for var in census_variables:
                value = candidate.census_data.get(var, 0)
                census_ranges[var]['min'] = min(census_ranges[var]['min'], value)
                census_ranges[var]['max'] = max(census_ranges[var]['max'], value)
        
        # Apply normalization and weights
        for candidate in candidates:
            # Infrastructure scores - following Min-Max Normalization formula:
            # Sinfra-normalized = (Sinfra - Sinfra-min) / (Sinfra-max - Sinfra-min)
            for i, layer in enumerate(infra_layers):
                infra_name = layer.name()
                raw_score = candidate.infrastructures.get(infra_name, {}).get('raw_score', 0)
                
                # Normalize using Min-Max scaling
                if global_infra_max > global_infra_min:
                    norm_score = (raw_score - global_infra_min) / (global_infra_max - global_infra_min)
                else:
                    norm_score = 1.0 if raw_score > 0 else 0.0
                
                # Apply weight: Sinfra-weighted = Sinfra-normalized × Winfra
                weighted_score = norm_score * infra_weights[i]
                candidate.set_infrastructure_score(infra_name, norm_score, weighted_score)
            
            # Census scores - following same normalization approach
            for i, var in enumerate(census_variables):
                value = candidate.census_data.get(var, 0)
                var_min = census_ranges[var]['min']
                var_max = census_ranges[var]['max']
                
                # Normalize census data
                if var_max > var_min:
                    norm_score = (value - var_min) / (var_max - var_min)
                else:
                    norm_score = 1.0 if value > 0 else 0.0
                
                # Apply weight: Scensus-weighted = Scensus-normalized × Wcensus
                weighted_score = norm_score * census_weights[i]
                candidate.set_census_data_score(var, weighted_score)

    def calculate_final_scores(self, candidates):
        """
        Calculate final scores for all candidates using the scoring system described in section 3.2.4.3.
        
        The final score is calculated as:
        Sfinal-total = Sinfra+census-final + Scritical-zone-score
        
        Where:
        - Sinfra+census-final is the sum of all weighted infrastructure and census scores
        - Scritical-zone-score is the sum of all critical zone scores (direct modifiers)
        
        Also calculates the outage cost savings as a separate economic metric.
        
        Args:
            candidates: List of candidate objects to calculate scores for
        """
        for candidate in candidates:
            # Sum of all weighted infrastructure scores
            infra_total = sum(info.get('weighted_score', 0) 
                            for info in candidate.infrastructures.values())
            candidate.total_infra_score = infra_total
            
            # Sum of all weighted census scores
            census_total = sum(candidate.census_scores.values())
            candidate.total_census_score = census_total
            
            # Sum of critical zone scores (direct modifiers)
            zone_total = sum(candidate.critical_zones.values())
            candidate.total_zone_score = zone_total
            
            # Final score: (weighted scores) + (zone modifiers)
            # Following the formula: Sfinal-total = Sinfra+census-final + Scritical-zone-score
            final_score = (infra_total + census_total) + zone_total
            candidate.final_score = final_score
            
            # Calculate outage cost savings (separate economic metric as per section 3.2.4.3)
            outage_savings = candidate.calculate_total_outage_cost_savings()
            
            self.log(f"Candidate scores: infra={infra_total:.4f}, census={census_total:.4f}, "
                    f"zones={zone_total:.4f}, final={final_score:.4f}, outage_savings=${outage_savings:.2f}")