# -*- coding: utf-8 -*-
"""
Zonal Majority Classification - Processing Algorithm
Assigns dominant and subdominant land cover classes to polygons from a raster.
"""

from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterBand,
    QgsProcessingParameterVectorLayer,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterFile,
    QgsProcessingParameterDefinition,
    QgsProcessingUtils,
    QgsField,
    QgsFields,
    QgsFeature,
    QgsFeatureSink,
    QgsGeometry,
    QgsCoordinateTransform,
    QgsProject,
    QgsProcessingException,
)
import numpy as np
from osgeo import gdal, ogr, osr
import csv
import os
import processing as qgis_processing


class ZonalMajorityClassification(QgsProcessingAlgorithm):
    """
    Assigns each polygon the dominant (majority) and subdominant (second majority)
    land cover class from an underlying raster, along with their proportional
    coverage. Class labels are resolved from a built-in legend or an optional
    user-supplied CSV.
    """

    INPUT_RASTER = 'INPUT_RASTER'
    INPUT_BAND = 'INPUT_BAND'
    INPUT_VECTOR = 'INPUT_VECTOR'
    USE_CUSTOM_LEGEND = 'USE_CUSTOM_LEGEND'
    CUSTOM_LEGEND_CSV = 'CUSTOM_LEGEND_CSV'
    OUTPUT = 'OUTPUT'

    # ------------------------------------------------------------------
    # Built-in Somalia land cover legend (34 classes)
    # Mapping: pixel_value -> (class_code, class_name)
    # ------------------------------------------------------------------
    DEFAULT_LEGEND = {
        1:  ('TCL',     'Trees Closed'),
        2:  ('TOP',     'Trees Open'),
        3:  ('TVO',     'Trees Very Open'),
        4:  ('TBU',     'Tiger Bush'),
        5:  ('SCL',     'Shrubs Closed'),
        6:  ('SOP',     'Shrubs Open'),
        7:  ('SSP',     'Shrubs Sparse'),
        8:  ('TSS',     'Trees and Shrubs Savanna'),
        9:  ('HGV',     'Grassland'),
        10: ('HFL',     'Herbaceous Permanent'),
        11: ('RGF',     'Riverine Gallery Forest'),
        12: ('TSF',     'Trees Seasonally Flooded'),
        13: ('WVW-ER',  'Vegetated Wadi'),
        14: ('WMA',     'Woody Mangrove'),
        15: ('OPA',     'Cultivated - Palms'),
        16: ('OCR',     'Cultivated - Generic Orchards'),
        17: ('HPF',     'Cultivated - Herbaceous Perennial'),
        18: ('HCR',     'Cultivated - Herbaceous Rainfed'),
        19: ('HCI',     'Cultivated - Herbaceous Irrigated'),
        20: ('BUU',     'Urban Areas'),
        21: ('BUR',     'Rural Villages'),
        22: ('BUA',     'Airport'),
        23: ('BBM',     'Bomas'),
        24: ('BSO',     'Bare Soil'),
        25: ('BRO',     'Bare Rock'),
        26: ('BDL',     'Badlands'),
        27: ('BSD',     'Sand Dunes'),
        28: ('BLS',     'Loose and Shifting Sand'),
        29: ('WWP',     'Permanent Water Body'),
        30: ('WWT',     'Temporal Water Body'),
        31: ('WRI',     'River'),
        32: ('WWC',     'Water Catchments'),
        33: ('WBW-ER',  'Bare Wadi / Ephemeral'),
        34: ('XXX',     'Water Coastal'),
    }

    def tr(self, string):
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):
        return ZonalMajorityClassification()

    def name(self):
        return 'zonalmajorityclassification'

    def displayName(self):
        return self.tr('Zonal Majority Classification')

    def group(self):
        return self.tr('Land Cover Analysis')

    def groupId(self):
        return 'landcoveranalysis'

    def shortHelpString(self):
        return self.tr(
            'Assigns each polygon the dominant and subdominant land cover class '
            'from an underlying raster, together with proportional coverage (%).\n\n'
            'A built-in legend (34 classes) is used by default. To use a custom '
            'legend, expand the Advanced Parameters section, enable '
            '"Use Custom Legend CSV", and select your CSV file.\n\n'
            'Custom CSV format (3 required columns):\n'
            '  Pixel_value,Class_Code,Class_Name\n'
            '  1,TCL,Trees Closed\n'
            '  2,TOP,Trees Open\n'
            '  ...\n\n'
            'Notes:\n'
            '  - Invalid geometries are repaired automatically.\n'
            '  - CRS mismatch between vector and raster is handled on the fly.\n\n'
            'Output fields:\n'
            '  dominant_class_code      - Class code of majority land cover\n'
            '  dominant_class_name      - Class name of majority land cover\n'
            '  dominant_pixel_value     - Raw raster pixel value\n'
            '  dominant_coverage_pct    - Percentage of polygon area\n'
            '  subdominant_class_code   - Class code of second-ranked land cover\n'
            '  subdominant_class_name   - Class name of second-ranked land cover\n'
            '  subdominant_pixel_value  - Raw raster pixel value\n'
            '  subdominant_coverage_pct - Percentage of polygon area'
        )

    def initAlgorithm(self, config=None):
        # ---- Main parameters (always visible) ----
        self.addParameter(
            QgsProcessingParameterRasterLayer(
                self.INPUT_RASTER,
                self.tr('Land Cover Raster'),
            )
        )

        self.addParameter(
            QgsProcessingParameterBand(
                self.INPUT_BAND,
                self.tr('Band Number'),
                1,
                self.INPUT_RASTER
            )
        )

        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.INPUT_VECTOR,
                self.tr('Segmentation / Polygon Layer'),
                [QgsProcessing.TypeVectorPolygon],
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT,
                self.tr('Classified Output'),
            )
        )

        # ---- Advanced parameters (collapsed by default) ----
        param_use_custom = QgsProcessingParameterBoolean(
            self.USE_CUSTOM_LEGEND,
            self.tr('Use Custom Legend CSV (overrides built-in legend)'),
            defaultValue=False,
        )
        param_use_custom.setFlags(
            param_use_custom.flags() | QgsProcessingParameterDefinition.FlagAdvanced
        )
        self.addParameter(param_use_custom)

        param_csv = QgsProcessingParameterFile(
            self.CUSTOM_LEGEND_CSV,
            self.tr('Custom Legend CSV (Pixel_value, Class_Code, Class_Name)'),
            extension='csv',
            optional=True,
        )
        param_csv.setFlags(
            param_csv.flags() | QgsProcessingParameterDefinition.FlagAdvanced
        )
        self.addParameter(param_csv)

    # ------------------------------------------------------------------
    # Helper: load legend from CSV
    # ------------------------------------------------------------------
    def _load_legend_csv(self, csv_path, feedback):
        """Parse a legend CSV and return dict {pixel_value: (code, name)}."""
        legend = {}
        try:
            with open(csv_path, newline='', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                reader.fieldnames = [h.strip() for h in reader.fieldnames if h and h.strip()]
                for row in reader:
                    try:
                        pv = int(row['Pixel_value'].strip())
                        code = row['Class_Code'].strip()
                        name = row['Class_Name'].strip()
                        legend[pv] = (code, name)
                    except (KeyError, ValueError) as e:
                        feedback.pushWarning(f'Skipping invalid row in legend CSV: {row} ({e})')
        except Exception as e:
            raise QgsProcessingException(f'Failed to read legend CSV: {e}')
        if not legend:
            raise QgsProcessingException('Legend CSV is empty or has no valid rows.')
        feedback.pushInfo(f'Loaded custom legend with {len(legend)} classes.')
        return legend

    # ------------------------------------------------------------------
    # Helper: write a feature with NULL classification
    # ------------------------------------------------------------------
    def _write_null_feature(self, sink, out_fields, geom, attributes):
        out_feat = QgsFeature(out_fields)
        out_feat.setGeometry(geom)
        out_feat.setAttributes(attributes + [None] * 8)
        sink.addFeature(out_feat, QgsFeatureSink.FastInsert)

    # ------------------------------------------------------------------
    # Helper: fix geometries silently via native:fixgeometries
    # ------------------------------------------------------------------
    def _fix_geometries(self, vector_layer, context, feedback):
        """Run native:fixgeometries and return the repaired layer.
        Uses QgsProcessingUtils.mapLayerFromString for robust retrieval,
        which works even when the layer is not registered in the project."""
        feedback.pushInfo('Repairing invalid geometries...')
        result = qgis_processing.run(
            'native:fixgeometries',
            {
                'INPUT': vector_layer,
                'METHOD': 1,
                'OUTPUT': 'TEMPORARY_OUTPUT',
            },
            context=context,
            feedback=feedback,
            is_child_algorithm=True,
        )

        output_id = result['OUTPUT']
        fixed_layer = QgsProcessingUtils.mapLayerFromString(output_id, context)

        if not fixed_layer or not fixed_layer.isValid():
            raise QgsProcessingException('Geometry repair failed.')

        feedback.pushInfo(f'Geometry repair complete — {fixed_layer.featureCount()} features.')
        return fixed_layer

    # ------------------------------------------------------------------
    # Main processing
    # ------------------------------------------------------------------
    def processAlgorithm(self, parameters, context, feedback):
        raster_layer = self.parameterAsRasterLayer(parameters, self.INPUT_RASTER, context)
        band_number = self.parameterAsInt(parameters, self.INPUT_BAND, context)
        vector_layer = self.parameterAsVectorLayer(parameters, self.INPUT_VECTOR, context)
        use_custom = self.parameterAsBool(parameters, self.USE_CUSTOM_LEGEND, context)
        custom_csv = self.parameterAsFile(parameters, self.CUSTOM_LEGEND_CSV, context)

        if raster_layer is None or vector_layer is None:
            raise QgsProcessingException('Invalid input layers.')

        # ---- Step 1: Fix geometries silently ----
        vector_layer = self._fix_geometries(vector_layer, context, feedback)

        # ---- Step 2: Resolve legend ----
        if use_custom:
            if not custom_csv or not os.path.isfile(custom_csv):
                raise QgsProcessingException(
                    'Custom legend is enabled but no valid CSV file was provided.'
                )
            legend = self._load_legend_csv(custom_csv, feedback)
            feedback.pushInfo('Using custom legend CSV.')
        else:
            legend = self.DEFAULT_LEGEND
            feedback.pushInfo('Using built-in legend (34 classes).')

        # ---- Step 3: Open raster ----
        raster_path = raster_layer.source()
        ds = gdal.Open(raster_path)
        if ds is None:
            raise QgsProcessingException(f'Cannot open raster: {raster_path}')

        band = ds.GetRasterBand(band_number)
        nodata = band.GetNoDataValue()
        gt = ds.GetGeoTransform()
        raster_cols = ds.RasterXSize
        raster_rows = ds.RasterYSize
        raster_extent = raster_layer.extent()

        # ---- Step 4: CRS handling ----
        needs_transform = False
        coord_transform = None
        if vector_layer.crs() != raster_layer.crs():
            coord_transform = QgsCoordinateTransform(
                vector_layer.crs(),
                raster_layer.crs(),
                QgsProject.instance(),
            )
            needs_transform = True
            feedback.pushInfo('CRS mismatch detected — reprojecting polygons on the fly.')

        # ---- Step 5: Prepare output fields ----
        out_fields = QgsFields(vector_layer.fields())
        out_fields.append(QgsField('dominant_class_code',       QVariant.String))
        out_fields.append(QgsField('dominant_class_name',       QVariant.String))
        out_fields.append(QgsField('dominant_pixel_value',      QVariant.Int))
        out_fields.append(QgsField('dominant_coverage_pct',     QVariant.Double))
        out_fields.append(QgsField('subdominant_class_code',    QVariant.String))
        out_fields.append(QgsField('subdominant_class_name',    QVariant.String))
        out_fields.append(QgsField('subdominant_pixel_value',   QVariant.Int))
        out_fields.append(QgsField('subdominant_coverage_pct',  QVariant.Double))

        (sink, dest_id) = self.parameterAsSink(
            parameters, self.OUTPUT, context,
            out_fields, vector_layer.wkbType(), vector_layer.crs(),
        )

        features = vector_layer.getFeatures()
        total = vector_layer.featureCount()

        if total == 0:
            return {self.OUTPUT: dest_id}

        feedback.pushInfo(f'Processing {total} polygons...')

        # ---- Step 6: Iterate polygons ----
        for current, feat in enumerate(features):
            if feedback.isCanceled():
                break
            feedback.setProgress(int((current / total) * 100))

            geom = feat.geometry()
            attrs = feat.attributes()

            if geom.isEmpty() or geom.isNull():
                self._write_null_feature(sink, out_fields, geom, attrs)
                continue

            if needs_transform:
                geom_transformed = QgsGeometry(geom)
                geom_transformed.transform(coord_transform)
            else:
                geom_transformed = geom

            bbox = geom_transformed.boundingBox()

            if not raster_extent.intersects(bbox):
                self._write_null_feature(sink, out_fields, geom, attrs)
                continue

            # Convert bounding box to pixel offsets
            x_off = int((bbox.xMinimum() - gt[0]) / gt[1])
            y_off = int((bbox.yMaximum() - gt[3]) / gt[5])
            x_end = int((bbox.xMaximum() - gt[0]) / gt[1]) + 1
            y_end = int((bbox.yMinimum() - gt[3]) / gt[5]) + 1

            x_off = max(0, x_off)
            y_off = max(0, y_off)
            x_end = min(raster_cols, x_end)
            y_end = min(raster_rows, y_end)

            x_size = x_end - x_off
            y_size = y_end - y_off

            if x_size <= 0 or y_size <= 0:
                self._write_null_feature(sink, out_fields, geom, attrs)
                continue

            data = band.ReadAsArray(x_off, y_off, x_size, y_size)
            if data is None:
                self._write_null_feature(sink, out_fields, geom, attrs)
                continue

            # Create in-memory mask raster
            mask_ds = gdal.GetDriverByName('MEM').Create('', x_size, y_size, 1, gdal.GDT_Byte)
            mask_ds.SetGeoTransform((
                gt[0] + x_off * gt[1], gt[1], 0,
                gt[3] + y_off * gt[5], 0, gt[5],
            ))
            mask_ds.SetProjection(ds.GetProjection())
            mask_ds.GetRasterBand(1).Fill(0)

            # Rasterize polygon — wkbUnknown handles single and multi-part
            ogr_ds = ogr.GetDriverByName('Memory').CreateDataSource('')
            srs = osr.SpatialReference()
            srs.ImportFromWkt(ds.GetProjection())
            ogr_layer = ogr_ds.CreateLayer('poly', srs, ogr.wkbUnknown)
            ogr_feat = ogr.Feature(ogr_layer.GetLayerDefn())
            ogr_feat.SetGeometry(ogr.CreateGeometryFromWkt(geom_transformed.asWkt()))
            ogr_layer.CreateFeature(ogr_feat)

            gdal.RasterizeLayer(mask_ds, [1], ogr_layer, burn_values=[1])
            mask_arr = mask_ds.GetRasterBand(1).ReadAsArray()

            del ogr_feat, ogr_layer, ogr_ds, mask_ds

            # Extract valid pixels within polygon
            valid_mask = mask_arr == 1
            if nodata is not None:
                valid_mask = valid_mask & (data != nodata)

            values = data[valid_mask]

            dom_code = None
            dom_name = None
            dom_val  = None
            dom_pct  = None
            sub_code = None
            sub_name = None
            sub_val  = None
            sub_pct  = None

            if values.size > 0:
                unique_vals, counts = np.unique(values, return_counts=True)
                sorted_indices = np.argsort(-counts)
                total_pixels = values.size

                # Dominant class
                dom_val = int(unique_vals[sorted_indices[0]])
                dom_pct = round((counts[sorted_indices[0]] / total_pixels) * 100, 2)
                if dom_val in legend:
                    dom_code, dom_name = legend[dom_val]

                # Subdominant class
                if len(unique_vals) > 1:
                    sub_val = int(unique_vals[sorted_indices[1]])
                    sub_pct = round((counts[sorted_indices[1]] / total_pixels) * 100, 2)
                    if sub_val in legend:
                        sub_code, sub_name = legend[sub_val]

            out_feat = QgsFeature(out_fields)
            out_feat.setGeometry(geom)
            out_feat.setAttributes(attrs + [
                dom_code, dom_name, dom_val, dom_pct,
                sub_code, sub_name, sub_val, sub_pct,
            ])
            sink.addFeature(out_feat, QgsFeatureSink.FastInsert)

        ds = None
        feedback.pushInfo('Processing complete.')
        return {self.OUTPUT: dest_id}
