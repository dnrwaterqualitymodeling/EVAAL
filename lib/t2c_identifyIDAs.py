import arcpy
from arcpy import env
from arcpy.sa import *
import numpy as np

def identifyIDAs(demFile, optimFillFile, prcpFile, cnFile, watershedFile, \
    nonContributingAreasFile, demFinalFile, ws):
    
    # Intermediate Files
    clipCn = ws['tempGdb'] + '/clipCn_' + ws['rid']
    runoffTable = ws['tempDir'] + '/runoffTable_' + ws['rid'] + '.dbf'
    storageTable = ws['tempDir'] + '/storageTable_' + ws['rid'] + '.dbf'
    trueSinkTable = ws['tempGdb'] + '/trueSinkTable_' + ws['rid']
    nonContribRaw = ws['tempGdb'] + '/nonContribRaw_' + ws['rid']
    nonContribFiltered = ws['tempGdb'] + '/nonContribFiltered_' + ws['rid']
    nonContribUngrouped = ws['tempGdb'] + '/nonContribUngrouped_' + ws['rid']
    inc_runoff = ws['tempGdb'] + '/inc_runoff_' + ws['rid']
    cum_runoff = ws['tempGdb'] + '/cum_runoff_' + ws['rid']
    sinkLarge_file = ws['tempGdb'] + '/sink_large_' + ws['rid']
    seeds_file1 = ws['tempGdb'] + '/seeds_' + ws['rid']
    seeds_file2 = ws['tempGdb'] + '/seeds2_' + ws['rid']

    env.snapRaster = demFile
    env.extent = demFile
    env.cellSize = arcpy.GetRasterProperties_management(demFile, 'CELLSIZEX').getOutput(0)
    env.mask = demFile

    arcpy.AddMessage("Identifying sinks...")
    fill = Fill(demFile)
    sinkDepth = fill - Raster(demFile)
    # area of a gridcell
    A = float(arcpy.GetRasterProperties_management(demFile, 'CELLSIZEX').getOutput(0))**2
    storageVolume = sinkDepth * A
    sinkExtent = Con(sinkDepth > 0, 1)
    sinkGroup = RegionGroup(sinkExtent, "EIGHT", '', 'NO_LINK')
    # to give each non contributing area the MAX depth in the area
    maxDepth = ZonalStatistics(sinkGroup, "Value", sinkDepth, "MAXIMUM", "DATA")
    prcpMeters = Raster(prcpFile) * 0.0000254
    # to assign the mean precip level to each noncontrib area
    meanPrecip = ZonalStatistics(sinkGroup, "Value", prcpMeters, "MEAN", "DATA")
    # only grab those areas where the depth is greater than the precip, thus only the non contributing areas
    sinkLarge = Con(maxDepth > meanPrecip, sinkGroup)
    sinkLarge.save(sinkLarge_file)
    arcpy.BuildRasterAttributeTable_management(sinkLarge, "Overwrite")
    # arcpy.AddField_management(sinkLarge, "true_sink", "SHORT")
    sinkLarge.save(sinkLarge_file)
    del sinkDepth, sinkExtent, sinkGroup, maxDepth
    
    allnoDat = int(arcpy.GetRasterProperties_management(sinkLarge, 'ALLNODATA').getOutput(0))
    arcpy.AddMessage('All no data returned: ' + str(allnoDat))
    if allnoDat == 1:
        arcpy.AddWarning("No internally draining areas found. Returning null raster and original conditioned DEM.")
        
        # Null raster being saved
        sinkLarge.save(nonContributingAreasFile)
        
        demFinal = arcpy.CopyRaster_management(demFile, demFinalFile)
    else:      
        arcpy.AddMessage("Calculating runoff...")
        CN = Raster(cnFile)
        prcpInches = Raster(prcpFile) / 1000.
        S = (1000.0 / CN) - 10.0
        Ia = 0.2 * S
        runoffDepth = (prcpInches - Ia)**2 / (prcpInches - Ia + S)
        runoffVolume = (runoffDepth * 0.0254) * A
        runoffVolume.save(inc_runoff)
        arcpy.AddMessage("Computing flow direction")
        fdr = FlowDirection(optimFillFile)
        arcpy.AddMessage("Computing runoff accumulation")
        runoffAcc = FlowAccumulation(fdr, runoffVolume, 'FLOAT')
        runoffAcc.save(cum_runoff)
        arcpy.AddMessage("Testing for sink capacity after storm")
        
        arcpy.BuildRasterAttributeTable_management(sinkLarge, "Overwrite")
        #Grab the maximum amount of runoff for each sink
        ZonalStatisticsAsTable(sinkLarge, "VALUE", runoffAcc, runoffTable, "DATA", "MAXIMUM")
        #Grab the total of the storage volume for each sink
        ZonalStatisticsAsTable(sinkLarge, "VALUE", storageVolume, storageTable, "DATA", "SUM")

        arcpy.JoinField_management(runoffTable, 'VALUE', storageTable, 'VALUE')
        # create new table, IF the total storage volume is greater than the max runoff
        arcpy.TableSelect_analysis(runoffTable, trueSinkTable, '"SUM" > "MAX"')
        del CN, S, Ia, runoffDepth
        
        trueSinkCount = int(arcpy.GetCount_management(trueSinkTable).getOutput(0))
    
        #if trueSinkCount > 0:
        trueSinks = []
        rows = arcpy.da.SearchCursor(trueSinkTable, ['Value'])
        for row in rows:
            trueSinks.append(row[0])
        del row, rows
        trueSinks = np.array(trueSinks)
        
        # ArcGIS set membership reclass functions (Reclassify, InList) are very slow
        # RasterToNumpyArray is used in blocks in an attempt to reduce computation time
        
        blocksize = 512
            
        xrng = range(0, sinkLarge.width, blocksize)
        yrng = range(0, sinkLarge.height, blocksize)
        
        tempfiles = []
        blockno = 0
        arcpy.AddMessage("Blocking sinks grids for numpy set membership")
        arcpy.ClearEnvironment("extent")
        for x in xrng:
            for y in yrng:
                
                # Lower left coordinate of block (in map units)
                mx = sinkLarge.extent.XMin + x * sinkLarge.meanCellWidth
                my = sinkLarge.extent.YMin + y * sinkLarge.meanCellHeight
                # Upper right coordinate of block (in cells)
                lx = min([x + blocksize, sinkLarge.width])
                ly = min([y + blocksize, sinkLarge.height])
                
                blck = arcpy.RasterToNumPyArray(sinkLarge, arcpy.Point(mx, my), lx-x, ly-y)
                blck_shp = blck.shape
                blck = blck.flatten()
                true_sink_blck = np.in1d(blck, trueSinks).astype(int)
                true_sink_blck = np.reshape(true_sink_blck, blck_shp)
                # true_sink_blck = np.isin(blck, trueSinks).astype(int)
                # Convert data block back to raster
                raster_blck = arcpy.NumPyArrayToRaster(
                    true_sink_blck,
                    arcpy.Point(mx, my),
                    sinkLarge.meanCellWidth,
                    sinkLarge.meanCellHeight
                )
                # Save on disk temporarily as 'filename_#.ext'
                # filetemp = ('_%i.' % blockno).join(seeds.rsplit('.',1))
                filetemp = seeds_file1 + ('_%i' % blockno)
                raster_blck.save(filetemp)

                # Maintain a list of saved temporary files
                tempfiles.append(filetemp)
                blockno += 1
        
        env.extent = demFile        
        # Mosaic temporary files
        arcpy.AddMessage("Mosaic blocks")
        if (len(tempfiles) > 1):
            arcpy.Mosaic_management(';'.join(tempfiles[1:]), tempfiles[0])
        if arcpy.Exists(seeds_file1):
            arcpy.Delete_management(seeds_file1)
        arcpy.Rename_management(tempfiles[0], seeds_file1)

        # Remove temporary files
        for fileitem in tempfiles:
            if arcpy.Exists(fileitem):
                arcpy.Delete_management(fileitem)

        # Release raster objects from memory
        del raster_blck
        
        arcpy.AddMessage("Delineating watersheds of 'true' sinks...")
        seeds2 = Con(Raster(seeds_file1) == 1, 1)
        seeds2.save(seeds_file2)
        nonContributingAreas = Watershed(fdr, Raster(seeds_file2))
        del seeds2, fdr

        arcpy.AddMessage("Saving output...")
        arcpy.RasterToPolygon_conversion(nonContributingAreas, nonContribRaw, False, 'Value')
        arcpy.MakeFeatureLayer_management(nonContribRaw, 'nonContribRaw_layer')
        arcpy.MakeFeatureLayer_management(watershedFile, 'watershed_layer')
        # To select those nonContributing watersheds that are within the target watershed
        arcpy.SelectLayerByLocation_management('nonContribRaw_layer', 'WITHIN', 'watershed_layer'\
            , '', 'NEW_SELECTION')
        arcpy.CopyFeatures_management('nonContribRaw_layer', nonContribFiltered)
        n_filtered = int(arcpy.GetCount_management(nonContribFiltered)[0])
        if n_filtered == 0:
            arcpy.AddWarning("No internally draining areas found. Returning null raster and original conditioned DEM.")
            
            # Null raster being saved
            null_out = SetNull(Raster(seeds_file2), Raster(seeds_file2), "Value IS NULL OR VALUE > 0")
            null_out.save(nonContributingAreasFile)
            
            demFinal = arcpy.CopyRaster_management(demFile, demFinalFile)
        else:
            #Convert only those nonContributing watersheds that are in the target to rasters
            #grid_code for 10.1 and gridcode for 10.2
            if int(arcpy.GetInstallInfo()['Version'].split('.')[1]) > 1:
                colNm = 'gridcode'
            else:
                colNm = 'grid_code'
            cs = arcpy.Describe(demFile).children[0].meanCellHeight
            arcpy.PolygonToRaster_conversion(nonContribFiltered, colNm \
                , nonContribUngrouped, 'CELL_CENTER', '', cs)
            noId = Reclassify(nonContribUngrouped, "Value", RemapRange([[1,1000000000000000,1]]))

            grouped = RegionGroup(noId, 'EIGHT', '', 'NO_LINK')
            grouped.save(nonContributingAreasFile)

            demFinal = Con(IsNull(nonContributingAreasFile), demFile)
            demFinal.save(demFinalFile)
