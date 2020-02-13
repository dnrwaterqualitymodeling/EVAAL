import arcpy
from arcpy import env
from arcpy.sa import *

def evi(usleFile, spiFile, zonalFile, zonalId, demFile, outErosionScoreFile, outSummaryTable, ws):

    env.snapRaster = demFile
    env.extent = demFile
    env.cellSize = arcpy.GetRasterProperties_management(demFile, 'CELLSIZEX').getOutput(0)

    arcpy.AddMessage("Converting zones to raster...")
    if zonalId is None:
        zonalId = 'OBJECTID'
    if zonalFile is not None:

        zonal = arcpy.PolygonToRaster_conversion(zonalFile, zonalId, ws['tempGdb'] + '/zonalRaster'\
            , 'CELL_CENTER', '', demFile)

        env.mask = ws['tempGdb'] + '/zonalRaster'

    arcpy.AddMessage("Calculating summary statistics of soil loss and stream power index...")
    lnUsle = Ln(Raster(usleFile) + 1)
        # x 1 was added by T. Nelson on 2014-08-20
        #    Arc was not able to calculate stats on (line 978)
        #    this '*1' seems to work...for some reason
    spi = Raster(spiFile)*1

    arcpy.CalculateStatistics_management(spi)
    arcpy.CalculateStatistics_management(lnUsle)

    spiMean = float(arcpy.GetRasterProperties_management(spi, "MEAN").getOutput(0))
    spiSd = float(arcpy.GetRasterProperties_management(spi, "STD").getOutput(0))
    usleMean = float(arcpy.GetRasterProperties_management(lnUsle, "MEAN").getOutput(0))
    usleSd = float(arcpy.GetRasterProperties_management(lnUsle, "STD").getOutput(0))

    arcpy.AddMessage("Calculating Z-scores...")
    spiZ = (spi - spiMean) / spiSd
    usleZ = (lnUsle - usleMean) / usleSd
    arcpy.AddMessage("Calculating erosion vulnerability index...")
    erosionScore = spiZ + usleZ

    if outErosionScoreFile is not None:
        erosionScore.save(outErosionScoreFile)
    if zonalFile is not None:
        arcpy.AddMessage("Summarizing erosion vulnerability index within zonal statistics feature class boundaries...")
        fields = arcpy.ListFields(ws['tempGdb'] + '/zonalRaster')
        if len(fields) == 3:
            erosionScoreByClu = ZonalStatisticsAsTable(ws['tempGdb'] + '/zonalRaster', 'Value', erosionScore\
                    , outSummaryTable, "DATA", "ALL")
        else:
            erosionScoreByClu = ZonalStatisticsAsTable(ws['tempGdb'] + '/zonalRaster', zonalId, erosionScore\
                , outSummaryTable, "DATA", "ALL")
