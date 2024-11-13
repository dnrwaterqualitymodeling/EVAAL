import arcpy
from arcpy import env
from arcpy.sa import *
import os
import subprocess as sp

def demConditioning(culverts, watershed, dem, buffer_size, dem_cond, dem_optim, ws):
    watershedBuffer = ws['tempGdb'] + '/watershedBuffer_' + ws['rid']
    lidarClip = ws['tempGdb'] + "/lidarClip_" + ws['rid']
    culverts_clip = ws['tempGdb'] + "/culverts_clip" + ws['rid']
    asciiDem = ws['tempDir'] + "/dem_" + ws['rid'] + ".asc"
    asciiConditioned = ws['tempDir'] + "/conditioned_" + ws['rid'] + ".asc"

    buffer_str = str(buffer_size) + ' Meters'
    arcpy.Buffer_analysis(watershed, watershedBuffer, buffer_str)
    arcpy.AddMessage("Clipping to watershed extent...")
    arcpy.Clip_management(dem, "", lidarClip, watershedBuffer, clipping_geometry="ClippingGeometry")
    arcpy.AddMessage("Clipping culverts to watershed extent")
    arcpy.Clip_analysis(culverts, watershedBuffer, culverts_clip)
    arcpy.AddMessage("Rasterizing culverts...")
    env.cellSize = Raster(lidarClip).meanCellHeight
    env.snapRaster = lidarClip
    env.extent = lidarClip
    cul_ras = ZonalStatistics(
        culverts_clip,
        arcpy.Describe(culverts).OIDFieldName,
        lidarClip,
        "MINIMUM"
    )
    dem_culv_burn = Con(IsNull(cul_ras), lidarClip, cul_ras)
    del cul_ras
    dem_culv_burn.save(dem_cond)
    del dem_culv_burn

    arcpy.AddMessage("Converting to ASCII...")
    arcpy.RasterToASCII_conversion(dem_cond, asciiDem)

    arcpy.AddMessage("Running optimized fill tool...")
    if os.path.exists(asciiConditioned):
        os.remove(asciiConditioned)
    asciiConditioned = asciiConditioned.replace("/", "\\")
    asciiDem = asciiDem.replace("/", "\\")
    spCall = [ws['optFillExe'], '-z', asciiDem, '-fel', asciiConditioned, '-mode', 'bal', '-step', '0.1']
    p = sp.Popen(spCall, startupinfo=ws['startupinfo'])
    p.wait()

    arcpy.AddMessage("Converting conditioned DEM back to raster...")
    arcpy.ASCIIToRaster_conversion(asciiConditioned, dem_optim, "FLOAT")
    arcpy.DefineProjection_management(dem_optim, watershed)

    os.remove(asciiConditioned)
    os.remove(asciiDem)

    for dataset in [lidarClip, culverts_clip]:
        arcpy.Delete_management(dataset)
