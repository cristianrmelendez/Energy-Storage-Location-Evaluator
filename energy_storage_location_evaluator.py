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

import os
import sys
import inspect

from qgis.core import QgsProcessingAlgorithm, QgsApplication
from .energy_storage_location_evaluator_provider import EnergyStorageLocationEvaluatorProvider

cmd_folder = os.path.split(inspect.getfile(inspect.currentframe()))[0]

if cmd_folder not in sys.path:
    sys.path.insert(0, cmd_folder)


class EnergyStorageLocationEvaluatorPlugin(object):

    def __init__(self):
        self.provider = None

    def initProcessing(self):
        """Init Processing provider for QGIS >= 3.8."""
        self.provider = EnergyStorageLocationEvaluatorProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def initGui(self):
        self.initProcessing()

    def unload(self):
        QgsApplication.processingRegistry().removeProvider(self.provider)
