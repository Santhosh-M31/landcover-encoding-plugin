# -*- coding: utf-8 -*-
"""
Zonal Majority Classification - Plugin loader
Registers the processing provider so the algorithm appears in the Processing Toolbox.
"""

from qgis.core import QgsApplication
from .provider import ZonalMajorityClassificationProvider


class ZonalMajorityClassificationPlugin:
    """QGIS Plugin — registers a custom Processing provider."""

    def __init__(self, iface):
        self.iface = iface
        self.provider = None

    def initProcessing(self):
        """Create and register the processing provider."""
        self.provider = ZonalMajorityClassificationProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def initGui(self):
        """Called when the plugin is loaded into QGIS."""
        self.initProcessing()

    def unload(self):
        """Called when the plugin is unloaded from QGIS."""
        if self.provider is not None:
            QgsApplication.processingRegistry().removeProvider(self.provider)
