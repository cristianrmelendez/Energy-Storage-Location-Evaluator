# Energy Storage Location Evaluator

## Overview
The Energy Storage Location Evaluator is a QGIS plugin that helps users evaluate potential locations for energy storage systems. It supports both static and mobile energy storage configurations, providing a comprehensive analysis based on proximity to critical infrastructure, demographic data, and critical zones.

## Features
- **Static Energy Storage Model**: Evaluates fixed installation sites using buffer zones around candidate locations
- **Mobile Energy Storage Model**: Evaluates mobile deployment strategies considering coverage areas and travel times
- **Multiple Assessment Criteria**:
  - Proximity to critical infrastructure (hospitals, schools, emergency services, etc.)
  - Demographic considerations from census data
  - Critical zones (favorable or unfavorable areas)
  - Economic analysis through outage cost savings

## Installation
Your plugin EnergyStorageLocationEvaluator was created in:
    /Users/cristianmelendez/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/energy_storage_location_evaluator

Your QGIS plugin directory is located at:
    /Users/cristianmelendez/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins

To install:
1. Copy the entire directory containing your new plugin to the QGIS plugin directory
2. Enable the plugin in the QGIS plugin manager
3. The tool will be available in the Processing Toolbox under "Energy Storage Evaluation"

## Usage
1. Open QGIS and enable the plugin
2. Access the tool from the Processing Toolbox under "Energy Storage Evaluation"
3. Select the appropriate model (Static or Mobile)
4. Provide the required input layers:
   - Candidates layer (point locations)
   - Critical infrastructure layers (points)
   - Census data layer (polygons)
   - Critical zones layers (polygons)
   - For Static Model: Buffer distance and distance calculation method
   - For Mobile Model: Coverage area polygon
5. Configure weights and scores
6. Run the analysis
7. The output layer will contain all scores and evaluations for each candidate location

## Road Network Analysis
For distance calculations, the plugin can use either:
- Straight-line distance (Haversine)
- Road network distance (requires OSRM server)

### OSRM Setup (Important!)
When using road network analysis, please note:
- The plugin expects OSRM to be listening on port 5001 (http://127.0.0.1:5001)
- It is the user's responsibility to set up and configure the OSRM server correctly
- You must provide appropriate mapping files (.osm.pbf) for the specific geographic area where your evaluation is taking place
- Road network distance calculations will fail if OSRM is not properly configured with the correct maps

To set up OSRM:
1. Download OSRM from http://project-osrm.org/
2. Download the appropriate .osm.pbf file for your region from https://download.geofabrik.de/
3. Process the map files according to OSRM documentation
4. Start the OSRM server on port 5001 (or modify the port in the road_network_analyzer.py file)

If you cannot set up OSRM, the plugin will fall back to using straight-line (Haversine) distance calculations.

## Developer Information
- Run tests with `make test`
- Customize by editing the implementation file: `energy_storage_location_evaluator.py`
- Use the Makefile to compile UI and resource files when making changes

For more information, see the PyQGIS Developer Cookbook at:
http://www.qgis.org/pyqgis-cookbook/index.html

(C) 2011-2018 GeoApt LLC - geoapt.com
