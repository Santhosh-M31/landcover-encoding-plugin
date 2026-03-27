# -*- coding: utf-8 -*-
"""
Zonal Majority Classification - Processing Provider
Groups all algorithms under the 'Land Cover Tools' provider in the Processing Toolbox.
"""

import os
from qgis.core import QgsProcessingProvider
from qgis.PyQt.QtGui import QIcon
from .algorithm import ZonalMajorityClassification


class ZonalMajorityClassificationProvider(QgsProcessingProvider):
    """Custom processing provider for land cover analysis tools."""

    def id(self):
        return 'landcovertools'

    def name(self):
        return 'Land Cover Tools'

    def longName(self):
        return 'Land Cover Analysis Tools'

    def icon(self):
        icon_path = os.path.join(os.path.dirname(__file__), 'icon.png')
        if os.path.exists(icon_path):
            return QIcon(icon_path)
        return super().icon()

    def loadAlgorithms(self):
        self.addAlgorithm(ZonalMajorityClassification())
