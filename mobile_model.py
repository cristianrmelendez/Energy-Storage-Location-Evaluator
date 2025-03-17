"""
This module implements the mobile energy storage evaluation model. It handles all the logic
for evaluating potential sites for mobile energy storage facilities as described in the
methodology section 3.3 (Mobile Energy Storage System Model).
"""

from qgis.core import (QgsProcessingException, QgsFeature, QgsFields, QgsField,
                      QgsWkbTypes, QgsFeatureSink, QgsPointXY, QgsProject,
                      QgsCoordinateTransform, QgsCoordinateReferenceSystem,
                      QgsGeometry, QgsRectangle)
from qgis.PyQt.QtCore import QVariant
from .road_network_analyzer import RoadNetworkAnalyzer
from .mobile_candidate import Candidate as MobileCandidate

class MobileEnergyStorageEvaluator:
    def __init__(self, feedback=None):
        """
        Initialize the mobile evaluator with optional feedback mechanism.
        
        The mobile evaluator focuses on travel times rather than distances,
        as described in section 3.3.2.1 (Estimating Traveling Time).
        """
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
        
        As described in section 3.3.4.4, the customization of scoring parameters
        follows the same approach as the static model, where weights must sum to 1.0.
        
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
        
        As described in section 3.3.4.2.2, critical zone scores follow the same
        approach as the static model. They are direct modifiers to the final score
        and not part of the weighted system.
        
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
                        # Apply the zone score as a direct modifier
                        candidate.set_critical_zone_score(zone_name, zone_score)
                        self.log(f"Candidate intersects with {zone_name}, applying score: {zone_score}")
                        break
                    else:
                        candidate.set_critical_zone_score(zone_name, 0)

    def evaluate_infrastructure(self, candidate, infra_layers, infra_weights, coverage_area):
        """
        Evaluate a candidate against infrastructure layers using ETA-based scoring.
        
        As described in section 3.3.2.1 and 3.3.4.2.1, for mobile ESS, the emphasis
        shifts from proximity to traveling time. This method uses OSRM to calculate
        the ETA from each candidate to infrastructure points within the coverage area.
        
        Instead of using individual buffers for each candidate, mobile ESS uses a
        single, user-defined coverage area (section 3.3.2.2).
        
        Args:
            candidate: Candidate object to evaluate
            infra_layers: List of infrastructure layers
            infra_weights: List of weights for each infrastructure layer
            coverage_area: QgsGeometry representing the shared coverage area
        """
        try:
            for i, layer in enumerate(infra_layers):
                infra_name = layer.name()
                total_score = 0
                total_duration = 0
                infra_count = 0
                invalid_count = 0
                
                self.log(f"\nEvaluating {infra_name} for candidate {candidate.id}:")
                
                for feature in layer.getFeatures():
                    try:
                        # Only consider infrastructure within the coverage area
                        # This implements the coverage area concept from section 3.3.2.2
                        if feature.geometry().intersects(coverage_area):
                            infra_count += 1
                            start_point = candidate.feature.geometry().asPoint()
                            end_point = feature.geometry().asPoint()
                            
                            # Transform coordinates for OSRM
                            start_lon, start_lat = self.road_analyzer.transform_coordinates(
                                start_point.x(), start_point.y()
                            )
                            end_lon, end_lat = self.road_analyzer.transform_coordinates(
                                end_point.x(), end_point.y()
                            )
                            
                            # Get duration in seconds with additional validation
                            # This implements the ETA calculation from section 3.3.2.1
                            try:
                                duration = self.road_analyzer.calculate_eta(
                                    start_lon, start_lat, end_lon, end_lat
                                )
                                
                                if duration is not None and duration > 0:
                                    total_duration += duration
                                    # Store the raw duration as the score - we'll invert during normalization
                                    # to ensure that shorter travel times result in higher scores
                                    total_score += duration
                                    
                                    self.log(f"Infrastructure {infra_count}: duration = {duration:.2f}s")
                                else:
                                    invalid_count += 1
                                    self.log(f"Infrastructure {infra_count}: Invalid duration received, skipping")
                                    continue
                                    
                            except Exception as e:
                                invalid_count += 1
                                self.log(f"Error calculating ETA for infrastructure {infra_count}: {str(e)}")
                                continue
                                
                    except Exception as e:
                        invalid_count += 1
                        self.log(f"Error processing infrastructure {infra_count}: {str(e)}")
                        continue
                
                # Only update scores if we have valid results
                if infra_count > invalid_count:
                    # Update candidate scores
                    candidate.update_infrastructure_count(infra_name, infra_count - invalid_count)
                    # Store total duration as the raw score
                    candidate.set_infrastructure_raw_score(infra_name, total_score)
                    candidate.set_infrastructure_total_duration(infra_name, total_duration)
                    
                    self.log(f"\nSummary for {infra_name}:")
                    self.log(f"Total valid infrastructures: {infra_count - invalid_count}")
                    self.log(f"Invalid/skipped infrastructures: {invalid_count}")
                    self.log(f"Total duration: {total_duration:.2f}s")
                else:
                    self.log(f"\nWarning: No valid results for {infra_name}, skipping infrastructure type")
                    candidate.update_infrastructure_count(infra_name, 0)
                    candidate.set_infrastructure_raw_score(infra_name, float('inf'))
                    candidate.set_infrastructure_total_duration(infra_name, 0)
        
        except Exception as e:
            self.log(f"Error in evaluate_infrastructure: {str(e)}")
            raise

    def normalize_and_weight_scores(self, candidates, infra_layers, census_vars, infra_weights, census_weights):
        """
        Normalize and apply weights to infrastructure and census scores.
        
        For infrastructure scores, the implementation inverts the normalization
        since lower durations result in higher normalized scores. This follows
        the formula from section 3.3.4.2.1:
        
        1. Raw score formula: Sinfra = ∑(1/ETA)
        2. Normalization: Sinfra-normalized = (Sinfra - Sinfra-min) / (Sinfra-max - Sinfra-min)
        3. Weighting: Sinfra-weighted = Sinfra-normalized × Winfra
        
        In our implementation, we first store raw durations and then convert them 
        to scores during normalization by inverting the relation.
        
        Args:
            candidates: List of candidate objects
            infra_layers: List of infrastructure layers
            census_vars: List of census variable names
            infra_weights: List of weights for infrastructure layers
            census_weights: List of weights for census variables
        """
        try:
            # Find global min/max for infrastructure scores (these are durations)
            global_infra_min = float('inf')
            global_infra_max = float('-inf')
            
            for candidate in candidates:
                for layer in infra_layers:
                    infra_name = layer.name()
                    duration = candidate.infrastructures.get(infra_name, {}).get('raw_score', float('inf'))
                    if duration != float('inf'):  # Only include valid durations
                        global_infra_min = min(global_infra_min, duration)
                        global_infra_max = max(global_infra_max, duration)
            
            # Find global min/max for census values
            census_ranges = {var: {'min': float('inf'), 'max': float('-inf')} 
                            for var in census_vars}
            
            for candidate in candidates:
                for var in census_vars:
                    value = candidate.census_data.get(var, 0)
                    census_ranges[var]['min'] = min(census_ranges[var]['min'], value)
                    census_ranges[var]['max'] = max(census_ranges[var]['max'], value)
            
            # Apply normalization and weights
            for candidate in candidates:
                # Infrastructure scores
                total_infra_score = 0
                for i, layer in enumerate(infra_layers):
                    infra_name = layer.name()
                    duration = candidate.infrastructures.get(infra_name, {}).get('raw_score', float('inf'))
                    
                    # Normalize score - invert the normalization since lower duration is better
                    # This implements the key difference in the mobile model scoring, where
                    # shorter travel times mean higher scores
                    if duration == float('inf'):
                        normalized = 0
                    elif global_infra_max == global_infra_min:
                        # If all durations are the same, give them all a score of 1
                        normalized = 1 if duration != float('inf') else 0
                    else:
                        # Invert the normalization: (max - duration) / (max - min)
                        # This way, lowest duration gets highest score (1.0)
                        normalized = (global_infra_max - duration) / (global_infra_max - global_infra_min)
                        normalized = max(0, min(1, normalized))  # Ensure value is between 0 and 1
                    
                    # Apply weight: Sinfra-weighted = Sinfra-normalized × Winfra
                    weighted_score = normalized * infra_weights[i]
                    candidate.set_infrastructure_score(infra_name, weighted_score)
                    total_infra_score += weighted_score
                    
                    self.log(f"\nInfrastructure {infra_name} for candidate {candidate.id}:")
                    self.log(f"  Raw duration: {duration:.4f}s")
                    self.log(f"  Normalized: {normalized:.4f}")
                    self.log(f"  Weighted: {weighted_score:.4f}")
                
                candidate.total_infra_score = total_infra_score
                
                # Census scores - following same normalization approach as static model
                # This is in line with section 3.3.4.2.2 which states demographic 
                # considerations follow the same approach as the static model
                total_census_score = 0
                for i, var in enumerate(census_vars):
                    value = candidate.census_data.get(var, 0)
                    var_min = census_ranges[var]['min']
                    var_max = census_ranges[var]['max']
                    
                    # Normalize score
                    if var_max > var_min:
                        normalized = (value - var_min) / (var_max - var_min)
                    else:
                        normalized = 1.0 if value > 0 else 0.0
                    normalized = max(0, min(1, normalized))  # Ensure value is between 0 and 1
                    
                    # Apply weight
                    weighted_score = normalized * census_weights[i]
                    candidate.set_census_data_score(var, weighted_score)
                    total_census_score += weighted_score
                    
                    self.log(f"\nCensus variable {var} for candidate {candidate.id}:")
                    self.log(f"  Raw value: {value:.4f}")
                    self.log(f"  Normalized: {normalized:.4f}")
                    self.log(f"  Weighted: {weighted_score:.4f}")
                
                candidate.total_census_score = total_census_score
            
        except Exception as e:
            self.log(f"Error in normalize_and_weight_scores: {str(e)}")
            raise

    def calculate_final_scores(self, candidates):
        """
        Calculate final scores for all candidates.
        
        This implements the final score calculation from section 3.3.4.3,
        combining normalized and weighted infrastructure scores, census scores,
        and critical zone scores.
        
        Note that unlike the static model, mobile ESS does not include outage cost
        savings calculations, as mentioned in section 3.3.4.3 under "Outage Cost Savings".
        
        Args:
            candidates: List of candidate objects to calculate scores for
        """
        try:
            self.log("\nCalculating final scores:")
            for candidate in candidates:
                try:
                    # Calculate sum of infrastructure scores
                    infra_score = candidate.total_infra_score
                    
                    # Calculate sum of census scores
                    census_score = candidate.total_census_score
                    
                    # Calculate sum of critical zone scores
                    critical_zone_total = sum(candidate.critical_zones.values())
                    candidate.total_zone_score = critical_zone_total
                    
                    # Final score is the direct sum of all three components
                    # This ensures that the total matches when manually adding the components
                    final_score = infra_score + census_score + critical_zone_total
                    
                    # Store the final score
                    candidate.final_score = final_score
                    
                    # Log detailed scoring information
                    self.log(f"\nCandidate {candidate.id}:")
                    self.log(f"  Infrastructure score: {infra_score:.4f}")
                    self.log(f"  Census/demographic score: {census_score:.4f}")
                    self.log(f"  Critical zone total: {critical_zone_total:.4f}")
                    self.log(f"  Final score: {final_score:.4f}")
                    
                except Exception as e:
                    self.log(f"Error calculating score for candidate {candidate.id}: {str(e)}")
                    candidate.final_score = 0
                    continue
        
        except Exception as e:
            self.log(f"Error in calculate_final_scores: {str(e)}")
            raise