import arcpy
from arcpy import env
import importlib
import aggregateSSURGO as agsur
import makeSsurgoTable as mst

def kfact(gssurgoGdb, attField, demFile, watershedFile, outRaster, ws):

    arcpy.AddMessage('Creating gSSURGO table views...')
    compTable = gssurgoGdb + '/component'
    chorizonTable = gssurgoGdb + '/chorizon'
    arcpy.MakeTableView_management(chorizonTable, 'chorizon')
    arcpy.MakeTableView_management(compTable, 'component')

    arcpy.AddMessage("Calculating weighted average across horizons...")
    byHoriz = agsur.aggregateSSURGO('chorizon', attField, 'cokey', 'hzdept_r', 'top')
    attAveByHorizFile = ws['tempGdb'] + '/attAveByHoriz_' + ws['rid']
    arcpy.AddMessage("Writing table for weighted average across horizons...")
    mst.makeSsurgoTable(byHoriz, attAveByHorizFile)
    arcpy.MakeTableView_management(attAveByHorizFile, 'attAveByHoriz')
    arcpy.AddMessage("Joining weighted average across horizons to component table...")
    arcpy.AddJoin_management('component', 'cokey', 'attAveByHoriz', 'element')
    arcpy.AddMessage("Calculating weighted average across components...")
    byComp = agsur.aggregateSSURGO('component', 'attAveByHoriz_' + ws['rid'] + '.attAve'\
        , 'component.mukey', 'component.comppct_r', 'wa')
    attAveByCompFile = ws['tempGdb'] + '/attAveByComp_' + ws['rid']
    arcpy.AddMessage("Writing table for weighted average across components...")
    mst.makeSsurgoTable(byComp, attAveByCompFile)
    arcpy.AddMessage("Projecting gSSURGO...")
    env.snapRaster = demFile
    env.extent = demFile
    
    cs = arcpy.Describe(demFile).children[0].meanCellHeight
    env.cellSize = cs
    arcpy.Clip_analysis(gssurgoGdb + '/MUPOLYGON', watershedFile\
        , ws['tempGdb'] + '/MUPOLYGON_clip_' + ws['rid'])
    arcpy.Project_management(ws['tempGdb'] + '/MUPOLYGON_clip_' + ws['rid']\
        , ws['tempGdb'] + '/MUPOLYGON_prj_' + ws['rid']\
        , demFile, 'NAD_1983_To_HARN_Wisconsin')
    arcpy.MakeFeatureLayer_management(ws['tempGdb'] + '/MUPOLYGON_prj_' + ws['rid'], 'mupolygon')
    arcpy.AddJoin_management('mupolygon', 'MUKEY', attAveByCompFile, 'element')
    outField = 'attAveByComp_' + ws['rid'] + '.attAve'
    arcpy.PolygonToRaster_conversion('mupolygon', outField, outRaster\
        ,'MAXIMUM_COMBINED_AREA', '', cs)
