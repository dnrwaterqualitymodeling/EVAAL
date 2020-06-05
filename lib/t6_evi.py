import arcpy
from arcpy import env
from arcpy.sa import *
import numpy as np
from scipy import stats


def evi(usle_file, spi_file, subset_ag, ag_file, zonal_file, zonal_id, subset_zone, out_raster, out_tbl, ws):
    template = Raster(usle_file)
    env.snapRaster = template
    env.extent = template
    env.cellSize = template.meanCellHeight

    zonal_raster = ws['tempGdb'] + '/zonalRaster_' + ws['rid']

    arcpy.AddMessage("Creating mask...")
    if zonal_id is None:
        zonal_id = 'OBJECTID'
    if zonal_file is not None:
        arcpy.PolygonToRaster_conversion(zonal_file, zonal_id, zonal_raster, 'CELL_CENTER', '', env.cellSize)
        zonal_array = arcpy.RasterToNumPyArray(zonal_raster).flatten()
    if ag_file is not None:
        ag_array = arcpy.RasterToNumPyArray(
            ag_file,
            lower_left_corner=arcpy.Point(template.extent.XMin, template.extent.YMin),
            ncols=template.width,
            nrows=template.height
        )
        # 0s are null and 1 is 'no agriculture'
        ag_array = np.in1d(ag_array, [0, 1], invert=True)

    if subset_ag == 'true' and subset_zone == 'false':
        mask = ag_array
    elif subset_ag == 'false' and subset_zone == 'true':
        mask = zonal_array > 0
    elif subset_ag == 'true' and subset_zone == 'true':
        mask = np.all([ag_array, zonal_array > 0], axis=0)
    else:
        mask = ag_array >= 0

    if ag_file is not None:
        del ag_array

    arcpy.AddMessage("Calculating summary statistics of soil loss and stream power index...")
    usle = arcpy.RasterToNumPyArray(usle_file).flatten()
    usle[mask] = stats.rankdata(usle[mask]) / len(usle[mask])
    # usle = np.log10(usle + 1)
    spi = arcpy.RasterToNumPyArray(spi_file).flatten()
    spi[mask] = stats.rankdata(spi[mask]) / len(spi[mask])
    # spi = np.log(spi + 1)
    evi = usle + spi


    evi[mask] = ((evi[mask] - np.min(evi[mask])) * 3) / (np.max(evi[mask]) - np.min(evi[mask]))

    evi[np.invert(mask)] = -9999
    evi = np.reshape(evi, (template.height, template.width))
    evi_raster = arcpy.NumPyArrayToRaster(
        evi,
        lower_left_corner=arcpy.Point(template.extent.XMin, template.extent.YMin),
        x_cell_size=template.meanCellHeight,
        y_cell_size=template.meanCellHeight,
        value_to_nodata=-9999
    )

    if out_raster is not None:
        evi_raster.save(out_raster)
    if zonal_file is not None:
        arcpy.AddMessage("Summarizing erosion vulnerability index within zonal statistics feature class boundaries...")
        fields = arcpy.ListFields(zonal_raster)
        if len(fields) == 3:
            ZonalStatisticsAsTable(zonal_raster, 'Value', evi_raster, out_tbl, "DATA", "ALL")
        else:
            ZonalStatisticsAsTable(zonal_raster, zonal_id, evi_raster, out_tbl, "DATA", "ALL")
