"""
This module implements the static energy storage evaluation model. It handles all the logic
for evaluating potential sites for static energy storage facilities.
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
        Critical zone scores are direct modifiers and not part of the weighted system.
        
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
                        candidate.set_critical_zone_score(zone_name, zone_score)
                        self.log(f"Candidate intersects with {zone_name}, applying score: {zone_score}")
                        break
                    else:
                        candidate.set_critical_zone_score(zone_name, 0)

    def evaluate_infrastructure(self, candidate, infra_layers, infra_weights, buffer_distance, distance_method):
        """
        Evaluate a candidate against infrastructure layers using the specified distance method.
        """
        for i, layer in enumerate(infra_layers):
            infra_name = layer.name()
            weight = infra_weights[i]
            
            # Calculate scores based on distances to infrastructure
            total_score = 0
            infra_count = 0
            
            for feature in layer.getFeatures():
                if feature.geometry().intersects(candidate.buffer):
                    infra_count += 1
                    start_point = candidate.feature.geometry().asPoint()
                    end_point = feature.geometry().asPoint()
                    
                    if distance_method == 0:  # Road distance
                        try:
                            distance = self.road_analyzer.calculate_road_distance(
                                start_point.x(), start_point.y(),
                                end_point.x(), end_point.y()
                            )
                        except Exception as e:
                            self.log(f"Road distance calculation failed: {str(e)}, using Haversine")
                            distance = candidate.feature.geometry().distance(feature.geometry())
                    else:  # Haversine distance
                        distance = candidate.feature.geometry().distance(feature.geometry())
                    
                    # Score formula: buffer_distance - actual_distance
                    score = max(0, buffer_distance - distance)
                    total_score += score
            
            # Update candidate with counts and raw scores
            candidate.update_infrastructure_count(infra_name, infra_count)
            candidate.set_infrastructure_raw_score(infra_name, total_score)

    def normalize_and_weight_scores(self, candidates, infra_layers, census_variables, infra_weights, census_weights):
        """
        Normalize and apply weights to infrastructure and census scores.
        Under the new system, all weights (infra and census) must sum to 1.0
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
            # Infrastructure scores
            for i, layer in enumerate(infra_layers):
                infra_name = layer.name()
                raw_score = candidate.infrastructures.get(infra_name, {}).get('raw_score', 0)
                
                # Normalize
                if global_infra_max > global_infra_min:
                    norm_score = (raw_score - global_infra_min) / (global_infra_max - global_infra_min)
                else:
                    norm_score = 1.0 if raw_score > 0 else 0.0
                
                # Apply weight
                weighted_score = norm_score * infra_weights[i]
                candidate.set_infrastructure_score(infra_name, norm_score, weighted_score)
            
            # Census scores
            for i, var in enumerate(census_variables):
                value = candidate.census_data.get(var, 0)
                var_min = census_ranges[var]['min']
                var_max = census_ranges[var]['max']
                
                # Normalize
                if var_max > var_min:
                    norm_score = (value - var_min) / (var_max - var_min)
                else:
                    norm_score = 1.0 if value > 0 else 0.0
                
                # Apply weight
                weighted_score = norm_score * census_weights[i]
                candidate.set_census_data_score(var, weighted_score)

    def calculate_final_scores(self, candidates):
        """
        Calculate final scores for all candidates using the new unified scoring system.
        Infrastructure and census scores use the unified weighting system,
        while critical zone scores are direct modifiers.
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
            final_score = (infra_total + census_total) + zone_total
            candidate.final_score = final_score
            
            self.log(f"Candidate scores: infra={infra_total:.4f}, census={census_total:.4f}, "
                    f"zones={zone_total:.4f}, final={final_score:.4f}")