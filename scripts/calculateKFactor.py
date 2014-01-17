import arcpy, os, random
sys.path.insert(1, sys.path[0] + '/scripts')
import setupTemp as tmp
import numpy as np
from arcpy import env
arcpy.CheckOutExtension("Spatial")
from arcpy.sa import *
env.overwriteOutput = True

def aggregateByElement(tableName, attField, elemField, wtField, stat):
	nRows = int(arcpy.GetCount_management(tableName).getOutput(0))
	elem = np.empty(nRows, dtype='S15')
	att = np.empty(nRows, dtype=np.float)
	wt = np.empty(nRows, dtype=np.float)
	rows = arcpy.SearchCursor(tableName)
	for i,row in enumerate(rows):
		elem[i] = row.getValue(elemField)
		att[i] = row.getValue(attField)
		wt[i] = row.getValue(wtField)
	del i, row, rows
	# Delete rows with nan values or weights equal to zero
	if stat == 'wa':
		inds = np.invert((np.isnan(att) + np.isnan(wt) + (wt == 0)) > 0)
	elif stat == 'top':
		inds = np.invert((np.isnan(att) + np.isnan(wt) + (wt > 0)) > 0)
	elem = elem[inds]
	att = att[inds]
	wt = wt[inds]
	attAve = np.zeros([len(np.unique(elem)),2], dtype=np.float)
	for i,m in enumerate(np.unique(elem)):
                ind = np.where(elem == m)
		if stat == 'wa':
			attAve[i,0:2] = np.array(np.average(att[ind], weights=wt[ind], returned=True))
		elif stat == 'top':
			attAve[i,0:2] = np.array(np.average(att[ind], returned=True))
	del i,m
	attAve = attAve[np.where(attAve[:,1] > 0)]
	elem = np.array(np.unique(elem)[np.where(attAve[:,1] > 0)])
	return {'element' : elem, 'attAve' : attAve}

def makeTableFromAggregatedData(dataDict, tableFile):
	if arcpy.Exists(tableFile):
		arcpy.Delete_management(tableFile)
	arcpy.CreateTable_management(os.path.dirname(tableFile), os.path.basename(tableFile))
	arcpy.AddField_management(tableFile, 'element', 'TEXT', '', '', 15)
	arcpy.AddField_management(tableFile, 'attAve', 'FLOAT', 5, 3)
	arcpy.AddField_management(tableFile, 'wt_sum', 'FLOAT', 5, 3)
	rows = arcpy.InsertCursor(tableFile)
	for i,m in enumerate(np.unique(dataDict['element'])):
		row = rows.newRow()
		row.element = str(m)
		row.attAve = float(dataDict['attAve'][i,0])
		row.wt_sum = float(dataDict['attAve'][i,1])
		rows.insertRow(row)
	del row, rows

def mainProcess(gssurgoGdb, attField, demFile, outRaster):
	randId = str(random.randint(1e5,1e6))

	tempDir = tmp.tempDir
	tempGdb = tmp.tempGdb
	os.environ['ARCTMPDIR'] = tmp.tempDir

	env.scratchWorkspace = tempDir
	env.workspace = tempDir

	arcpy.AddMessage('Creating gSSURGO table views...')
	compTable = gssurgoGdb + '/component'
	chorizonTable = gssurgoGdb + '/chorizon'
	arcpy.MakeTableView_management(chorizonTable, 'chorizon')
	arcpy.MakeTableView_management(compTable, 'component')

	arcpy.AddMessage("Calculating weighted average across horizons...")
	byHoriz = aggregateByElement('chorizon', attField, 'cokey', 'hzdept_r', 'top')
	attAveByHorizFile = tempGdb + '/attAveByHoriz_' + randId
	arcpy.AddMessage("Writing table for weighted average across horizons...")
	makeTableFromAggregatedData(byHoriz, attAveByHorizFile)
	arcpy.MakeTableView_management(attAveByHorizFile, 'attAveByHoriz')
	arcpy.AddMessage("Joining weighted average across horizons to component table...")
	arcpy.AddJoin_management('component', 'cokey', 'attAveByHoriz', 'element')
	arcpy.AddMessage("Calculating weighted average across components...")
	byComp = aggregateByElement('component', 'attAveByHoriz_' + randId + '.attAve'\
		, 'component.mukey', 'component.comppct_r', 'wa')
	attAveByCompFile = tempGdb + '/attAveByComp_' + randId
	arcpy.AddMessage("Writing table for weighted average across components...")
	makeTableFromAggregatedData(byComp, attAveByCompFile)
	arcpy.AddMessage("Projecting gSSURGO...")
	env.snapRaster = demFile
	env.extent = demFile
	env.cellSize = demFile
	arcpy.Clip_analysis(gssurgoGdb + '/MUPOLYGON', watershedFile\
		, tempGdb + '/MUPOLYGON_clip_' + randId)
	arcpy.Project_management(tempGdb + '/MUPOLYGON_clip_' + randId\
		, tempGdb + '/MUPOLYGON_prj_' + randId\
		, demFile, 'NAD_1983_To_HARN_Wisconsin')
	arcpy.MakeFeatureLayer_management(tempGdb + '/MUPOLYGON_prj_' + randId, 'mupolygon')
	arcpy.AddJoin_management('mupolygon', 'MUKEY', attAveByCompFile, 'element')
	outField = 'attAveByComp_' + randId + '.attAve'
	arcpy.PolygonToRaster_conversion('mupolygon', outField, outRaster\
		,'MAXIMUM_COMBINED_AREA', '', demFile)

if __name__ == '__main__':
	gssurgoGdb = arcpy.GetParameterAsText(0)
	attField = arcpy.GetParameterAsText(1)
	demFile = arcpy.GetParameterAsText(2)
	watershedFile = arcpy.GetParameterAsText(3)
	outRaster = arcpy.GetParameterAsText(4)

	mainProcess(gssurgoGdb, attField, demFile, outRaster)
