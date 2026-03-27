# -*- coding: utf-8 -*-
"""
Zonal Majority Classification - QGIS Plugin
Assigns dominant and subdominant land cover classes to polygons from a raster.
"""


def classFactory(iface):
    """Load the plugin class.

    :param iface: A QGIS interface instance.
    :type iface: QgsInterface
    """
    from .plugin import ZonalMajorityClassificationPlugin
    return ZonalMajorityClassificationPlugin(iface)
