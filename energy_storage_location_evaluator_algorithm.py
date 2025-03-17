# -*- coding: utf-8 -*-

"""
/***************************************************************************
 EnergyStorageLocationEvaluator
                                 A QGIS plugin
 A tool to evaluate potential locations for energy storage facilities, providing options for static and mobile configurations based on various spatial criteria.
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
                              -------------------
        begin                : 2025-01-01
        copyright            : (C) 2025 by Cristian Melendez
        email                : cristian.melendez@upr.edu
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

__author__ = 'Cristian Melendez'
__date__ = '2025-01-01'
__copyright__ = '(C) 2025 by Cristian Melendez'

# This will get replaced with a git SHA1 when you do a git archive

__revision__ = '$Format:%H$'

from qgis.PyQt.QtCore import (QCoreApplication, QVariant)

from qgis.core import (QgsProcessing,
                       QgsProcessingAlgorithm,
                       QgsProcessingParameterFeatureSource,
                       QgsProcessingParameterNumber,
                       QgsProcessingParameterFeatureSink,
                       QgsProcessingParameterMultipleLayers,
                       QgsProcessingParameterString,
                       QgsProcessingParameterEnum,
                       QgsFeatureRequest,
                       QgsFeature,
                       QgsFields,
                       QgsField,
                       QgsWkbTypes,
                       QgsFeatureSink,
                       QgsProcessingException,
                       QgsPointXY,
                       QgsProject,
                       QgsCoordinateTransform,
                       QgsCoordinateReferenceSystem,
                       QgsGeometry,
                       QgsRectangle
                       )

# Import both candidate classes - each model has its own dedicated candidate class
from .mobile_candidate import Candidate as MobileCandidate
from .static_candidate import Candidate as StaticCandidate
from .static_model import StaticEnergyStorageEvaluator
from .mobile_model import MobileEnergyStorageEvaluator


class EnergyStorageLocationEvaluatorAlgorithm(QgsProcessingAlgorithm):
    """
    This algorithm evaluates potential locations for energy storage systems.
    It supports two distinct models:
    1. Static Energy Storage (section 3.2): Uses buffer zones around each candidate
    2. Mobile Energy Storage (section 3.3): Uses a coverage area and travel times
    
    The algorithm automatically selects the appropriate model based on user input
    and handles parameter validation, data processing, and scoring accordingly.
    """

    # Input parameters
    EVALUATION_TYPE = 'EVALUATION_TYPE'
    DISTANCE_METHOD = 'DISTANCE_METHOD'
    CANDIDATES_LAYER = 'CANDIDATES_LAYER'
    BUFFER_DISTANCE = 'BUFFER_DISTANCE'
    CRITICAL_INFRASTRUCTURES = 'CRITICAL_INFRASTRUCTURES'
    INFRASTRUCTURE_WEIGHTS = 'INFRASTRUCTURE_WEIGHTS'
    CENSUS_DATA_LAYER = 'CENSUS_DATA_LAYER'
    CENSUS_DATA_WEIGHTS = 'CENSUS_DATA_WEIGHTS'
    CRITICAL_ZONES = 'CRITICAL_ZONES'
    CRITICAL_ZONE_SCORES = 'CRITICAL_ZONE_SCORES'
    COVERAGE_AREA = 'COVERAGE_AREA'  # Used only for mobile model
    
    # Output parameter
    OUTPUT = 'OUTPUT'

    def initAlgorithm(self, config=None):
        """
        Define the inputs and outputs of the algorithm.
        
        This method sets up the parameters needed for both static and mobile
        energy storage evaluation models. Some parameters are specific to
        one model or the other.
        """
        # Evaluation Type - determines which model to use
        self.addParameter(
            QgsProcessingParameterEnum(
                self.EVALUATION_TYPE,
                self.tr('Select Evaluation Type'),
                options=['Static Energy Storage', 'Mobile Energy Storage'],
                defaultValue=0  # Default to Static Energy Storage
            )
        )

        # Coverage Area - only required for Mobile Energy Storage (section 3.3.2.2)
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.COVERAGE_AREA,
                self.tr('Coverage Area (Required for Mobile Energy Storage Only)'),
                [QgsProcessing.TypeVectorPolygon],
                optional=True  # Optional because it's only needed for mobile model
            )
        )

        # Distance Method - only applicable for Static Energy Storage (section 3.2.2.1)
        self.addParameter(
            QgsProcessingParameterEnum(
                self.DISTANCE_METHOD,
                self.tr('Select distance calculation method '
                        '(Only for static model, for mobile model the only option is time travel through the road network)'),
                options=['Road distance', 'Haversine distance (straight-line)'],
                defaultValue=0  # Default to Road distance
            )
        )

        # Candidates Layer - required for both models
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.CANDIDATES_LAYER,
                self.tr('Candidates Layer'),
                [QgsProcessing.TypeVectorPoint]
            )
        )

        # Buffer Distance - only used for Static Energy Storage (section 3.2.2.2)
        self.addParameter(
            QgsProcessingParameterNumber(
                self.BUFFER_DISTANCE,
                self.tr('Buffer distance in kilometers (Required For Static Energy Storage Only)'),
                QgsProcessingParameterNumber.Double,
                defaultValue=1.0,
                minValue=0.0
            )
        )

        # Critical Infrastructure Layers - required for both models
        self.addParameter(
            QgsProcessingParameterMultipleLayers(
                self.CRITICAL_INFRASTRUCTURES,
                self.tr('Critical Infrastructure Layers'),
                QgsProcessing.TypeVectorPoint
            )
        )

        # Infrastructure Weights - required for both models
        self.addParameter(
            QgsProcessingParameterString(
                self.INFRASTRUCTURE_WEIGHTS,
                self.tr('Enter the weights for each infrastructure layer (comma-separated)'
                        ' in the same order as the layers.'),
                defaultValue='0.25,0.25,0.25,0.25'  # Example default value for 4 layers
            )
        )

        # Census Data Layer - required for both models
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.CENSUS_DATA_LAYER,
                self.tr('Census Data Layer'),
                [QgsProcessing.TypeVectorPolygon]  # Accept only polygon layers
            )
        )

        # Census Data Weights - required for both models
        self.addParameter(
            QgsProcessingParameterString(
                self.CENSUS_DATA_WEIGHTS,
                self.tr('Enter weights for the census data variables (comma-separated)'),
                defaultValue='0.25,0.25,0.25,0.25'  # Example default value for 4 variables
            )
        )

        # Critical Zones Layers - required for both models
        self.addParameter(
            QgsProcessingParameterMultipleLayers(
                self.CRITICAL_ZONES,
                self.tr('Critical Zones Layers'),
                QgsProcessing.TypeVectorPolygon  # Only polygon layers
            )
        )

        # Critical Zone Scores - required for both models
        self.addParameter(
            QgsProcessingParameterString(
                self.CRITICAL_ZONE_SCORES,
                self.tr('Enter the scores for each critical zone layer (comma-separated)'
                        ' in the same order as the layers. Use negative values to subtract score.'),
                defaultValue='10,-5,-10'  # Example default value
            )
        )

        # Output Layer - required for both models
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT,
                self.tr('Output layer'),
                QgsProcessing.TypeVectorAnyGeometry  # Allow both points and polygons
            )
        )

    def safe_field_name(self, layer_name):
        """
        Convert a layer name to a safe field name.
        
        Args:
            layer_name (str): Original layer name
            
        Returns:
            str: Safe field name with spaces replaced and special characters removed
        """
        # Replace spaces with underscores and remove special characters
        return ''.join([c if c.isalnum() or c == '_' else '' for c in layer_name.replace(' ', '_')])

    def _initialize_output_fields(self):
        """
        Initialize the base output layer fields structure.
        
        Returns:
            QgsFields: Base fields for the output layer
        """
        output_fields = QgsFields()
        output_fields.append(QgsField('id', QVariant.Int))
        output_fields.append(QgsField('name', QVariant.String))
        return output_fields

    def _validate_weights(self, weights_str, expected_count, weight_type):
        """
        Validate and normalize weights.
        
        As described in sections 3.2.4.4 and 3.3.4.4, weights must sum to 1.0.
        
        Args:
            weights_str (str): Comma-separated weights
            expected_count (int): Expected number of weights
            weight_type (str): Type of weights for error messages
            
        Returns:
            list: Normalized weights
            
        Raises:
            QgsProcessingException: If weights are invalid
        """
        try:
            weights = [float(w) for w in weights_str.split(',')]
        except ValueError:
            raise QgsProcessingException(f"{weight_type} weights must be numeric values separated by commas.")
        
        if len(weights) != expected_count:
            raise QgsProcessingException(
                f"The number of {weight_type.lower()} weights ({len(weights)}) does not match "
                f"the expected count ({expected_count}).")
        
        if not 0.999 <= sum(weights) <= 1.001:
            raise QgsProcessingException(
                f"{weight_type} weights sum to {sum(weights)}, but they must sum to 1.0.")
        
        # Normalize weights to exactly 1.0
        weight_sum = sum(weights)
        if weight_sum != 1.0:
            weights = [w/weight_sum for w in weights]
            
        return weights

    def _add_infrastructure_fields(self, output_fields, infra_layers, evaluation_type):
        """
        Add infrastructure-related fields to the output structure.
        
        The fields differ between static and mobile models:
        - For Static Model (evaluation_type = 0): Includes outage costs (section 3.2.4.3)
        - For Mobile Model (evaluation_type = 1): Focuses on travel times (section 3.3.4.2.1)
        
        Args:
            output_fields (QgsFields): Fields to add to
            infra_layers (list): List of infrastructure layers
            evaluation_type (int): 0 for static, 1 for mobile
            
        Returns:
            QgsFields: Updated fields
        """
        for layer in infra_layers:
            infra_name = self.safe_field_name(layer.name())
            # Truncate to 10 chars for shapefile compatibility but store full name
            short_name = infra_name[:10]
            
            # Basic score fields needed for both models
            count_field = QgsField(f'{short_name}_Cnt', QVariant.Int)
            count_field.setAlias(f'{layer.name()} Count')
            output_fields.append(count_field)
            
            raw_field = QgsField(f'{short_name}_Raw', QVariant.Double)
            raw_field.setAlias(f'{layer.name()} Raw Score')
            output_fields.append(raw_field)
            
            final_field = QgsField(f'{short_name}_Fnl', QVariant.Double)
            final_field.setAlias(f'{layer.name()} Final Score')
            output_fields.append(final_field)
            
            if evaluation_type == 0:  # Static Energy Storage
                # Only static model tracks outage costs (section 3.2.4.3)
                cost_field = QgsField(f'{short_name}_Cost', QVariant.Double)
                cost_field.setAlias(f'{layer.name()} Outage Cost')
                output_fields.append(cost_field)
        
        total_infra_field = QgsField('TotalInfra', QVariant.Double)
        total_infra_field.setAlias('Total Infrastructure Score')
        output_fields.append(total_infra_field)
        
        # Add total outage cost field only for static model (section 3.2.4.3)
        if evaluation_type == 0:  # Static Energy Storage
            total_cost_field = QgsField('TotalCost', QVariant.Double)
            total_cost_field.setAlias('Total Outage Cost Savings')
            output_fields.append(total_cost_field)
            
        return output_fields

    def _add_census_fields(self, output_fields, census_layer):
        """
        Add census-related fields and extract census variables.
        
        Both models use the same approach for census data, as specified in 
        sections 3.2.4.2.2 and 3.3.4.2.2.
        
        Args:
            output_fields (QgsFields): Fields to add to
            census_layer: Census data layer
            
        Returns:
            tuple: (updated fields, list of census variables)
        """
        census_fields = census_layer.fields()
        census_variables = []
        
        for i in range(6, len(census_fields)):
            field_name = census_fields.at(i).name()
            census_variables.append(field_name)
            
            # Create short field names with full aliases
            short_name = field_name[:8]
            
            val_field = QgsField(f'{short_name}_Val', QVariant.Double)
            val_field.setAlias(f'{field_name} Value')
            output_fields.append(val_field)
            
            score_field = QgsField(f'{short_name}_Scr', QVariant.Double)
            score_field.setAlias(f'{field_name} Score')
            output_fields.append(score_field)
            
        return output_fields, census_variables

    def _add_zone_fields(self, output_fields, zone_layers):
        """
        Add zone-related fields to the output structure.
        
        Both models use the same approach for critical zones, as specified in
        sections 3.2.4.2.3 and 3.3.4.2.2.
        
        Args:
            output_fields (QgsFields): Fields to add to
            zone_layers: List of zone layers
            
        Returns:
            QgsFields: Updated fields
        """
        for layer in zone_layers:
            zone_name = self.safe_field_name(layer.name())
            # Create shorter field name with full alias
            short_name = zone_name[:8]
            
            zone_field = QgsField(f'{short_name}_Scr', QVariant.Double)
            zone_field.setAlias(f'{layer.name()} Score')
            output_fields.append(zone_field)
        
        total_zone_field = QgsField('TotalZones', QVariant.Double)
        total_zone_field.setAlias('Total Zones Score')
        output_fields.append(total_zone_field)
        
        # Add total demographic/census score field
        total_demo_field = QgsField('TotalDemo', QVariant.Double)
        total_demo_field.setAlias('Total Demographic Score')
        output_fields.append(total_demo_field)
        
        final_field = QgsField('FinalScore', QVariant.Double)
        final_field.setAlias('Final Score')
        output_fields.append(final_field)
        
        return output_fields

    def _log_crs_info(self, candidate_layer, infra_layers, feedback):
        """
        Log CRS information for debugging.
        
        Args:
            candidate_layer: Candidate layer
            infra_layers: List of infrastructure layers
            feedback: Feedback object for logging
        """
        feedback.pushInfo(f"Candidate layer CRS: {candidate_layer.sourceCrs().authid()}")
        for i, layer in enumerate(infra_layers):
            feedback.pushInfo(f"Infrastructure layer {i+1} ({layer.name()}) CRS: {layer.crs().authid()}")

    def _prepare_output_fields(self, candidates_layer, infra_layers, evaluation_type, census_layer):
        """
        Prepare the complete set of output fields for the result layer.
        
        This combines fields from infrastructure, census data, and critical zones
        based on the evaluation type (static or mobile).
        
        Args:
            candidates_layer: Candidate layer
            infra_layers: List of infrastructure layers
            evaluation_type (int): 0 for static, 1 for mobile
            census_layer: Census data layer
            
        Returns:
            QgsFields: Complete set of output fields
        """
        # Start with base fields
        output_fields = self._initialize_output_fields()
        
        # Add infrastructure fields - different between static and mobile
        output_fields = self._add_infrastructure_fields(output_fields, infra_layers, evaluation_type)
        
        # Add census fields if census layer is provided - same for both models
        if census_layer:
            output_fields, census_variables = self._add_census_fields(output_fields, census_layer)
        
        # Add zone fields - same for both models
        zone_layers = self.parameterAsLayerList(
            self.parameters, self.CRITICAL_ZONES, self.context
        )
        output_fields = self._add_zone_fields(output_fields, zone_layers)
        
        return output_fields

    def processAlgorithm(self, parameters, context, feedback):
        """
        Execute the algorithm to evaluate energy storage locations.
        
        This method handles both static and mobile energy storage models, selecting
        the appropriate model based on the evaluation_type parameter. It manages
        parameter validation, data processing, and result generation for both models.
        
        Args:
            parameters: Algorithm parameters
            context: Processing context
            feedback: Feedback object for logging
            
        Returns:
            dict: Output layer ID
        """
        self.feedback = feedback
        self.parameters = parameters
        self.context = context
        feedback.pushInfo('Starting Energy Storage Location Evaluator')
        try:
            # Extract common parameters for both models
            candidates_layer = self.parameterAsSource(parameters, self.CANDIDATES_LAYER, context)
            evaluation_type = self.parameterAsInt(parameters, self.EVALUATION_TYPE, context)
            
            infra_layers = self.parameterAsLayerList(parameters, self.CRITICAL_INFRASTRUCTURES, context)
            census_layer = self.parameterAsSource(parameters, self.CENSUS_DATA_LAYER, context)
            zone_layers = self.parameterAsLayerList(parameters, self.CRITICAL_ZONES, context)
            
            infra_weights = parameters[self.INFRASTRUCTURE_WEIGHTS]
            census_weights = parameters[self.CENSUS_DATA_WEIGHTS]
            
            try:
                zone_scores = [float(x) for x in parameters[self.CRITICAL_ZONE_SCORES].split(',')]
            except ValueError:
                raise QgsProcessingException("Critical zone scores must be numeric values separated by commas.")
            
            # Validate common parameters
            if not candidates_layer:
                raise QgsProcessingException("No candidates layer provided")
            if not infra_layers:
                raise QgsProcessingException("No infrastructure layers provided")
            if len(zone_layers) != len(zone_scores):
                raise QgsProcessingException(
                    f"Number of zone scores ({len(zone_scores)}) does not match "
                    f"number of critical zone layers ({len(zone_layers)})"
                )
            
            # Extract and validate model-specific parameters
            if evaluation_type == 0:  # Static Energy Storage Model
                # For static model, buffer distance and distance method are required
                buffer_distance = self.parameterAsDouble(parameters, self.BUFFER_DISTANCE, context)
                distance_method = self.parameterAsInt(parameters, self.DISTANCE_METHOD, context)
                
                if buffer_distance <= 0:
                    raise QgsProcessingException("Buffer distance must be greater than 0 for static model")
                
                # Convert buffer distance to meters (static model uses meters)
                buffer_distance_meters = buffer_distance * 1000
                
                feedback.pushInfo(f"Using Static Energy Storage Model with buffer distance: {buffer_distance}km ({buffer_distance_meters}m)")
                feedback.pushInfo(f"Distance method: {['Road', 'Haversine'][distance_method]}")
                
            else:  # Mobile Energy Storage Model
                # For mobile model, coverage area is required
                coverage_area = self.parameterAsSource(parameters, self.COVERAGE_AREA, context)
                
                if not coverage_area:
                    raise QgsProcessingException("Coverage area is required for mobile energy storage evaluation")
                
                # Extract coverage geometry
                coverage_geom = None
                for feature in coverage_area.getFeatures():
                    coverage_geom = feature.geometry()
                    break
                
                if not coverage_geom:
                    raise QgsProcessingException("Empty coverage area geometry")
                
                feedback.pushInfo("Using Mobile Energy Storage Model with user-defined coverage area")
            
            # Create output fields structure based on evaluation type
            fields = self._prepare_output_fields(candidates_layer, infra_layers, 
                                              evaluation_type, census_layer)
            
            # Create the sink (output layer) with appropriate geometry type
            if evaluation_type == 0:  # Static Energy Storage - uses polygon (buffer) outputs
                sink, dest_id = self.parameterAsSink(
                    parameters, self.OUTPUT, context, fields, 
                    QgsWkbTypes.Polygon, candidates_layer.sourceCrs()
                )
            else:  # Mobile Energy Storage - uses point outputs
                sink, dest_id = self.parameterAsSink(
                    parameters, self.OUTPUT, context, fields, 
                    QgsWkbTypes.Point, candidates_layer.sourceCrs()
                )
            
            if sink is None:
                raise QgsProcessingException("Failed to create output layer")
            
            feedback.pushInfo(f"Created output sink with {len(fields)} fields")
            
            # Initialize the appropriate model based on evaluation type
            if evaluation_type == 0:  # Static Energy Storage
                model = StaticEnergyStorageEvaluator(feedback)
            else:  # Mobile Energy Storage
                model = MobileEnergyStorageEvaluator(feedback)
            
            # Initialize candidates based on model type
            candidates = []
            total_features = candidates_layer.featureCount()
            feedback.pushInfo(f"Processing {total_features} candidate locations")
            
            for current, feature in enumerate(candidates_layer.getFeatures()):
                if feedback.isCanceled():
                    break
                    
                try:
                    if evaluation_type == 0:  # Static Energy Storage
                        # For static model, buffer_distance is required (section 3.2.2.2)
                        candidate = StaticCandidate(feature, buffer_distance_meters, feedback)
                    else:  # Mobile Energy Storage
                        # For mobile model, buffer parameter is not used (section 3.3.2.2)
                        # but we still pass the parameter for API compatibility
                        candidate = MobileCandidate(feature, None, feedback)
                        
                    candidates.append(candidate)
                    feedback.setProgress(int(current * 20 / total_features))  # 0-20% progress
                    
                except Exception as e:
                    feedback.reportError(f"Error initializing candidate {current}: {str(e)}")
                    continue
            
            # Process census data and extract variables
            try:
                census_vars = []
                if census_layer:
                    census_fields = census_layer.fields()
                    census_vars = [field.name() for field in census_fields 
                                 if field.isNumeric() and not field.name().lower() in ('id', 'fid')]
                    
                    if not census_vars:
                        feedback.pushWarning("No numeric census variables found in census layer")
                
                # Validate weights through the model
                infra_weights_list, census_weights_list = model.validate_weights(
                    infra_weights, census_weights,
                    len(infra_layers), len(census_vars)
                )
            except Exception as e:
                raise QgsProcessingException(f"Weight validation failed: {str(e)}")
            
            # Process census data if available
            if census_layer and census_vars:
                feedback.pushInfo(f"Processing census data with {len(census_vars)} variables")
                for i, candidate in enumerate(candidates):
                    if feedback.isCanceled():
                        break
                    try:
                        self._process_census_data(candidate, census_layer, census_vars)
                    except Exception as e:
                        feedback.reportError(f"Error processing census data for candidate {candidate.id}: {str(e)}")
                    
                    if i % 10 == 0:  # Update progress every 10 candidates
                        feedback.setProgress(20 + int(i * 10 / len(candidates)))  # 20-30% progress
            
            # Evaluate critical zones
            try:
                feedback.pushInfo(f"Evaluating {len(zone_layers)} critical zones")
                model.evaluate_critical_zones(candidates, zone_layers, zone_scores)
            except Exception as e:
                feedback.reportError(f"Error evaluating critical zones: {str(e)}")
                # Continue despite errors
            
            # Evaluate infrastructures based on model type
            feedback.pushInfo(f"Evaluating {len(infra_layers)} infrastructure layers")
            for i, candidate in enumerate(candidates):
                if feedback.isCanceled():
                    break
                try:
                    if evaluation_type == 0:  # Static model
                        # Static model needs buffer_distance and distance_method
                        model.evaluate_infrastructure(
                            candidate, infra_layers, infra_weights_list, 
                            buffer_distance_meters, distance_method
                        )
                    else:  # Mobile model
                        # Mobile model needs coverage_geom
                        model.evaluate_infrastructure(
                            candidate, infra_layers, infra_weights_list, coverage_geom
                        )
                except Exception as e:
                    feedback.reportError(f"Error evaluating infrastructure for candidate {candidate.id}: {str(e)}")
                
                if i % 10 == 0:  # Update progress every 10 candidates
                    feedback.setProgress(30 + int(i * 40 / len(candidates)))  # 30-70% progress
            
            # Normalize and calculate final scores
            try:
                feedback.pushInfo("Normalizing and calculating final scores")
                model.normalize_and_weight_scores(
                    candidates, infra_layers, census_vars, 
                    infra_weights_list, census_weights_list
                )
                model.calculate_final_scores(candidates)
            except Exception as e:
                feedback.reportError(f"Error calculating final scores: {str(e)}")
                raise
            
            # Write results to output layer
            feedback.pushInfo("Writing results to output layer")
            for i, candidate in enumerate(candidates):
                if feedback.isCanceled():
                    break
                try:
                    feat = QgsFeature(fields)
                    
                    # Use the appropriate geometry based on the model type
                    if evaluation_type == 0:  # Static Energy Storage - use buffer polygon
                        if not candidate.buffer:
                            feedback.reportError(f"Missing buffer geometry for candidate {candidate.id}")
                            continue
                            
                        if not candidate.buffer.isGeosValid():
                            feedback.reportError(f"Invalid buffer geometry for candidate {candidate.id}")
                            continue
                            
                        feat.setGeometry(candidate.buffer)
                        feedback.pushInfo(f"Adding buffer polygon for candidate {candidate.id}, area: {candidate.buffer.area():.2f}m²")
                    else:  # Mobile Energy Storage - use point geometry
                        feat.setGeometry(candidate.feature.geometry())
                    
                    # Generate output attributes from candidate
                    attrs = candidate.generate_output_attributes()
                    feat.setAttributes(attrs)
                    
                    if not sink.addFeature(feat, QgsFeatureSink.FastInsert):
                        feedback.reportError(f"Failed to add feature for candidate {candidate.id}")
                except Exception as e:
                    feedback.reportError(f"Error writing output for candidate {candidate.id}: {str(e)}")
                
                if i % 10 == 0:  # Update progress every 10 candidates
                    feedback.setProgress(70 + int(i * 30 / len(candidates)))  # 70-100% progress
            
            feedback.pushInfo("Energy Storage Location Evaluation completed successfully")
            return {'OUTPUT': dest_id}
            
        except QgsProcessingException as e:
            feedback.reportError(f"Error: {str(e)}")
            raise
        except Exception as e:
            feedback.reportError(f"Critical error in processAlgorithm: {str(e)}")
            raise

    def _process_census_data(self, candidate, census_layer, census_vars):
        """
        Process census data for a candidate location.
        
        For both models, this identifies the census area that intersects with
        the candidate and extracts the relevant census variables.
        
        Args:
            candidate: Candidate object (static or mobile)
            census_layer: Census data layer
            census_vars: List of census variable names to extract
            
        Raises:
            Exception: If there's an error processing the census data
        """
        try:
            # Get candidate geometry
            candidate_geom = candidate.feature.geometry()
            
            if not candidate_geom.isGeosValid():
                candidate_geom = candidate_geom.makeValid()
            
            found_intersection = False
            
            # For each census feature, check if it intersects with the candidate
            for census_feature in census_layer.getFeatures():
                census_geom = census_feature.geometry()
                
                if not census_geom.isGeosValid():
                    census_geom = census_geom.makeValid()
                
                if census_geom.intersects(candidate_geom):
                    # Found intersecting census area, extract the values
                    for var_name in census_vars:
                        if var_name in census_feature.fields().names():
                            value = census_feature[var_name]
                            if value is not None and value != "NULL":
                                try:
                                    value_float = float(value)
                                    # Store the raw census data value
                                    candidate.set_census_data(var_name, value_float)
                                except (ValueError, TypeError):
                                    self.feedback.pushInfo(f"Could not convert census value '{value}' to number")
                    
                    found_intersection = True
                    break  # Assuming each candidate is in only one census area
            
            if not found_intersection:
                self.feedback.pushWarning(f"No intersecting census area found for candidate {candidate.id}")
                
        except Exception as e:
            self.feedback.reportError(f"Error in _process_census_data: {str(e)}")
            raise

    def name(self):
        """
        Returns the algorithm name, used for identifying the algorithm.
        """
        return 'EvaluateEnergyStorageSites'

    def displayName(self):
        """
        Returns the translated algorithm name.
        """
        return self.tr(self.name())

    def group(self):
        """
        Returns the name of the group this algorithm belongs to.
        """
        return self.tr(self.groupId())

    def groupId(self):
        """
        Returns the unique ID of the group this algorithm belongs to.
        """
        return 'Energy Storage Evaluation'

    def tr(self, string):
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):
        return EnergyStorageLocationEvaluatorAlgorithm()
