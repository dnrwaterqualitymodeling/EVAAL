import arcpy
from arcpy import env
from arcpy.sa import *
import math

def usle(demFile, fillFile, erosivityFile, erosivityConstant, kFactorFile, cFactorFile, \
    facThreshold, outFile, ws):

    env.snapRaster = demFile
    env.extent = demFile
    env.mask = demFile

    origRes = float(arcpy.GetRasterProperties_management(demFile, 'CELLSIZEX').getOutput(0))

    # Temp files
    resampleDemFile = ws['tempGdb'] + "/resample"
    resampleFillFile = ws['tempGdb'] + "/resampleFill"
    lsFile = ws['tempGdb'] + "/ls"

    # Resample the dem to 10-meter resolution (use linear interpolation resample method)
    arcpy.AddMessage("Resampling conditioned DEM...")
    arcpy.Resample_management(demFile, resampleDemFile, "10", "BILINEAR")
    arcpy.AddMessage("Resampling re-conditioned DEM...")
    arcpy.Resample_management(fillFile, resampleFillFile, "10", "BILINEAR")
    env.cellSize = arcpy.GetRasterProperties_management(resampleDemFile, 'CELLSIZEX').getOutput(0)
    arcpy.AddMessage("Re-filling re-conditioned DEM...")
    refill = Fill(resampleFillFile)

    arcpy.AddMessage("Calculating LS-factor from grid. This may take awhile...")
    fac = FlowAccumulation(FlowDirection(refill))
    arcpy.AddMessage('Removing flow accumulation pixels above threshold...')
    facLand = Plus(Con(fac < facThreshold, fac), 1.0)
    del fac
    Am = facLand * 100
    del facLand
    arcpy.AddMessage('Calculating br term of slope/slope-length equation...')
    br = Slope(resampleDemFile, "DEGREE") * (math.pi / 180.0)

    a0 = 22.1
    m = 0.6
    n = 1.3
    b0 = 0.09
    arcpy.AddMessage('Calculating slope/slope-length...')
    LS10 = (m+1)*((Am / a0)**m)*((Sin(br) / b0)**n)
    del a0, m, n, b0
    arcpy.Resample_management(LS10, lsFile, origRes, "BILINEAR")
    del LS10

    env.cellSize = arcpy.GetRasterProperties_management(demFile, 'CELLSIZEX').getOutput(0)
    arcpy.AddMessage("Calculating Soil Loss...")
    if erosivityConstant is None and erosivityFile is None:
        R = 1
    elif erosivityConstant == '':
        R = Raster(erosivityFile)
    else:
        R = float(erosivityConstant)
    K = Raster(kFactorFile)
    C = Raster(cFactorFile)
    LS = Con(
        BooleanAnd(IsNull(lsFile), (Raster(demFile) > 0)),
        0,
        lsFile
    )

    E = R * K * LS * C

    E.save(outFile)
    del E, R, K, LS, C
