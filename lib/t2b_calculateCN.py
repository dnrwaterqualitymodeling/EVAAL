import arcpy
from arcpy import env
from arcpy.sa import *
import numpy as np
import json
import downloadCDL as dcdl
import queryCN as qcn
# import importlib
# importlib.reload(dcdl)
# importlib.reload(qcn)


def calculateCN(download_bool, yr_start, yr_end, local_cdl, gssurgo, watershed, dem_cond, out_cn_low, out_cn_high, ws):

    # Intermediate files
    years = np.arange(int(yr_start), int(yr_end) + 1).tolist()
    watershedCdlPrj = ws['tempGdb'] + '/watershedCdlPrj_' + ws['rid']
    clipSSURGO = ws['tempGdb'] + '/clipSSURGO_' + ws['rid']
    samplePts = ws['tempGdb'] + '/samplePts_' + ws['rid']
    joinSsurgo = ws['tempGdb'] + '/joinSsurgo_' + ws['rid']
    mapunits_prj = ws['tempGdb'] + '/mapunits_prj_' + ws['rid']
    out_cn_low1 = ws['tempGdb'] + '/out_cn_low1_' + ws['rid']
    out_cn_high1 = ws['tempGdb'] + '/out_cn_high1_' + ws['rid']

    # Read in C-factor crosswalk table and CDL legend file
    dtypes = ['i1', 'S60', 'S4', 'S25', 'i1', 'i1', 'i1', 'i1']
    cnLookup = np.genfromtxt(ws['cnLookupFile'], dtype=dtypes, delimiter=',', names=True)
    f = open(ws['coverTypeLookupFile'], 'r')
    coverTypeLookup = json.load(f)
    f.close()
    del f
    arcpy.AddMessage("Projecting Area Of Interest to Cropland Data Layer projection...")
    sr = arcpy.SpatialReference(102039)
    arcpy.Project_management(watershed, watershedCdlPrj, sr, "NAD_1983_To_HARN_Wisconsin")
    if download_bool == 'true':
        arcpy.AddMessage("Downloading Cropland Data Layers...")
        cdlTiffs = dcdl.downloadCDL(yr_start, yr_end, ws['tempDir'], watershedCdlPrj, ws['rid'])
    else:
        local_cdl = local_cdl.split(';')
        cdlTiffs = []
        years = []
        for i,localCdl in enumerate(local_cdl):
            clipCdl = ws['tempDir'] + '/cdl_' + str(i) + '_' + ws['rid'] + '.tif'
            arcpy.Clip_management(localCdl, '', clipCdl, watershedCdlPrj)
            cdlTiffs.append(clipCdl)
            years.append(i)

    resolutions = []
    for cdlTiff in cdlTiffs:
        res = float(arcpy.GetRasterProperties_management(cdlTiff, 'CELLSIZEX').getOutput(0))
        resolutions.append(res)
    minResCdlTiff = np.array(cdlTiffs)[resolutions == np.min(resolutions)][0]
    arcpy.RasterToPoint_conversion(minResCdlTiff, samplePts)

    cdlList = []
    yrCols = []
    for i,year in enumerate(years):
        yrCol = 'lc_' + str(year)
        yrCols.append(yrCol)
        cdlList.append([cdlTiffs[i], yrCol])

    ExtractMultiValuesToPoints(samplePts, cdlList, 'NONE')

    arcpy.AddMessage("Overlaying gSSURGO Hydrologic Soil Group...")
    arcpy.Clip_analysis(gssurgo + "/MUPOLYGON", watershed, clipSSURGO)
    arcpy.Project_management(clipSSURGO, mapunits_prj, dem_cond)
    arcpy.JoinField_management(mapunits_prj, "MUKEY", gssurgo + "/muaggatt" \
        , "MUKEY", "hydgrpdcd")
    arcpy.SpatialJoin_analysis(samplePts, mapunits_prj, joinSsurgo, '' \
        , 'KEEP_COMMON', '', 'INTERSECT')

    arcpy.AddMessage("Querying TR-55 based on land cover and hydrologic soil group...")
    arcpy.AddField_management(joinSsurgo, 'cnLow', 'FLOAT')
    arcpy.AddField_management(joinSsurgo, 'cnHigh', 'FLOAT')
    ptCount = int(arcpy.GetCount_management(joinSsurgo).getOutput(0))
    msg = "Generalizing rotation from crop sequence, and applying a C-factor..."
    arcpy.SetProgressor("step", msg, 0, ptCount, 1)
    rows = arcpy.da.UpdateCursor(joinSsurgo, ['hydgrpdcd'] + yrCols + ['cnLow', 'cnHigh'])
    for row in rows:
        if row[0] is None:
            hsgs = ['A','B','C','D']
        else:
            hsgs = [str(row[0][0])]
        lcs = []
        for y in range(1,len(yrCols)+1):
            if row[y] is None:
                lcs.append('0')
            else:
                lcs.append(str(row[y]))
        cnsHigh = []
        cnsLow = []
        for lc in lcs:
            for scen, hydCond in zip(['low', 'high'], ['Good', 'Poor']):
                cn = qcn.queryCN(lc, hsgs, scen, coverTypeLookup, cnLookup)
                if scen == 'low' and cn is not None:
                    cnsLow.append(cn)
                elif scen == 'high' and cn is not None:
                    cnsHigh.append(cn)
        if (len(cnsHigh) > 0) and (len(cnsLow) > 0):
            row[len(yrCols) + 1] = np.mean(cnsLow)
            row[len(yrCols) + 2] = np.mean(cnsHigh)
        rows.updateRow(row)
        arcpy.SetProgressorPosition()
    arcpy.ResetProgressor()
    del row, rows

    arcpy.AddMessage("Creating output rasters...")
    arcpy.PointToRaster_conversion(joinSsurgo, "cnLow", out_cn_low1, 'MOST_FREQUENT', '', minResCdlTiff)
    arcpy.PointToRaster_conversion(joinSsurgo, "cnHigh", out_cn_high1, 'MOST_FREQUENT', '', minResCdlTiff)

    env.snapRaster = dem_cond
    env.cellSize = Raster(dem_cond).meanCellHeight
    env.mask = dem_cond

    wtm = arcpy.Describe(dem_cond).spatialReference
    arcpy.ProjectRaster_management(out_cn_low1, out_cn_low, wtm, 'BILINEAR', env.cellSize)
    arcpy.ProjectRaster_management(out_cn_high1, out_cn_high, wtm, 'BILINEAR', env.cellSize)
